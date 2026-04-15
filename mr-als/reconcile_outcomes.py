#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from experience_hygiene import parse_notes_fields, read_jsonl


def _task_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _delivery_candidates(state_root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in sorted(state_root.glob("*/delivery.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        task = payload.get("task")
        if not task:
            continue
        ref_entry = payload.get("ref_entry") or {}
        ts = _parse_ts(ref_entry.get("timestamp"))
        if ts is None:
            continue
        scores = payload.get("scores") or {}
        delivery_gate = payload.get("delivery_gate") or {}
        candidates.append(
            {
                "path": path,
                "task_hash": _task_hash(task),
                "task_type": ref_entry.get("task_type"),
                "timestamp": ts,
                "delivery_gate_passed": delivery_gate.get("all_passed"),
                "verdict": scores.get("verdict"),
                "threshold": scores.get("threshold"),
            }
        )
    return candidates


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if content:
        content += "\n"
    path.write_text(content)


def reconcile_outcomes(
    *,
    events_path: Path,
    outcomes_path: Path,
    state_root: Path,
    dry_run: bool = False,
    max_window_seconds: int = 300,
) -> dict[str, Any]:
    events = {
        row.get("request_id"): row
        for row in read_jsonl(events_path)
        if row.get("request_id")
    }
    outcomes = read_jsonl(outcomes_path)
    deliveries = _delivery_candidates(state_root)

    updated_rows = 0
    ambiguous_rows = 0
    unmatched_rows = 0
    event_missing_rows = 0
    updated_request_ids: list[str] = []

    for row in outcomes:
        request_id = row.get("request_id")
        if not request_id:
            continue
        if row.get("outcome_quality") is not None and row.get("delivery_gate_passed") is not None and row.get("verdict") is not None and row.get("threshold") is not None:
            continue

        event = events.get(request_id)
        if not event:
            event_missing_rows += 1
            continue

        event_ts = _parse_ts(event.get("timestamp"))
        task_hash = event.get("task_text_hash")
        if not event_ts or not task_hash:
            unmatched_rows += 1
            continue

        matches: list[tuple[float, dict[str, Any]]] = []
        for candidate in deliveries:
            if candidate["task_hash"] != task_hash:
                continue
            if candidate.get("task_type") and candidate.get("task_type") != row.get("task_type"):
                continue
            diff = abs((candidate["timestamp"] - event_ts).total_seconds())
            if diff <= max_window_seconds:
                matches.append((diff, candidate))

        if not matches:
            unmatched_rows += 1
            continue
        if len(matches) != 1:
            ambiguous_rows += 1
            continue

        _, match = matches[0]
        notes_fields = parse_notes_fields(row.get("notes"))
        changed = False

        if row.get("outcome_quality") is None and row.get("composite_score") is not None:
            row["outcome_quality"] = row.get("composite_score")
            changed = True
        if row.get("delivery_gate_passed") is None and match.get("delivery_gate_passed") is not None:
            row["delivery_gate_passed"] = match.get("delivery_gate_passed")
            changed = True
        if row.get("verdict") is None and match.get("verdict") is not None:
            row["verdict"] = match.get("verdict")
            changed = True
        if row.get("threshold") is None and match.get("threshold") is not None:
            row["threshold"] = match.get("threshold")
            changed = True
        if row.get("evidence_valid") is None and "evidence_valid" in notes_fields:
            row["evidence_valid"] = notes_fields["evidence_valid"]
            changed = True
        if row.get("adv_findings_count") is None and "adv_findings" in notes_fields:
            row["adv_findings_count"] = notes_fields["adv_findings"]
            changed = True

        if changed:
            updated_rows += 1
            updated_request_ids.append(request_id)

    if updated_rows and not dry_run:
        _write_jsonl(outcomes_path, outcomes)

    return {
        "updated_rows": updated_rows,
        "ambiguous_rows": ambiguous_rows,
        "unmatched_rows": unmatched_rows,
        "event_missing_rows": event_missing_rows,
        "updated_request_ids": updated_request_ids,
        "dry_run": dry_run,
        "max_window_seconds": max_window_seconds,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing MR-ALS outcome fields from delivery artifacts when the match is unambiguous")
    parser.add_argument("--events", default="/home/samade10/.openclaw/workspace/skills/maintainer/meta-router/experience/routing_events.jsonl")
    parser.add_argument("--outcomes", default="/home/samade10/.openclaw/workspace/skills/maintainer/meta-router/experience/routing_outcomes.jsonl")
    parser.add_argument("--state-root", default="/home/samade10/.openclaw/workspace/rql/state")
    parser.add_argument("--window-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = reconcile_outcomes(
        events_path=Path(args.events),
        outcomes_path=Path(args.outcomes),
        state_root=Path(args.state_root),
        dry_run=args.dry_run,
        max_window_seconds=args.window_seconds,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
