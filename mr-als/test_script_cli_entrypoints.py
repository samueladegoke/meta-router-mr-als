import subprocess
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"


@pytest.mark.parametrize(
    ("script_name", "args", "expected_fragment"),
    [
        ("shadow_eval.py", ["--baseline"], '"baseline"'),
        ("optimize_weights.py", ["--dry-run"], '"bootstrap_mode"'),
        ("model_learner.py", ["--report"], "Model Learner Report"),
        ("skill_learner.py", ["--report"], "Skill Performance Report"),
        ("plugin_sync.py", ["--dry-run", "--report"], "Plugin Sync Report"),
        ("pareto_manager.py", ["--list"], '"candidate_id"'),
    ],
)
def test_script_entrypoints_run_under_system_python(script_name, args, expected_fragment):
    proc = subprocess.run(
        ["python3", script_name, *args],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    assert proc.returncode == 0, combined
    assert expected_fragment in combined
