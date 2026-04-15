#!/usr/bin/env python3
"""
experience_hygiene.py — shared MR-ALS learning-plane hygiene helpers.

Centralizes provenance partitioning and eligibility decisions for the adaptive
learning plane so optimizer/analytics/status code do not silently learn from
synthetic, bypassed, or outcome-incomplete rows.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

SYNTHETIC_SOURCES = {
    "test",
    "t",
    "e2e-test",
    "e2e-multiplier-test",
}
PRODUCTION_SOURCES = {
    "cli",
    "api",
    "gateway",
    "openclaw-plugin",
}
ELIGIBILITY_POLICY_VERSION = "experience-hygiene-v1"


def _coerce_scalar(value: str) -> Any:
    lower = value.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null" or lower == "none":
        return None
    try:
        if any(ch in lower for ch in (".", "e")):
            return float(value)
        return int(value)
    except ValueError:
        return value.strip()


def classify_source(source: str | None) -> str:
    src = (source or "").strip().lower()
    if src in PRODUCTION_SOURCES:
        return "production"
    if src in SYNTHETIC_SOURCES or "test" in src:
        return "synthetic"
    return "unknown"


def parse_notes_fields(notes: str | None) -> dict[str, Any]:
    if not notes:
        return {}
    fields: dict[str, Any] = {}
    for part in notes.split("|"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if not key:
            continue
        fields[key] = _coerce_scalar(value)
    return fields


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result


def build_joined_records(events: list[dict], outcomes: list[dict]) -> list[dict]:
    events_by_request_id = {
        event.get("request_id", ""): event
        for event in events
        if event.get("request_id")
    }
    records: list[dict] = []
    for outcome in outcomes:
        request_id = outcome.get("request_id")
        event = events_by_request_id.get(request_id, {})
        notes_fields = parse_notes_fields(outcome.get("notes"))
        source_bucket = classify_source(event.get("source"))
        reasons: list[str] = []

        outcome_quality = outcome.get("outcome_quality")
        evidence_valid = outcome.get("evidence_valid")
        if evidence_valid is None:
            evidence_valid = notes_fields.get("evidence_valid")
        delivery_gate_passed = outcome.get("delivery_gate_passed")
        if delivery_gate_passed is None:
            delivery_gate_passed = notes_fields.get("delivery_gate_passed")

        if source_bucket == "synthetic":
            reasons.append("synthetic_source")
        elif source_bucket != "production":
            reasons.append("unknown_source")
        if event.get("bypassed"):
            reasons.append("bypassed")
        if outcome.get("error"):
            reasons.append("error_present")
        if outcome_quality is None:
            reasons.append("missing_outcome_quality")
        if outcome.get("oracle_verdict") != "PASS":
            reasons.append("oracle_not_pass")
        if outcome.get("adv_pass_clean") is False:
            reasons.append("adv_pass_not_clean")
        if delivery_gate_passed is False:
            reasons.append("delivery_gate_failed")
        if evidence_valid is False:
            reasons.append("invalid_evidence")
        som_status = notes_fields.get("som_status")
        if som_status not in (None, "complete"):
            reasons.append("som_not_complete")

        record = dict(outcome)
        record.update({
            "event": event,
            "source": event.get("source"),
            "surface": event.get("surface"),
            "confidence": event.get("confidence"),
            "bypassed": bool(event.get("bypassed")),
            "source_bucket": source_bucket,
            "notes_fields": notes_fields,
            "outcome_quality": outcome_quality,
            "evidence_valid": evidence_valid,
            "delivery_gate_passed": delivery_gate_passed,
            "eligible_for_learning": len(reasons) == 0,
            "ineligible_reasons": reasons,
        })
        records.append(record)
    return records


def summarize_learning_dataset(records: list[dict], *, min_eligible_outcomes: int = 50) -> dict[str, Any]:
    eligible = [record for record in records if record.get("eligible_for_learning")]
    source_buckets = Counter(record.get("source_bucket", "unknown") for record in records)
    reasons = Counter(
        reason
        for record in records
        for reason in record.get("ineligible_reasons", [])
    )
    return {
        "policy_version": ELIGIBILITY_POLICY_VERSION,
        "n_total_outcomes": len(records),
        "n_eligible_outcomes": len(eligible),
        "learning_mode": "live-data" if len(eligible) >= min_eligible_outcomes else "bootstrap",
        "promotion_ready": len(eligible) >= min_eligible_outcomes,
        "min_eligible_outcomes": min_eligible_outcomes,
        "source_buckets": dict(source_buckets),
        "ineligible_reasons": dict(reasons),
    }


def load_joined_records(events_path: Path, outcomes_path: Path) -> list[dict]:
    return build_joined_records(read_jsonl(events_path), read_jsonl(outcomes_path))
