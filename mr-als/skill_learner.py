#!/usr/bin/env python3
"""
skill_learner.py — MR-ALS Phase 7: Skill Performance Tracker

Aggregates routing_outcomes.jsonl by task type to build a picture of which
task types the current skill set serves well vs poorly.

Outputs:
  experience/skills_performance.json — per-type performance summary + tier labels

Tier labels:
  excellent  — avg_quality >= 75, pct_poor < 0.15
  good       — avg_quality >= 60, pct_poor < 0.30
  fair       — avg_quality >= 45
  poor       — below fair thresholds

Usage:
    python3 skill_learner.py              # analyze and write skills_performance.json
    python3 skill_learner.py --report     # also print summary table
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev

from experience_hygiene import load_joined_records, summarize_learning_dataset

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
EXP_DIR = MR_DIR / "experience"
OUTCOMES_JSONL = EXP_DIR / "routing_outcomes.jsonl"
SKILLS_PERF = EXP_DIR / "skills_performance.json"

TYPES = ["code", "audit", "research", "production", "integration", "config", "design"]

# Primary pipeline labels per type (mirrors meta_router_runtime._PRIMARY)
_PRIMARY_PIPELINE = {
    "code":        "som",
    "audit":       "eop-adv-pass",
    "research":    "som",
    "production":  "som",
    "integration": "som",
    "design":      "som",
    "config":      "som",
}

# Tier thresholds
_TIERS = [
    ("excellent", lambda avg, pct: avg >= 75.0 and pct < 0.15),
    ("good",      lambda avg, pct: avg >= 60.0 and pct < 0.30),
    ("fair",      lambda avg, pct: avg >= 45.0),
    ("poor",      lambda avg, pct: True),  # catch-all
]


def _tier_for(avg_quality: float, pct_poor: float) -> str:
    for label, predicate in _TIERS:
        if predicate(avg_quality, pct_poor):
            return label
    return "poor"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return result


def _trend(series: list[float]) -> str:
    """Rough trend label from recent vs earlier half of a quality series."""
    if len(series) < 4:
        return "insufficient_data"
    mid = len(series) // 2
    early_avg = mean(series[:mid])
    late_avg = mean(series[mid:])
    diff = late_avg - early_avg
    if diff > 5:
        return "improving"
    if diff < -5:
        return "degrading"
    return "stable"


def analyze(dry_run: bool = False) -> dict:
    """
    Read routing_outcomes.jsonl and compute per-type skill performance metrics.
    Returns the full skills_performance dict.
    """
    joined_records = load_joined_records(EXP_DIR / "routing_events.jsonl", OUTCOMES_JSONL)
    eligibility_summary = summarize_learning_dataset(joined_records, min_eligible_outcomes=50)
    outcomes = [record for record in joined_records if record.get("eligible_for_learning")]

    # Group qualities by type (chronological order for trend)
    type_series: dict[str, list[float]] = {t: [] for t in TYPES}
    type_latencies: dict[str, list[float]] = {t: [] for t in TYPES}

    for o in outcomes:
        tt = o.get("task_type", "code")
        q = o.get("outcome_quality")
        lat = o.get("latency_ms")
        if tt in type_series and q is not None:
            type_series[tt].append(float(q))
        if tt in type_latencies and lat is not None:
            type_latencies[tt].append(float(lat))

    per_type: dict[str, dict] = {}
    for t in TYPES:
        qs = type_series[t]
        lats = type_latencies[t]
        if not qs:
            per_type[t] = {
                "task_type": t,
                "primary_pipeline": _PRIMARY_PIPELINE.get(t, "som"),
                "count": 0,
                "tier": "no_data",
                "avg_quality": None,
                "std_quality": None,
                "pct_poor": None,
                "trend": "no_data",
                "avg_latency_ms": None,
            }
            continue

        avg_q = round(mean(qs), 2)
        std_q = round(stdev(qs), 2) if len(qs) > 1 else 0.0
        pct_poor = round(sum(1 for q in qs if q < 50.0) / len(qs), 3)

        per_type[t] = {
            "task_type": t,
            "primary_pipeline": _PRIMARY_PIPELINE.get(t, "som"),
            "count": len(qs),
            "tier": _tier_for(avg_q, pct_poor),
            "avg_quality": avg_q,
            "std_quality": std_q,
            "pct_poor": pct_poor,
            "trend": _trend(qs),
            "avg_latency_ms": round(mean(lats), 1) if lats else None,
        }

    # Global summary
    all_qs = [q for qs in type_series.values() for q in qs]
    global_avg = round(mean(all_qs), 2) if all_qs else None

    tier_counts = {"excellent": 0, "good": 0, "fair": 0, "poor": 0, "no_data": 0}
    for entry in per_type.values():
        tier_counts[entry["tier"]] = tier_counts.get(entry["tier"], 0) + 1

    skills_perf = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_total_outcomes": eligibility_summary["n_total_outcomes"],
        "n_eligible_outcomes": len(outcomes),
        "eligibility_summary": eligibility_summary,
        "global_avg_quality": global_avg,
        "tier_summary": tier_counts,
        "per_type": per_type,
    }

    if dry_run:
        print(f"[DRY-RUN] Would write: {SKILLS_PERF}")
    else:
        SKILLS_PERF.write_text(json.dumps(skills_perf, indent=2))
        print(f"Wrote: {SKILLS_PERF}")
    return skills_perf


def print_report(perf: dict) -> None:
    print("\n── Skill Performance Report ──────────────────────")
    print(f"  Total outcomes:  {perf['n_total_outcomes']}")
    print(f"  Eligible outcomes: {perf.get('n_eligible_outcomes', 0)}")
    print(f"  Global avg quality: {perf['global_avg_quality']}")
    tiers = perf.get("tier_summary", {})
    print(f"  Tiers: excellent={tiers.get('excellent',0)}  "
          f"good={tiers.get('good',0)}  "
          f"fair={tiers.get('fair',0)}  "
          f"poor={tiers.get('poor',0)}  "
          f"no_data={tiers.get('no_data',0)}")
    print()
    print(f"  {'Type':<14} {'Tier':<12} {'Avg Q':>6}  {'Pct Poor':>8}  {'Trend':<12}  {'N':>4}  Pipeline")
    print("  " + "-" * 75)
    for t, e in sorted(perf["per_type"].items()):
        avg = f"{e['avg_quality']:.1f}" if e["avg_quality"] is not None else "  —  "
        poor = f"{e['pct_poor']:.0%}" if e["pct_poor"] is not None else "  —  "
        print(f"  {t:<14} {e['tier']:<12} {avg:>6}  {poor:>8}  "
              f"{e['trend']:<12}  {e['count']:>4}  {e['primary_pipeline']}")
    print("─────────────────────────────────────────────────\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MR-ALS Phase 7: Skill Performance Tracker")
    parser.add_argument("--report", action="store_true", help="Print summary table")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing skills_performance.json")
    args = parser.parse_args()
    perf = analyze(dry_run=args.dry_run)
    if args.report:
        print_report(perf)
    else:
        tier_summary = {k: v for k, v in perf["tier_summary"].items() if v > 0}
        print(json.dumps({"n_outcomes": perf["n_total_outcomes"],
                          "global_avg_quality": perf["global_avg_quality"],
                          "tier_summary": tier_summary}, indent=2))


if __name__ == "__main__":
    main()
