import sys
import types
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import mr_als_runner


def test_run_phases_propagates_dry_run_to_mutating_phases(monkeypatch):
    seen = {}

    def fake_shadow_run(*, all_candidates=False, promote=False, dry_run=False, candidate_id=None, baseline_only=False):
        seen["phase5_dry_run"] = dry_run
        return {"candidates": {}}

    def fake_model_run(*, generate=False, report=False, dry_run=False):
        seen["phase6_dry_run"] = dry_run
        return {"recommendations": []}

    def fake_skill_analyze(*, dry_run=False):
        seen["phase7_dry_run"] = dry_run
        return {"tier_summary": {}}

    monkeypatch.setitem(sys.modules, "shadow_eval", types.SimpleNamespace(run=fake_shadow_run))
    monkeypatch.setitem(sys.modules, "model_learner", types.SimpleNamespace(run=fake_model_run))
    monkeypatch.setitem(sys.modules, "skill_learner", types.SimpleNamespace(analyze=fake_skill_analyze))

    results = mr_als_runner.run_phases(phases=[5, 6, 7], dry_run=True)

    assert "error" not in results["phase5"]
    assert "error" not in results["phase6"]
    assert "error" not in results["phase7"]
    assert seen == {
        "phase5_dry_run": True,
        "phase6_dry_run": True,
        "phase7_dry_run": True,
    }
