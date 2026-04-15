#!/usr/bin/env python3
"""
model_learner.py — MR-ALS Phase 6: Model Improvement Learner

Analyzes routing_outcomes.jsonl for systematic failure patterns and
generates actionable improvement insights:

  1. Per-type outcome quality distribution (which routes underperform)
  2. Confidence-quality correlation (does high confidence ↔ good outcome?)
  3. Type confusion analysis on the shadow set
  4. Keyword gap analysis: types that score low need stronger discriminators

Generates:
  - experience/model_insights.json  (findings + recommendations)
  - candidate artifacts tagged with "model-learner" provenance
    (only when --generate is passed)

Usage:
    python3 model_learner.py              # analyze, write model_insights.json
    python3 model_learner.py --generate   # also write improved candidates
    python3 model_learner.py --report     # human-readable report to stdout
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev
from typing import Optional

from experience_hygiene import load_joined_records, summarize_learning_dataset

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
ARTIFACTS_DIR = MR_DIR / "artifacts"
EXP_DIR = MR_DIR / "experience"
SHADOW_SET = EXP_DIR / "shadow_eval_set.json"
OUTCOMES_JSONL = EXP_DIR / "routing_outcomes.jsonl"
EVENTS_JSONL = EXP_DIR / "routing_events.jsonl"
INSIGHTS_FILE = EXP_DIR / "model_insights.json"
HERMES_GW = Path("/home/samade10/.hermes/hermes-agent")

TYPES = ["code", "audit", "research", "production", "integration", "config", "design"]
LOW_QUALITY_THRESHOLD = 50.0   # outcome_quality below this is "poor"
LOW_CONFIDENCE_THRESHOLD = 0.5 # routing confidence below this is "uncertain"


# ── Base rules loader ──────────────────────────────────────────────────────────

def _load_base_rules():
    sys.path.insert(0, str(HERMES_GW))
    from gateway.meta_router import _RULES, _MODE_RULES  # type: ignore[attr-defined]
    return _RULES, _MODE_RULES


# ── JSONL helpers ──────────────────────────────────────────────────────────────

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


# ── Analysis routines ──────────────────────────────────────────────────────────

def _per_type_quality(outcomes: list[dict]) -> dict[str, dict]:
    """
    Group outcomes by task_type.
    Returns per-type: {count, avg_quality, pct_poor, qualities: list}.
    """
    groups: dict[str, list[float]] = {t: [] for t in TYPES}
    for o in outcomes:
        tt = o.get("task_type", "code")
        q = o.get("outcome_quality")
        if tt in groups and q is not None:
            groups[tt].append(float(q))

    result = {}
    for t, qs in groups.items():
        if not qs:
            continue
        result[t] = {
            "count": len(qs),
            "avg_quality": round(mean(qs), 2),
            "std_quality": round(stdev(qs), 2) if len(qs) > 1 else 0.0,
            "pct_poor": round(sum(1 for q in qs if q < LOW_QUALITY_THRESHOLD) / len(qs), 3),
            "min_quality": round(min(qs), 2),
            "max_quality": round(max(qs), 2),
        }
    return result


def _confidence_quality_pairs(outcomes: list[dict], events: dict[str, dict]) -> list[dict]:
    """Join outcomes with events on request_id to get (confidence, quality) pairs."""
    pairs = []
    for o in outcomes:
        rid = o.get("request_id")
        ev = events.get(rid, {})
        conf = ev.get("confidence")
        q = o.get("outcome_quality")
        if conf is not None and q is not None:
            pairs.append({
                "request_id": rid,
                "task_type": o.get("task_type"),
                "confidence": float(conf),
                "quality": float(q),
            })
    return pairs


def _conf_quality_correlation(pairs: list[dict]) -> Optional[float]:
    """Pearson r between confidence and quality. Returns None if < 3 pairs."""
    if len(pairs) < 3:
        return None
    xs = [p["confidence"] for p in pairs]
    ys = [p["quality"] for p in pairs]
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = (sum((x - mx) ** 2 for x in xs)) ** 0.5
    den_y = (sum((y - my) ** 2 for y in ys)) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 3)


def _confusion_analysis(shadow_entries: list, rules) -> dict[str, dict]:
    """
    Run baseline weights on shadow set.
    Returns per-type accuracy + main confusion target.
    """
    type_stats: dict[str, dict] = {t: {"total": 0, "correct": 0, "confused_with": {}} for t in TYPES}

    for entry in shadow_entries:
        exp = entry["expected_type"]
        lower = entry["text"].lower()
        scores = {cat: 0 for cat, _ in rules}
        for cat, patterns in rules:
            for p in patterns:
                if re.search(p, lower):
                    scores[cat] += 1
        pred = max(scores, key=lambda c: scores[c]) if max(scores.values()) > 0 else "code"

        if exp in type_stats:
            type_stats[exp]["total"] += 1
            if pred == exp:
                type_stats[exp]["correct"] += 1
            else:
                type_stats[exp]["confused_with"][pred] = (
                    type_stats[exp]["confused_with"].get(pred, 0) + 1
                )

    result = {}
    for t, s in type_stats.items():
        if s["total"] == 0:
            continue
        top_confusion = (
            max(s["confused_with"].items(), key=lambda x: x[1])
            if s["confused_with"]
            else None
        )
        result[t] = {
            "accuracy": round(s["correct"] / s["total"], 3),
            "total": s["total"],
            "main_confusion": top_confusion[0] if top_confusion else None,
            "confusion_count": top_confusion[1] if top_confusion else 0,
        }
    return result


def _keyword_coverage(rules) -> dict[str, int]:
    """Count how many keyword patterns each type has."""
    return {cat: len(patterns) for cat, patterns in rules}


def _build_recommendations(
    type_quality: dict,
    confusion: dict,
    kw_coverage: dict,
) -> list[dict]:
    """
    Synthesize observations into ranked recommendations.
    """
    recs = []

    for t in TYPES:
        cq = confusion.get(t, {})
        tq = type_quality.get(t, {})
        acc = cq.get("accuracy", 1.0)
        pct_poor = tq.get("pct_poor", 0.0)
        main_conf = cq.get("main_confusion")
        n_kw = kw_coverage.get(t, 0)

        if acc < 0.7:
            recs.append({
                "priority": "HIGH",
                "type": t,
                "finding": f"Low shadow-set accuracy ({acc:.0%}) — frequently confused with '{main_conf}'",
                "recommendation": f"Add discriminating keywords for '{t}'; review overlap with '{main_conf}'",
                "action": "keyword_expansion",
            })
        if pct_poor > 0.3 and tq.get("count", 0) >= 3:
            recs.append({
                "priority": "HIGH",
                "type": t,
                "finding": f"{pct_poor:.0%} of '{t}' outcomes scored below {LOW_QUALITY_THRESHOLD}",
                "recommendation": f"'{t}' tasks are poorly served; consider improving routing pipeline or skill coverage",
                "action": "pipeline_review",
            })
        if n_kw < 3:
            recs.append({
                "priority": "MEDIUM",
                "type": t,
                "finding": f"Only {n_kw} keyword pattern(s) for '{t}'",
                "recommendation": f"Expand keyword coverage for '{t}' to improve recall",
                "action": "keyword_expansion",
            })

    # Sort: HIGH before MEDIUM
    recs.sort(key=lambda r: (0 if r["priority"] == "HIGH" else 1, r["type"]))
    return recs


# ── Candidate generation (Phase 6 improvement artifacts) ─────────────────────

def _generate_model_candidates(confusion: dict, type_quality: dict) -> list[dict]:
    """
    Generate weight adjustment candidates based on model insights.
    Returns list of (strategy_name, weight_adj) tuples.
    """
    from optimize_weights import _baseline_adj  # reuse baseline builder

    # Strategy: combined quality + accuracy signal
    adj = _baseline_adj()
    for t in TYPES:
        acc = confusion.get(t, {}).get("accuracy", 1.0)
        pct_poor = type_quality.get(t, {}).get("pct_poor", 0.0)
        # Both low accuracy AND poor quality → max boost
        if acc < 0.7 and pct_poor > 0.3:
            adj[t]["weight_multiplier"] = 1.8
        elif acc < 0.7:
            adj[t]["weight_multiplier"] = 1.4
        elif pct_poor > 0.3:
            adj[t]["weight_multiplier"] = 1.2

    return [("model-learner-combined-v1", adj)]


def _write_model_candidate(strategy: str, weight_adj: dict) -> str:
    """Write a model-learner candidate artifact. Returns candidate_id."""
    existing = list(ARTIFACTS_DIR.glob("candidate-*.json"))
    nums = [
        int(p.stem.split("-")[1])
        for p in existing
        if len(p.stem.split("-")) == 2 and p.stem.split("-")[1].isdigit()
    ]
    next_num = (max(nums) + 1) if nums else 1
    cid = f"candidate-{next_num:04d}"

    baseline = json.loads((ARTIFACTS_DIR / "baseline-0001.json").read_text())
    artifact = {
        "candidate_id": cid,
        "version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": f"Phase 6 model-learner candidate — {strategy}",
        "strategy": strategy,
        "keyword_weight_adjustments": weight_adj,
        "confidence_thresholds": baseline.get("confidence_thresholds", {
            "min_confidence_to_route": 0.0,
            "high_confidence_threshold": 0.8,
        }),
        "type_priority": baseline.get("type_priority", TYPES),
        "promoted_at": None,
        "pareto_score": None,
        "metrics": {"accuracy_estimate": None, "avg_confidence": None, "coverage": None},
        "lineage": {
            "parent_id": "baseline-0001",
            "generation": 1,
            "created_by": "model_learner",
        },
    }
    path = ARTIFACTS_DIR / f"{cid}.json"
    path.write_text(json.dumps(artifact, indent=2))
    return cid


# ── Main ───────────────────────────────────────────────────────────────────────

def run(generate: bool = False, report: bool = False) -> dict:
    """
    Run Phase 6 analysis. Returns insights dict.
    Writes experience/model_insights.json.
    Writes candidate artifact(s) if generate=True.
    """
    rules, _ = _load_base_rules()
    shadow_entries = json.loads(SHADOW_SET.read_text())["entries"]
    joined_records = load_joined_records(EVENTS_JSONL, OUTCOMES_JSONL)
    eligibility_summary = summarize_learning_dataset(joined_records, min_eligible_outcomes=50)
    outcomes = [record for record in joined_records if record.get("eligible_for_learning")]
    events = {record.get("request_id", ""): record for record in outcomes}

    type_quality = _per_type_quality(outcomes)
    pairs = _confidence_quality_pairs(outcomes, events)
    conf_q_corr = _conf_quality_correlation(pairs)
    confusion = _confusion_analysis(shadow_entries, rules)
    kw_coverage = _keyword_coverage(rules)
    recommendations = _build_recommendations(type_quality, confusion, kw_coverage)

    generated_candidates = []
    if generate and outcomes:
        cands = _generate_model_candidates(confusion, type_quality)
        for strategy, adj in cands:
            cid = _write_model_candidate(strategy, adj)
            generated_candidates.append(cid)
            print(f"  [model-learner] wrote candidate: {cid} ({strategy})")

    insights = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_outcomes": eligibility_summary["n_total_outcomes"],
        "n_eligible_outcomes": len(outcomes),
        "n_events": len(_read_jsonl(EVENTS_JSONL)),
        "shadow_set_size": len(shadow_entries),
        "eligibility_summary": eligibility_summary,
        "conf_quality_correlation": conf_q_corr,
        "correlation_interpretation": (
            "insufficient eligible outcome-enriched production data"
            if conf_q_corr is None and len(pairs) < 3
            else (
                "positive (confident routing → better outcomes)"
                if (conf_q_corr or 0) > 0.3
                else "weak/negative (confidence not a reliable quality predictor)"
            )
        ),
        "per_type_quality": type_quality,
        "shadow_confusion": confusion,
        "keyword_coverage": kw_coverage,
        "recommendations": recommendations,
        "generated_candidates": generated_candidates,
    }

    INSIGHTS_FILE.write_text(json.dumps(insights, indent=2))
    print(f"Wrote: {INSIGHTS_FILE}")

    if report:
        _print_report(insights)

    return insights


def _print_report(insights: dict) -> None:
    print("\n── Model Learner Report ─────────────────────────")
    print(f"  Outcomes analyzed:    {insights['n_outcomes']}")
    print(f"  Eligible outcomes:    {insights.get('n_eligible_outcomes', 0)}")
    print(f"  Conf↔Quality r:       {insights['conf_quality_correlation']}")
    print(f"  {insights['correlation_interpretation']}")
    print("\n  Shadow-set confusion:")
    for t, s in sorted(insights["shadow_confusion"].items()):
        acc = s.get("accuracy", 0)
        mc = s.get("main_confusion", "—")
        print(f"    {t:<14} acc={acc:.0%}  confused_with={mc}")
    print("\n  Recommendations:")
    for r in insights["recommendations"]:
        print(f"    [{r['priority']}] {r['type']}: {r['finding']}")
    print("─────────────────────────────────────────────────\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MR-ALS Phase 6: Model Improvement Learner")
    parser.add_argument("--generate", action="store_true", help="Write improved candidate artifacts")
    parser.add_argument("--report", action="store_true", help="Print human-readable report")
    args = parser.parse_args()
    result = run(generate=args.generate, report=args.report)
    if not args.report:
        print("\n" + json.dumps({"recommendations": result["recommendations"],
                                  "n_outcomes": result["n_outcomes"]}, indent=2))


if __name__ == "__main__":
    main()
