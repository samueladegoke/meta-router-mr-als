#!/usr/bin/env python3
"""
optimize_weights.py — MR-ALS Phase 4: Adaptive Weight Optimizer

Reads routing_outcomes.jsonl and generates candidate routing artifacts
with optimized keyword weight adjustments.

Bootstrap mode (< MIN_OUTCOMES): uses shadow_eval_set.json as the training
proxy via confusion-matrix analysis.

Live mode (>= MIN_OUTCOMES): augments confusion analysis with actual outcome
quality signals from routing_outcomes.jsonl.

Usage:
    python3 optimize_weights.py              # auto-select mode by outcome count
    python3 optimize_weights.py --force      # run regardless of outcome count
    python3 optimize_weights.py --bootstrap  # force bootstrap mode
    python3 optimize_weights.py --dry-run    # print plan, don't write artifacts
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from experience_hygiene import load_joined_records, summarize_learning_dataset, ELIGIBILITY_POLICY_VERSION, MIN_ELIGIBLE_OUTCOMES
from meta_router_rules import load_base_rules

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
ARTIFACTS_DIR = MR_DIR / "artifacts"
EXP_DIR = MR_DIR / "experience"
SHADOW_SET = EXP_DIR / "shadow_eval_set.json"
OUTCOMES_JSONL = EXP_DIR / "routing_outcomes.jsonl"
EVENTS_JSONL = EXP_DIR / "routing_events.jsonl"

MIN_OUTCOMES = MIN_ELIGIBLE_OUTCOMES  # single source of truth in experience_hygiene.py
TYPES = ["code", "audit", "research", "production", "integration", "config", "design"]
TOP_N_CANDIDATES = 3


# ── Shadow set loader ──────────────────────────────────────────────────────────

def _count_outcomes() -> int:
    if not OUTCOMES_JSONL.exists():
        return 0
    return sum(1 for line in OUTCOMES_JSONL.read_text().splitlines() if line.strip())


def _load_learning_records() -> tuple[list[dict], list[dict], dict]:
    joined_records = load_joined_records(EVENTS_JSONL, OUTCOMES_JSONL)
    summary = summarize_learning_dataset(joined_records, min_eligible_outcomes=MIN_OUTCOMES)
    eligible_outcomes = [record for record in joined_records if record.get("eligible_for_learning")]
    return joined_records, eligible_outcomes, summary


def _load_outcomes() -> list[dict]:
    if not OUTCOMES_JSONL.exists():
        return []
    result = []
    for line in OUTCOMES_JSONL.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return result


def _load_events() -> dict[str, dict]:
    """Load routing events keyed by request_id."""
    if not EVENTS_JSONL.exists():
        return {}
    result = {}
    for line in EVENTS_JSONL.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                ev = json.loads(line)
                result[ev.get("request_id", "")] = ev
            except json.JSONDecodeError:
                pass
    return result


# ── Classification helper ──────────────────────────────────────────────────────

def _classify(text: str, rules, weight_adj: dict) -> str:
    """Classify text with weight adjustments. Returns predicted type string."""
    lower = text.lower()
    scores: dict[str, float] = {cat: 0.0 for cat, _ in rules}
    for category, patterns in rules:
        for pattern in patterns:
            if re.search(pattern, lower):
                scores[category] += 1.0

    adjusted = {
        cat: scores[cat] * weight_adj.get(cat, {}).get("weight_multiplier", 1.0)
        for cat in scores
    }
    best = max(adjusted, key=lambda c: adjusted[c])
    return best if adjusted[best] > 0 else "code"


def _eval_on_shadow(weight_adj: dict, shadow_entries: list, rules) -> float:
    """Return accuracy of weight_adj on shadow set."""
    correct = sum(
        1 for e in shadow_entries
        if _classify(e["text"], rules, weight_adj) == e["expected_type"]
    )
    return correct / len(shadow_entries) if shadow_entries else 0.0


def _confusion_matrix(weight_adj: dict, shadow_entries: list, rules) -> dict[str, dict[str, int]]:
    """confusion[expected][predicted] = count."""
    cm: dict[str, dict[str, int]] = {t: {t2: 0 for t2 in TYPES} for t in TYPES}
    for e in shadow_entries:
        pred = _classify(e["text"], rules, weight_adj)
        exp = e["expected_type"]
        if exp in cm and pred in cm[exp]:
            cm[exp][pred] += 1
    return cm


def _baseline_adj() -> dict[str, dict]:
    return {t: {"weight_multiplier": 1.0} for t in TYPES}


# ── Candidate generation strategies ───────────────────────────────────────────

def _confusion_boost(shadow_entries, rules) -> dict[str, dict]:
    """
    For each type that's being mis-predicted, boost its weight and mildly
    reduce the most common wrong prediction's weight.
    """
    adj = _baseline_adj()
    cm = _confusion_matrix(adj, shadow_entries, rules)
    for exp_type in TYPES:
        row = cm[exp_type]
        wrong = [(t, c) for t, c in row.items() if t != exp_type and c > 0]
        if wrong:
            worst_t, _ = max(wrong, key=lambda x: x[1])
            adj[exp_type]["weight_multiplier"] = round(
                min(1.5, adj[exp_type]["weight_multiplier"] + 0.3), 2
            )
            adj[worst_t]["weight_multiplier"] = round(
                max(0.7, adj[worst_t]["weight_multiplier"] - 0.1), 2
            )
    return adj


def _low_acc_boost(shadow_entries, rules) -> dict[str, dict]:
    """Boost worst-performing types proportionally to their accuracy deficit."""
    adj = _baseline_adj()
    cm = _confusion_matrix(adj, shadow_entries, rules)
    type_acc = {}
    for t in TYPES:
        total = sum(cm[t].values())
        type_acc[t] = cm[t].get(t, 0) / total if total > 0 else 1.0

    worst_three = sorted(type_acc.items(), key=lambda x: x[1])[:3]
    for typ, acc in worst_three:
        boost = 1.0 + (1.0 - acc) * 0.8  # up to 1.8x at 0% accuracy
        adj[typ]["weight_multiplier"] = round(min(2.0, boost), 2)
    return adj


def _non_code_nudge() -> dict[str, dict]:
    """
    Nudge all non-code types up +10%.
    Rationale: "code" is the default fallback; nudging others improves discrimination.
    """
    adj = _baseline_adj()
    for t in TYPES:
        if t != "code":
            adj[t]["weight_multiplier"] = 1.1
    return adj


def _audit_prod_premium() -> dict[str, dict]:
    """
    Boost audit and production — they carry the highest consequence if misrouted.
    """
    adj = _baseline_adj()
    adj["audit"]["weight_multiplier"] = 1.5
    adj["production"]["weight_multiplier"] = 1.3
    return adj


def _inverse_acc_scale(shadow_entries, rules) -> dict[str, dict]:
    """Scale weights inversely to per-type accuracy — most confused types get highest boost."""
    adj = _baseline_adj()
    cm = _confusion_matrix(adj, shadow_entries, rules)
    for t in TYPES:
        total = sum(cm[t].values())
        acc = cm[t].get(t, 0) / total if total > 0 else 1.0
        adj[t]["weight_multiplier"] = round(min(2.0, 1.0 / max(acc, 0.3)), 2)
    return adj


def _outcome_quality_boost(outcomes: list) -> dict[str, dict]:
    """
    Live mode: boost types with below-average outcome quality.
    """
    adj = _baseline_adj()
    type_q: dict[str, list[float]] = {t: [] for t in TYPES}
    for o in outcomes:
        tt = o.get("task_type", "code")
        q = o.get("outcome_quality")
        if tt in type_q and q is not None:
            type_q[tt].append(float(q))

    avg_q = {t: sum(qs) / len(qs) if qs else 50.0 for t, qs in type_q.items()}
    overall = sum(avg_q.values()) / len(avg_q)
    for t, avg in avg_q.items():
        if avg < overall:
            deficit = (overall - avg) / overall
            adj[t]["weight_multiplier"] = round(1.0 + deficit * 0.5, 2)
    return adj


# ── Strategy registry ──────────────────────────────────────────────────────────

def _get_strategies(shadow_entries, rules, outcomes=None) -> list[tuple[str, dict]]:
    strategies = [
        ("confusion-boost-v1",        _confusion_boost(shadow_entries, rules)),
        ("low-acc-boost-v1",          _low_acc_boost(shadow_entries, rules)),
        ("non-code-nudge-v1",         _non_code_nudge()),
        ("audit-prod-premium-v1",     _audit_prod_premium()),
        ("inverse-acc-scale-v1",      _inverse_acc_scale(shadow_entries, rules)),
    ]
    if outcomes:
        strategies.insert(0, ("outcome-quality-boost-v1", _outcome_quality_boost(outcomes)))
    return strategies


# ── Artifact I/O ───────────────────────────────────────────────────────────────

def _allocate_ids(n: int) -> list[str]:
    existing = list(ARTIFACTS_DIR.glob("candidate-*.json"))
    nums = [
        int(p.stem.split("-")[1])
        for p in existing
        if len(p.stem.split("-")) == 2 and p.stem.split("-")[1].isdigit()
    ]
    start = (max(nums) + 1) if nums else 1
    return [f"candidate-{start + i:04d}" for i in range(n)]


def _make_artifact(cid: str, strategy: str, weight_adj: dict, shadow_acc: float) -> dict:
    baseline_path = ARTIFACTS_DIR / "baseline-0001.json"
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    type_priority = baseline.get(
        "type_priority",
        ["audit", "design", "research", "production", "integration", "config", "code"],
    )
    return {
        "candidate_id": cid,
        "version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": f"Phase 4 optimizer candidate — strategy: {strategy}",
        "strategy": strategy,
        "keyword_weight_adjustments": weight_adj,
        "confidence_thresholds": {
            "min_confidence_to_route": 0.0,
            "high_confidence_threshold": 0.8,
        },
        "type_priority": type_priority,
        "promoted_at": None,
        "pareto_score": None,
        "metrics": {
            "accuracy_estimate": None,
            "avg_confidence": None,
            "coverage": None,
            "shadow_acc_pretrial": shadow_acc,
        },
        "lineage": {
            "parent_id": "baseline-0001",
            "generation": 1,
            "created_by": "optimize_weights",
        },
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def run(force: bool = False, bootstrap: bool = False, dry_run: bool = False) -> dict:
    """Run Phase 4 optimizer. Returns dict with generated candidate info."""
    rules, _ = load_base_rules()
    shadow_entries = json.loads(SHADOW_SET.read_text())["entries"]
    joined_records, eligible_outcomes, eligibility_summary = _load_learning_records()
    n_outcomes_raw = len(joined_records)
    n_outcomes_eligible = len(eligible_outcomes)
    use_bootstrap = bootstrap or (n_outcomes_eligible < MIN_OUTCOMES)

    print(f"Routing outcomes (raw): {n_outcomes_raw}  (eligible threshold: {MIN_OUTCOMES})")
    print(f"Routing outcomes (eligible): {n_outcomes_eligible}")
    print(f"Mode: {'bootstrap' if use_bootstrap else 'live-data'}")

    if not force and n_outcomes_raw == 0 and not bootstrap:
        print("No outcomes yet — use --bootstrap or --force to run anyway.")
        return {"skipped": True, "reason": "no_outcomes"}

    outcomes = [] if use_bootstrap else eligible_outcomes
    strategies = _get_strategies(shadow_entries, rules, outcomes if outcomes else None)

    # Score each strategy on shadow set
    scored = sorted(
        [(name, adj, _eval_on_shadow(adj, shadow_entries, rules)) for name, adj in strategies],
        key=lambda x: x[2],
        reverse=True,
    )

    print(f"\nTop strategies (shadow set accuracy):")
    for name, _, acc in scored[:5]:
        print(f"  {name:<35} {acc:.3f}")

    # Allocate IDs for top-N and write
    ids = _allocate_ids(TOP_N_CANDIDATES)
    generated = []

    for cid, (name, adj, acc) in zip(ids, scored[:TOP_N_CANDIDATES]):
        artifact = _make_artifact(cid, name, adj, round(acc, 3))
        artifact["training_data"] = {
            "mode": "bootstrap" if use_bootstrap else "live-data",
            "raw_outcomes": n_outcomes_raw,
            "eligible_outcomes": n_outcomes_eligible,
            "eligibility_policy": ELIGIBILITY_POLICY_VERSION,
        }
        if dry_run:
            print(f"  [DRY-RUN] {cid}  strategy={name}  shadow_acc={acc:.3f}")
        else:
            path = ARTIFACTS_DIR / f"{cid}.json"
            path.write_text(json.dumps(artifact, indent=2))
            print(f"  Wrote: {path}")
        generated.append({"candidate_id": cid, "strategy": name, "shadow_acc_pretrial": round(acc, 3)})

    return {
        "generated": generated,
        "bootstrap_mode": use_bootstrap,
        "n_outcomes": n_outcomes_raw,
        "n_outcomes_raw": n_outcomes_raw,
        "n_outcomes_eligible": n_outcomes_eligible,
        "eligibility_summary": eligibility_summary,
        "top_strategy": scored[0][0] if scored else None,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MR-ALS Phase 4: Adaptive Weight Optimizer")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--bootstrap", action="store_true", help="Force bootstrap mode")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force, bootstrap=args.bootstrap, dry_run=args.dry_run)
    print("\n" + json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
