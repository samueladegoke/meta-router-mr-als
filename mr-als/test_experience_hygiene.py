import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import experience_hygiene as hygiene


def test_classify_source_distinguishes_production_from_synthetic():
    assert hygiene.classify_source("cli") == "production"
    assert hygiene.classify_source("api") == "production"
    assert hygiene.classify_source("openclaw-plugin") == "production"
    assert hygiene.classify_source("gateway") == "production"

    for source in ["test", "t", "e2e-test", "e2e-multiplier-test"]:
        assert hygiene.classify_source(source) == "synthetic"



def test_parse_notes_fields_coerces_scalars():
    fields = hygiene.parse_notes_fields(
        "som_status=complete | evidence_valid=true | adv_findings=2 | score=61.5 | label=ok"
    )

    assert fields["som_status"] == "complete"
    assert fields["evidence_valid"] is True
    assert fields["adv_findings"] == 2
    assert fields["score"] == 61.5
    assert fields["label"] == "ok"



def test_build_joined_records_and_summary_filter_synthetic_rows():
    events = [
        {
            "request_id": "rid-prod",
            "source": "cli",
            "surface": "cli",
            "bypassed": False,
            "task_type": "code",
            "confidence": 0.9,
        },
        {
            "request_id": "rid-test",
            "source": "e2e-test",
            "surface": "cli",
            "bypassed": False,
            "task_type": "code",
            "confidence": 0.9,
        },
    ]
    outcomes = [
        {
            "request_id": "rid-prod",
            "task_type": "code",
            "oracle_verdict": "PASS",
            "adv_pass_clean": True,
            "delivery_gate_passed": True,
            "outcome_quality": 88.0,
            "error": None,
            "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
        },
        {
            "request_id": "rid-test",
            "task_type": "code",
            "oracle_verdict": "PASS",
            "adv_pass_clean": True,
            "delivery_gate_passed": True,
            "outcome_quality": 91.0,
            "error": None,
            "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
        },
    ]

    records = hygiene.build_joined_records(events, outcomes)
    eligible = [record for record in records if record["eligible_for_learning"]]

    assert [record["request_id"] for record in eligible] == ["rid-prod"]
    assert records[1]["source_bucket"] == "synthetic"
    assert "synthetic_source" in records[1]["ineligible_reasons"]

    summary = hygiene.summarize_learning_dataset(records, min_eligible_outcomes=50)
    assert summary["n_total_outcomes"] == 2
    assert summary["n_eligible_outcomes"] == 1
    assert summary["promotion_ready"] is False
    assert summary["learning_mode"] == "bootstrap"
    assert summary["ineligible_reasons"]["synthetic_source"] == 1



def test_delivery_gate_failure_blocks_learning_eligibility_even_with_pass_pass():
    events = [
        {
            "request_id": "rid-threshold",
            "source": "cli",
            "surface": "cli",
            "bypassed": False,
            "task_type": "code",
            "confidence": 1.0,
        }
    ]
    outcomes = [
        {
            "request_id": "rid-threshold",
            "task_type": "code",
            "oracle_verdict": "PASS",
            "adv_pass_clean": True,
            "delivery_gate_passed": False,
            "outcome_quality": 78.4,
            "error": None,
            "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
        }
    ]

    records = hygiene.build_joined_records(events, outcomes)

    assert records[0]["eligible_for_learning"] is False
    assert "delivery_gate_failed" in records[0]["ineligible_reasons"]


def test_default_learning_maturity_threshold_is_15():
    # Threshold is 15 by design — see references/THRESHOLD_POLICY.md
    # and the rationale comment on MIN_ELIGIBLE_OUTCOMES in experience_hygiene.py.
    summary = hygiene.summarize_learning_dataset([])
    assert summary["min_eligible_outcomes"] == 15
    assert summary["promotion_ready"] is False



def test_build_joined_records_uses_llm_outcome_quality_fallback(monkeypatch):
    events = [
        {
            "request_id": "rid-llm",
            "source": "cli",
            "surface": "cli",
            "bypassed": False,
            "task_type": "code",
            "confidence": 0.7,
        }
    ]
    outcomes = [
        {
            "request_id": "rid-llm",
            "task_type": "code",
            "task_text": "Implement the merge workflow",
            "response_excerpt": "I updated the branch, resolved the conflict, and ran the tests.",
            "oracle_verdict": "PASS",
            "adv_pass_clean": True,
            "delivery_gate_passed": True,
            "error": None,
            "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
        }
    ]
    calls = []

    def fake_llm_score(task_text, response_excerpt, task_type):
        calls.append((task_text, response_excerpt, task_type))
        return 83.5

    monkeypatch.setattr(hygiene, "llm_score_outcome", fake_llm_score, raising=False)

    records = hygiene.build_joined_records(events, outcomes)

    assert calls == [
        (
            "Implement the merge workflow",
            "I updated the branch, resolved the conflict, and ran the tests.",
            "code",
        )
    ]
    assert records[0]["outcome_quality"] == 83.5
    assert records[0]["outcome_quality_source"] == "llm-fallback"
    assert records[0]["eligible_for_learning"] is True



def test_build_joined_records_keeps_missing_outcome_quality_when_llm_fails(monkeypatch):
    events = [
        {
            "request_id": "rid-llm-fail",
            "source": "cli",
            "surface": "cli",
            "bypassed": False,
            "task_type": "code",
            "confidence": 0.7,
        }
    ]
    outcomes = [
        {
            "request_id": "rid-llm-fail",
            "task_type": "code",
            "task_text": "Implement the merge workflow",
            "response_excerpt": "I updated the branch, resolved the conflict, and ran the tests.",
            "oracle_verdict": "PASS",
            "adv_pass_clean": True,
            "delivery_gate_passed": True,
            "error": None,
            "notes": "som_status=complete | evidence_valid=true | adv_findings=0",
        }
    ]

    monkeypatch.setattr(hygiene, "llm_score_outcome", lambda *args, **kwargs: None, raising=False)

    records = hygiene.build_joined_records(events, outcomes)

    assert records[0]["outcome_quality"] is None
    assert "missing_outcome_quality" in records[0]["ineligible_reasons"]
    assert records[0]["eligible_for_learning"] is False
