#!/usr/bin/env python3
"""
mr_als_runner.py — MR-ALS Orchestrator

Runs the full MR-ALS pipeline in sequence:

  Phase 4  → optimize_weights.py   (generate candidate artifacts)
  Phase 5  → shadow_eval.py        (evaluate + gate all candidates)
  Phase 4b → pareto_manager.py     (update Pareto frontier)
  Phase 6  → model_learner.py      (failure pattern analysis)
  Phase 7  → skill_learner.py      (skill performance tracking)
  Phase 8  → plugin_sync.py        (sync STATUS.md + plugin_report.json)

Also handles:
  --promote → auto-promote best passing candidate after phase 5
  --phase N,M → run only specified phases (comma-separated)

Called from two contexts:
  1. CLI: python3 mr_als_runner.py [options]
  2. Threshold trigger: meta_router_executor.py calls run_phases() after N outcomes

Usage:
    python3 mr_als_runner.py                     # full pipeline
    python3 mr_als_runner.py --phase 4,5         # optimizer + shadow eval only
    python3 mr_als_runner.py --bootstrap         # force bootstrap mode for phase 4
    python3 mr_als_runner.py --force             # ignore outcome threshold
    python3 mr_als_runner.py --promote           # promote best candidate after eval
    python3 mr_als_runner.py --dry-run           # simulate, no file writes
    python3 mr_als_runner.py --all-phases        # explicitly run all phases
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
SCRIPTS_DIR = MR_DIR / "scripts"
HERMES_GW = Path("/home/samade10/.hermes/hermes-agent")

# Add scripts dir to path for relative imports within the suite
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(HERMES_GW))


# ── Phase runners ──────────────────────────────────────────────────────────────

def _run_phase4(force: bool, bootstrap: bool, dry_run: bool) -> dict:
    """Phase 4: generate candidate artifacts."""
    try:
        import optimize_weights
        return optimize_weights.run(force=force, bootstrap=bootstrap, dry_run=dry_run)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def _run_phase5(promote: bool, dry_run: bool) -> dict:
    """Phase 5: shadow-evaluate all unevaluated candidates."""
    try:
        import shadow_eval
        # Evaluate all candidate-*.json artifacts
        result = shadow_eval.run(
            all_candidates=True,
            promote=promote,
            dry_run=dry_run,
        )
        return result
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def _run_phase4b(dry_run: bool) -> dict:
    """Phase 4b: update Pareto frontier from evaluated artifacts."""
    try:
        import pareto_manager
        return pareto_manager.rebuild_frontier(dry_run=dry_run)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def _run_phase6(generate: bool, dry_run: bool) -> dict:
    """Phase 6: model failure pattern analysis."""
    try:
        import model_learner
        return model_learner.run(generate=generate, dry_run=dry_run)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def _run_phase7(dry_run: bool) -> dict:
    """Phase 7: skill performance analysis."""
    try:
        import skill_learner
        return skill_learner.analyze(dry_run=dry_run)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def _run_phase8(dry_run: bool) -> dict:
    """Phase 8: sync STATUS.md and plugin report."""
    try:
        import plugin_sync
        return plugin_sync.run(dry_run=dry_run)
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


# ── Public API ─────────────────────────────────────────────────────────────────

def run_phases(
    phases: list[int] | None = None,
    force: bool = False,
    bootstrap: bool = False,
    promote: bool = False,
    dry_run: bool = False,
    generate_model_candidates: bool = False,
) -> dict:
    """
    Run specified pipeline phases.

    Args:
        phases: list of phase numbers to run (default: all)
        force: bypass outcome threshold for phase 4
        bootstrap: force bootstrap mode for phase 4
        promote: auto-promote best passing candidate after phase 5
        dry_run: simulate without writing any files
        generate_model_candidates: write artifacts from phase 6 insights

    Returns dict with per-phase results.
    """
    all_phases = [4, 5, "4b", 6, 7, 8]
    if phases is None:
        phases_to_run = all_phases
    else:
        phases_to_run = phases

    results: dict[str, dict] = {}
    started_at = datetime.now(timezone.utc).isoformat()

    def _log(msg: str):
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}")

    if 4 in phases_to_run:
        _log("Phase 4: optimize_weights — generating candidate artifacts")
        results["phase4"] = _run_phase4(force=force, bootstrap=bootstrap, dry_run=dry_run)
        if "error" in results["phase4"]:
            _log(f"  ERROR: {results['phase4']['error']}")
        else:
            n = len(results["phase4"].get("generated", []))
            _log(f"  Generated {n} candidate(s)")

    if 5 in phases_to_run:
        _log("Phase 5: shadow_eval — evaluating all candidates")
        results["phase5"] = _run_phase5(promote=promote, dry_run=dry_run)
        if "error" in results["phase5"]:
            _log(f"  ERROR: {results['phase5']['error']}")
        else:
            cands = results["phase5"].get("candidates", {})
            passing = sum(1 for c in cands.values() if c.get("gate_passes"))
            _log(f"  Evaluated {len(cands)} candidate(s), {passing} passed gate")

    if "4b" in phases_to_run:
        _log("Phase 4b: pareto_manager — rebuilding Pareto frontier")
        results["phase4b"] = _run_phase4b(dry_run=dry_run)
        if "error" in results["phase4b"]:
            _log(f"  ERROR: {results['phase4b']['error']}")
        else:
            n_f = len(results["phase4b"].get("frontier", []))
            _log(f"  Frontier: {n_f} member(s)")

    if 6 in phases_to_run:
        _log("Phase 6: model_learner — analyzing failure patterns")
        results["phase6"] = _run_phase6(generate=generate_model_candidates, dry_run=dry_run)
        if "error" in results["phase6"]:
            _log(f"  ERROR: {results['phase6']['error']}")
        else:
            n_recs = len(results["phase6"].get("recommendations", []))
            _log(f"  {n_recs} recommendation(s) generated")

    if 7 in phases_to_run:
        _log("Phase 7: skill_learner — updating skill performance")
        results["phase7"] = _run_phase7(dry_run=dry_run)
        if "error" in results["phase7"]:
            _log(f"  ERROR: {results['phase7']['error']}")
        else:
            _log(f"  skills_performance.json updated")

    if 8 in phases_to_run:
        _log("Phase 8: plugin_sync — syncing STATUS.md + plugin_report")
        results["phase8"] = _run_phase8(dry_run=dry_run)
        if "error" in results["phase8"]:
            _log(f"  ERROR: {results['phase8']['error']}")
        else:
            _log("  STATUS.md and plugin_report.json updated")

    results["meta"] = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "phases_run": [str(p) for p in phases_to_run],
        "dry_run": dry_run,
    }

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="MR-ALS Orchestrator")
    parser.add_argument(
        "--phase", metavar="N,M,...",
        help="Comma-separated phase numbers to run (e.g. '4,5' or '6,7,8'). "
             "Use '4b' for Pareto manager. Default: all.",
    )
    parser.add_argument("--all-phases", action="store_true", help="Explicitly run all phases")
    parser.add_argument("--force", action="store_true", help="Ignore outcome threshold for Phase 4")
    parser.add_argument("--bootstrap", action="store_true", help="Force bootstrap mode (Phase 4)")
    parser.add_argument("--promote", action="store_true", help="Auto-promote best passing candidate")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing")
    parser.add_argument("--generate-model-candidates", action="store_true",
                        help="Write candidate artifacts from Phase 6 insights")
    args = parser.parse_args()

    if args.phase:
        raw = [p.strip() for p in args.phase.split(",")]
        phases = []
        for r in raw:
            if r == "4b":
                phases.append("4b")
            elif r.isdigit():
                phases.append(int(r))
        if not phases:
            print("ERROR: no valid phases specified. Use e.g. --phase 4,5 or --phase 4b")
            sys.exit(1)
    else:
        phases = None  # all

    results = run_phases(
        phases=phases,
        force=args.force,
        bootstrap=args.bootstrap,
        promote=args.promote,
        dry_run=args.dry_run,
        generate_model_candidates=args.generate_model_candidates,
    )

    # Print compact summary
    print("\n── Run Summary ────────────────────────────────────")
    for phase_key, result in results.items():
        if phase_key == "meta":
            continue
        status = "ERROR" if "error" in result else "OK"
        print(f"  {phase_key}: {status}")
    print(f"  Finished: {results['meta']['finished_at']}")
    print("─────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
