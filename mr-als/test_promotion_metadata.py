import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import load_active_routing



def test_promote_artifact_records_rollout_metadata(tmp_path, monkeypatch):
    deployment_state = tmp_path / "experience" / "deployment_state.json"
    artifacts_dir = tmp_path / "artifacts"
    deployment_state.parent.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    deployment_state.write_text(
        json.dumps(
            {
                "active_candidate_id": "static-default",
                "previous_candidate_id": None,
                "rollback_available": False,
                "rollback_candidate_id": None,
            }
        )
    )

    monkeypatch.setattr(load_active_routing, "_DEPLOYMENT_STATE", deployment_state)
    monkeypatch.setattr(load_active_routing, "_ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(load_active_routing, "_cached_overrides", None)

    artifact = {
        "candidate_id": "candidate-0002",
        "type_priority": ["code", "audit"],
        "keyword_weight_adjustments": {},
        "confidence_thresholds": {"min_confidence_to_route": 0.0, "high_confidence_threshold": 0.8},
        "metrics": {"shadow_eval_n": 20, "gate_passes": True},
    }

    ok = load_active_routing.promote_artifact(
        "candidate-0002",
        artifact,
        rollout_mode="shadow",
        activation_basis="shadow-eval",
        eligible_outcomes=0,
    )

    assert ok is True
    state = json.loads(deployment_state.read_text())
    assert state["active_candidate_id"] == "candidate-0002"
    assert state["rollout_mode"] == "shadow"
    assert state["activation_basis"] == "shadow-eval"
    assert state["evidence_maturity"] == "shadow-only"
    assert state["eligible_outcomes_at_promotion"] == 0
    assert state["promotion_ready"] is False
    assert state["last_rollout_result"]["status"] == "promoted"
