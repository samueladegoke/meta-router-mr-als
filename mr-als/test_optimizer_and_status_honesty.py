import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import optimize_weights
import plugin_sync


RULES = [
    ("code", [r"code", r"python"]),
    ("audit", [r"audit", r"security"]),
    ("research", [r"research", r"compare"]),
    ("production", [r"production", r"incident"]),
    ("integration", [r"integration", r"webhook"]),
    ("config", [r"config", r"nginx"]),
    ("design", [r"design", r"ui"]),
]



def test_optimize_weights_uses_only_eligible_outcomes_for_live_mode(tmp_path, monkeypatch):
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    shadow_set = tmp_path / "shadow_eval_set.json"
    events_path = tmp_path / "routing_events.jsonl"
    outcomes_path = tmp_path / "routing_outcomes.jsonl"

    shadow_set.write_text(
        json.dumps({"entries": [{"text": "write python code", "expected_type": "code"}]})
    )

    synthetic_events = []
    synthetic_outcomes = []
    for idx in range(55):
        request_id = f"rid-{idx}"
        synthetic_events.append(
            {
                "request_id": request_id,
                "source": "e2e-test",
                "surface": "cli",
                "bypassed": False,
                "task_type": "code",
                "confidence": 1.0,
            }
        )
        synthetic_outcomes.append(
            {
                "request_id": request_id,
                "task_type": "code",
                "oracle_verdict": "PASS",
                "adv_pass_clean": True,
                "outcome_quality": 95.0,
                "error": None,
                "notes": "som_status=complete | evidence_valid=true",
            }
        )

    events_path.write_text("\n".join(json.dumps(row) for row in synthetic_events) + "\n")
    outcomes_path.write_text("\n".join(json.dumps(row) for row in synthetic_outcomes) + "\n")

    monkeypatch.setattr(optimize_weights, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(optimize_weights, "SHADOW_SET", shadow_set)
    monkeypatch.setattr(optimize_weights, "EVENTS_JSONL", events_path)
    monkeypatch.setattr(optimize_weights, "OUTCOMES_JSONL", outcomes_path)
    monkeypatch.setattr(optimize_weights, "_load_base_rules", lambda: (RULES, []))

    result = optimize_weights.run(force=True, dry_run=True)

    assert result["bootstrap_mode"] is True
    assert result["n_outcomes_raw"] == 55
    assert result["n_outcomes_eligible"] == 0
    assert result["eligibility_summary"]["promotion_ready"] is False



def test_plugin_sync_flags_learning_as_not_mature_without_eligible_outcomes():
    state = {
        "n_events": 120,
        "n_outcomes": 55,
        "deployment": {
            "active_candidate_id": "candidate-0002",
            "rollout_mode": "shadow",
            "evidence_maturity": "shadow-only",
            "promotion_ready": False,
        },
        "frontier": {"frontier": ["candidate-0002"]},
        "source_counts": {"cli": 90, "e2e-test": 30},
        "openclaw_plugin_loaded": True,
        "has_model_insights": True,
        "has_skills_perf": True,
        "n_candidates": 3,
        "n_evaluated": 3,
        "experience_summary": {
            "n_total_outcomes": 55,
            "n_eligible_outcomes": 0,
            "learning_mode": "bootstrap",
            "promotion_ready": False,
            "ineligible_reasons": {"synthetic_source": 55},
        },
        "meta_router_server_healthy": False,
    }

    flags = plugin_sync._derive_flags(state)

    assert flags["routing_live"] is False
    assert flags["learning_data_live"] is False
    assert flags["learning_data_mature"] is False
    assert flags["promotion_ready"] is False

    status_md = plugin_sync._build_status_md(flags, state)
    assert "eligible outcome-enriched production rows" in status_md
    assert "shadow-only" in status_md
