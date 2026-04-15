#!/usr/bin/env python3
"""
shadow_eval.py — MR-ALS Phase 5: Shadow Evaluation & Canary Gate

Evaluates a candidate routing artifact against the held-out shadow_eval_set.json.
Used as the gate before any candidate can be promoted to active routing.

Usage:
    python3 shadow_eval.py --candidate <id>          # evaluate one candidate
    python3 shadow_eval.py --candidate <id> --promote # evaluate + promote if passes
    python3 shadow_eval.py --all                      # evaluate all unevaluated candidates
    python3 shadow_eval.py --baseline                 # re-score baseline for reference
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from meta_router_rules import load_base_rules

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
ARTIFACTS_DIR = MR_DIR / "artifacts"
EXP_DIR = MR_DIR / "experience"
SCRIPTS_DIR = MR_DIR / "scripts"
SHADOW_SET = EXP_DIR / "shadow_eval_set.json"
DEPLOYMENT_STATE = EXP_DIR / "deployment_state.json"

# ── Adjusted classifier ────────────────────────────────────────────────────────

def classify_with_artifact(text: str, artifact: dict) -> dict:
    """
    Classify text applying a candidate artifact's weight adjustments.
    Returns {"type": str, "mode": str, "confidence": float}.
    """
    _RULES, _MODE_RULES = load_base_rules()
    weight_adj = artifact.get("keyword_weight_adjustments", {})
    lower = text.lower()

    # Raw keyword scores
    raw: dict[str, int] = {cat: 0 for cat, _ in _RULES}
    for category, patterns in _RULES:
        for pattern in patterns:
            if re.search(pattern, lower):
                raw[category] += 1

    # Apply multipliers
    adjusted: dict[str, float] = {}
    for cat, score in raw.items():
        mult = weight_adj.get(cat, {}).get("weight_multiplier", 1.0)
        adjusted[cat] = score * mult

    # Type priority tie-breaking
    type_priority = artifact.get("type_priority", list(raw.keys()))

    def sort_key(c: str):
        pri = type_priority.index(c) if c in type_priority else 999
        return (adjusted.get(c, 0.0), -pri)

    best_cat = max(adjusted, key=sort_key) if adjusted else "code"
    best_score = adjusted.get(best_cat, 0.0)

    if best_score <= 0:
        best_cat = "code"
        confidence = 0.5
    else:
        total = sum(adjusted.values()) or 1.0
        confidence = round(best_score / total, 3)

    # Confidence threshold gate
    min_conf = artifact.get("confidence_thresholds", {}).get("min_confidence_to_route", 0.0)
    if confidence < min_conf:
        best_cat = "code"
        confidence = 0.5

    # Mode inference
    mode = "execute"
    for m, patterns in _MODE_RULES[:-1]:
        if any(re.search(p, lower) for p in patterns):
            mode = m
            break

    return {"type": best_cat, "mode": mode, "confidence": confidence}


# ── Shadow evaluation ──────────────────────────────────────────────────────────

def evaluate_artifact(artifact: dict, shadow_entries: list) -> dict:
    """
    Evaluate an artifact against all shadow eval entries.
    Returns metrics dict: accuracy, mode_accuracy, avg_confidence, per_type_accuracy.
    """
    type_results: dict[str, dict] = {}
    correct_type = 0
    correct_mode = 0
    confidences = []

    for entry in shadow_entries:
        text = entry["text"]
        expected_type = entry["expected_type"]
        expected_mode = entry.get("expected_mode", "execute")

        pred = classify_with_artifact(text, artifact)
        predicted_type = pred["type"]
        predicted_mode = pred["mode"]
        confidence = pred["confidence"]

        if expected_type not in type_results:
            type_results[expected_type] = {"total": 0, "correct": 0}
        type_results[expected_type]["total"] += 1

        if predicted_type == expected_type:
            correct_type += 1
            type_results[expected_type]["correct"] += 1
        if predicted_mode == expected_mode:
            correct_mode += 1
        confidences.append(confidence)

    n = len(shadow_entries)
    per_type = {
        t: round(v["correct"] / v["total"], 3) if v["total"] else 0.0
        for t, v in type_results.items()
    }
    return {
        "accuracy": round(correct_type / n, 3) if n else 0.0,
        "mode_accuracy": round(correct_mode / n, 3) if n else 0.0,
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
        "coverage": round(sum(1 for c in confidences if c >= 0.5) / n, 3) if n else 0.0,
        "per_type_accuracy": per_type,
        "n_entries": n,
        "n_correct": correct_type,
    }


def gate_passes(candidate_metrics: dict, baseline_metrics: dict, tolerance: float = 0.0) -> tuple[bool, str]:
    """
    Canary gate: candidate passes if accuracy >= baseline (with optional tolerance).
    Returns (passes: bool, reason: str).
    """
    cand_acc = candidate_metrics["accuracy"]
    base_acc = baseline_metrics["accuracy"]
    cand_conf = candidate_metrics["avg_confidence"]
    base_conf = baseline_metrics["avg_confidence"]

    if cand_acc < base_acc - tolerance:
        return False, f"accuracy {cand_acc:.3f} < baseline {base_acc:.3f} (tolerance={tolerance})"
    if cand_conf < base_conf - 0.05:
        return False, f"avg_confidence {cand_conf:.3f} < baseline {base_conf:.3f} - 0.05"
    return True, f"accuracy {cand_acc:.3f} >= baseline {base_acc:.3f}, confidence {cand_conf:.3f} >= baseline {base_conf:.3f} - 0.05"


# ── Artifact I/O ───────────────────────────────────────────────────────────────

def load_artifact(candidate_id: str) -> dict:
    path = ARTIFACTS_DIR / f"{candidate_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")
    return json.loads(path.read_text())


def save_artifact(artifact: dict) -> None:
    cid = artifact["candidate_id"]
    path = ARTIFACTS_DIR / f"{cid}.json"
    path.write_text(json.dumps(artifact, indent=2))


def promote_artifact(candidate_id: str) -> None:
    """Write candidate_id as active in deployment_state.json."""
    from load_active_routing import promote_artifact as shared_promote_artifact
    from experience_hygiene import MIN_ELIGIBLE_OUTCOMES, build_joined_records, read_jsonl, summarize_learning_dataset

    artifact = load_artifact(candidate_id)
    try:
        events = read_jsonl(EXP_DIR / "routing_events.jsonl")
        outcomes = read_jsonl(EXP_DIR / "routing_outcomes.jsonl")
        records = build_joined_records(events, outcomes)
        n_eligible = summarize_learning_dataset(records).get("n_eligible_outcomes", 0)
    except Exception:
        n_eligible = 0
    is_live = n_eligible >= MIN_ELIGIBLE_OUTCOMES
    ok = shared_promote_artifact(
        candidate_id,
        artifact,
        rollout_mode="live" if is_live else "shadow",
        activation_basis="live-data" if is_live else "shadow-eval",
        eligible_outcomes=n_eligible,
    )
    mode = "live" if is_live else "shadow"
    result = "ok" if ok else "failed"
    print(f"Promoted: {candidate_id} ({result}) [eligible={n_eligible}, mode={mode}]")

def run(candidate_id: Optional[str] = None, promote: bool = False,
        all_candidates: bool = False, baseline_only: bool = False, dry_run: bool = False) -> dict:
    """Run shadow evaluation. Returns results dict."""
    shadow_data = json.loads(SHADOW_SET.read_text())
    entries = shadow_data["entries"]

    # Always evaluate baseline first
    baseline_artifact = load_artifact("baseline-0001")
    baseline_metrics = evaluate_artifact(baseline_artifact, entries)
    print(f"\nBaseline accuracy: {baseline_metrics['accuracy']:.1%}  "
          f"mode: {baseline_metrics['mode_accuracy']:.1%}  "
          f"conf: {baseline_metrics['avg_confidence']:.3f}")

    if baseline_only:
        return {"baseline": baseline_metrics}

    candidates_to_eval: list[str] = []
    if all_candidates:
        candidates_to_eval = [
            p.stem for p in ARTIFACTS_DIR.glob("candidate-*.json")
        ]
    elif candidate_id:
        candidates_to_eval = [candidate_id]

    results = {"baseline": baseline_metrics, "candidates": {}}

    for cid in candidates_to_eval:
        print(f"\nEvaluating: {cid}")
        try:
            artifact = load_artifact(cid)
        except FileNotFoundError as e:
            print(f"  ERROR: {e}")
            results["candidates"][cid] = {"error": str(e)}
            continue

        metrics = evaluate_artifact(artifact, entries)
        passes, reason = gate_passes(metrics, baseline_metrics)

        print(f"  accuracy:      {metrics['accuracy']:.1%}  (baseline: {baseline_metrics['accuracy']:.1%})")
        print(f"  mode_accuracy: {metrics['mode_accuracy']:.1%}")
        print(f"  avg_confidence:{metrics['avg_confidence']:.3f}")
        print(f"  coverage:      {metrics['coverage']:.1%}")
        print(f"  per_type: {metrics['per_type_accuracy']}")
        print(f"  Gate: {'✅ PASS' if passes else '❌ FAIL'}  — {reason}")

        # Update artifact with shadow eval results
        artifact["metrics"] = {
            "accuracy_estimate": metrics["accuracy"],
            "avg_confidence": metrics["avg_confidence"],
            "coverage": metrics["coverage"],
            "mode_accuracy": metrics["mode_accuracy"],
            "per_type_accuracy": metrics["per_type_accuracy"],
            "shadow_eval_n": metrics["n_entries"],
            "gate_passes": passes,
            "gate_reason": reason,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        artifact["pareto_score"] = round(
            0.7 * metrics["accuracy"] + 0.2 * metrics["avg_confidence"] + 0.1 * metrics["coverage"], 4
        )
        if dry_run:
            print(f"  [DRY-RUN] Would update artifact metrics for {cid}")
        else:
            save_artifact(artifact)

        if passes and promote:
            if dry_run:
                print(f"  [DRY-RUN] Would promote: {cid}")
            else:
                promote_artifact(cid)

        results["candidates"][cid] = {
            "metrics": metrics,
            "gate_passes": passes,
            "gate_reason": reason,
            "pareto_score": artifact["pareto_score"],
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="MR-ALS Shadow Evaluation & Canary Gate")
    parser.add_argument("--candidate", help="Candidate ID to evaluate")
    parser.add_argument("--promote", action="store_true", help="Promote candidate if gate passes")
    parser.add_argument("--all", action="store_true", dest="all_candidates",
                        help="Evaluate all candidate-*.json artifacts")
    parser.add_argument("--baseline", action="store_true", help="Only score baseline")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing artifacts or promotions")
    args = parser.parse_args()

    results = run(
        candidate_id=args.candidate,
        promote=args.promote,
        all_candidates=args.all_candidates,
        baseline_only=args.baseline,
        dry_run=args.dry_run,
    )
    print("\n" + json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
