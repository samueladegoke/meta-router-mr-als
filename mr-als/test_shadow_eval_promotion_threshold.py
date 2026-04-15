import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import shadow_eval


def test_shadow_eval_live_promotion_requires_50_eligible_outcomes(tmp_path, monkeypatch, capsys):
    artifacts_dir = tmp_path / "artifacts"
    exp_dir = tmp_path / "experience"
    artifacts_dir.mkdir(parents=True)
    exp_dir.mkdir(parents=True)

    monkeypatch.setattr(shadow_eval, "ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr(shadow_eval, "EXP_DIR", exp_dir)

    artifact = {
        "candidate_id": "candidate-0010",
        "metrics": {"shadow_eval_n": 20, "gate_passes": True},
    }
    (artifacts_dir / "candidate-0010.json").write_text(json.dumps(artifact))

    monkeypatch.setattr(shadow_eval, "load_artifact", lambda candidate_id: artifact)

    captured = {}

    def fake_shared_promote(candidate_id, artifact_obj, *, rollout_mode, activation_basis, eligible_outcomes):
        captured["rollout_mode"] = rollout_mode
        captured["activation_basis"] = activation_basis
        captured["eligible_outcomes"] = eligible_outcomes
        return True

    import experience_hygiene as hygiene
    monkeypatch.setattr(hygiene, "read_jsonl", lambda path: [])
    monkeypatch.setattr(hygiene, "build_joined_records", lambda events, outcomes: [])
    monkeypatch.setattr(hygiene, "summarize_learning_dataset", lambda records: {"n_eligible_outcomes": 19})

    import load_active_routing
    monkeypatch.setattr(load_active_routing, "promote_artifact", fake_shared_promote)

    shadow_eval.promote_artifact("candidate-0010")

    assert captured["eligible_outcomes"] == 19
    assert captured["rollout_mode"] == "shadow"
    assert captured["activation_basis"] == "shadow-eval"
