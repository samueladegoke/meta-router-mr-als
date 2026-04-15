import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import reconcile_outcomes


def _task_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def test_reconcile_outcomes_backfills_unique_delivery_match(tmp_path):
    events_path = tmp_path / "routing_events.jsonl"
    outcomes_path = tmp_path / "routing_outcomes.jsonl"
    state_root = tmp_path / "state"

    task = "Write a Python function safe_divide(a, b)."
    events_path.write_text(
        json.dumps(
            {
                "request_id": "rid-1",
                "timestamp": "2026-04-15T10:30:32+00:00",
                "source": "cli",
                "surface": "cli",
                "task_text_hash": _task_hash(task),
                "task_preview": task[:120],
                "task_type": "code",
                "bypassed": False,
            }
        )
        + "\n"
    )
    outcomes_path.write_text(
        json.dumps(
            {
                "request_id": "rid-1",
                "timestamp": "2026-04-15T10:32:37+00:00",
                "task_type": "code",
                "composite_score": 80.2,
                "som_score": 67.0,
                "eop_score": 100.0,
                "oracle_verdict": "PASS",
                "adv_pass_clean": True,
                "latency_ms": 10.0,
                "error": None,
                "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
            }
        )
        + "\n"
    )

    _write_json(
        state_root / "safe-divide-pass" / "delivery.json",
        {
            "task": task,
            "scores": {
                "total_weighted_score": 67,
                "verdict": "ACCEPTABLE",
                "threshold": 65,
            },
            "delivery_gate": {"all_passed": True},
            "ref_entry": {
                "timestamp": "2026-04-15T10:32:37+00:00",
                "task_type": "code",
            },
        },
    )

    result = reconcile_outcomes.reconcile_outcomes(
        events_path=events_path,
        outcomes_path=outcomes_path,
        state_root=state_root,
        dry_run=False,
    )

    updated = [row for row in reconcile_outcomes.read_jsonl(outcomes_path) if row["request_id"] == "rid-1"][0]
    assert result["updated_rows"] == 1
    assert updated["outcome_quality"] == 80.2
    assert updated["delivery_gate_passed"] is True
    assert updated["verdict"] == "ACCEPTABLE"
    assert updated["threshold"] == 65
    assert updated["evidence_valid"] is True
    assert updated["adv_findings_count"] == 0


def test_reconcile_outcomes_skips_ambiguous_delivery_matches(tmp_path):
    events_path = tmp_path / "routing_events.jsonl"
    outcomes_path = tmp_path / "routing_outcomes.jsonl"
    state_root = tmp_path / "state"

    task = "Create a tiny Python multiply(a, b) function."
    events_path.write_text(
        json.dumps(
            {
                "request_id": "rid-ambiguous",
                "timestamp": "2026-04-15T10:51:11+00:00",
                "source": "cli",
                "surface": "cli",
                "task_text_hash": _task_hash(task),
                "task_preview": task[:120],
                "task_type": "code",
                "bypassed": False,
            }
        )
        + "\n"
    )
    outcomes_path.write_text(
        json.dumps(
            {
                "request_id": "rid-ambiguous",
                "timestamp": "2026-04-15T10:52:02+00:00",
                "task_type": "code",
                "composite_score": 76.6,
                "oracle_verdict": "PASS",
                "adv_pass_clean": True,
                "error": None,
                "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
            }
        )
        + "\n"
    )

    for name, ts in [("match-a", "2026-04-15T10:52:00+00:00"), ("match-b", "2026-04-15T10:54:00+00:00")]:
        _write_json(
            state_root / name / "delivery.json",
            {
                "task": task,
                "scores": {
                    "total_weighted_score": 61,
                    "verdict": "NEEDS_WORK",
                    "threshold": 65,
                },
                "delivery_gate": {"all_passed": False},
                "ref_entry": {
                    "timestamp": ts,
                    "task_type": "code",
                },
            },
        )

    result = reconcile_outcomes.reconcile_outcomes(
        events_path=events_path,
        outcomes_path=outcomes_path,
        state_root=state_root,
        dry_run=False,
    )

    updated = reconcile_outcomes.read_jsonl(outcomes_path)[0]
    assert result["updated_rows"] == 0
    assert result["ambiguous_rows"] == 1
    assert "outcome_quality" not in updated
    assert "delivery_gate_passed" not in updated
