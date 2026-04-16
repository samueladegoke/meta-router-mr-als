#!/usr/bin/env python3
"""
plugin_sync.py — MR-ALS Phase 8: Plugin State Sync

Reads live state from the MR-ALS experience plane and updates:
  1. STATUS.md — runtime flag YAML + phase progress table
  2. experience/plugin_report.json — machine-readable state summary for
     OpenClaw plugin integration

State sources:
  routing_events.jsonl    → Phase 1 health
  routing_outcomes.jsonl  → Phase 2 health
  deployment_state.json   → Phase 3 state
  artifacts/*.json        → Phase 4/5 state
  pareto_frontier.json    → Phase 4b state
  model_insights.json     → Phase 6 state
  skills_performance.json → Phase 7 state

Usage:
    python3 plugin_sync.py              # sync status + write report
    python3 plugin_sync.py --dry-run    # print proposed changes, don't write
    python3 plugin_sync.py --report     # also print human-readable summary
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from experience_hygiene import MIN_ELIGIBLE_OUTCOMES, load_joined_records, summarize_learning_dataset

MR_DIR = Path("/home/samade10/.openclaw/workspace/skills/maintainer/meta-router")
ARTIFACTS_DIR = MR_DIR / "artifacts"
EXP_DIR = MR_DIR / "experience"
STATUS_MD = MR_DIR / "STATUS.md"
PLUGIN_REPORT = EXP_DIR / "plugin_report.json"
DEPLOYMENT_STATE = EXP_DIR / "deployment_state.json"
PARETO_FRONTIER = EXP_DIR / "pareto_frontier.json"
EVENTS_JSONL = EXP_DIR / "routing_events.jsonl"
OUTCOMES_JSONL = EXP_DIR / "routing_outcomes.jsonl"
MODEL_INSIGHTS = EXP_DIR / "model_insights.json"
SKILLS_PERF = EXP_DIR / "skills_performance.json"


# ── State readers ──────────────────────────────────────────────────────────────

def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _jsonl_source_counts(path: Path) -> dict[str, int]:
    """Return per-source counts from a JSONL event stream."""
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        source = obj.get("source")
        if source:
            counts[source] = counts.get(source, 0) + 1
    return counts


def _jsonl_routed_source_count(path: Path, source_name: str) -> int:
    """Return count of non-bypassed rows for a specific source."""
    if not path.exists():
        return 0
    count = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("source") != source_name:
            continue
        if obj.get("bypassed"):
            continue
        count += 1
    return count


def _openclaw_plugin_loaded() -> bool:
    """Return True when OpenClaw reports the meta-router plugin as loaded.

    OpenClaw's plugin inspect output is TTY-sensitive on this machine. A plain
    subprocess capture can hang or return only early bootstrap logs. Use
    `script` to allocate a pseudo-terminal first, then fall back to a direct
    subprocess if needed.
    """
    commands = [
        ["script", "-q", "-c", "openclaw plugins inspect meta-router", "/dev/null"],
        ["openclaw", "plugins", "inspect", "meta-router"],
    ]
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except Exception:
            continue
        combined = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
        if proc.returncode == 0 and "Status: loaded" in combined:
            return True
    return False


def _meta_router_server_healthy() -> bool:
    try:
        with urlopen("http://127.0.0.1:3120/health", timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") != "ok":
                return False
    except (URLError, TimeoutError, ValueError, OSError):
        return False

    try:
        req = Request(
            "http://127.0.0.1:3120/classify",
            data=json.dumps({"text": "ok", "source": "plugin-sync", "surface": "healthcheck"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        return False

    required_keys = {
        "request_id",
        "type",
        "mode",
        "confidence",
        "directive",
        "text_with_directive",
        "primary",
        "budget_multiplier",
        "routing_artifact_version",
        "bypassed",
        "bypass_reason",
    }
    if not required_keys.issubset(payload):
        return False
    if payload.get("bypassed") is not True:
        return False
    if payload.get("bypass_reason") != "short-ack":
        return False
    if payload.get("directive") != "":
        return False
    if payload.get("text_with_directive") != "ok":
        return False
    return True


def _count_candidates() -> tuple[int, int]:
    """Returns (total_candidates, evaluated_candidates)."""
    cands = list(ARTIFACTS_DIR.glob("candidate-*.json"))
    evaluated = 0
    for p in cands:
        art = json.loads(p.read_text())
        if art.get("metrics", {}).get("accuracy_estimate") is not None:
            evaluated += 1
    return len(cands), evaluated


def _best_passing_candidate() -> dict | None:
    """Return best passing candidate artifact dict, or None."""
    for p in sorted(ARTIFACTS_DIR.glob("candidate-*.json"), key=lambda x: x.name):
        art = json.loads(p.read_text())
        if art.get("metrics", {}).get("gate_passes"):
            return art
    return None


# ── Flags derivation ───────────────────────────────────────────────────────────

def _derive_flags(state: dict) -> dict[str, bool]:
    """Derive runtime flag values from observed state."""
    n_events = state["n_events"]
    n_outcomes = state["n_outcomes"]
    deploy = state["deployment"]
    frontier = state["frontier"]
    n_cands, n_eval = state["n_candidates"], state["n_evaluated"]
    has_insights = state["has_model_insights"]
    has_skills = state["has_skills_perf"]
    plugin_loaded = state["openclaw_plugin_loaded"]
    source_counts = state["source_counts"]
    experience_summary = state.get("experience_summary", {})
    meta_router_server_healthy = state.get("meta_router_server_healthy", False)

    active = deploy.get("active_candidate_id", "static-default")
    openclaw_plugin_events = source_counts.get("openclaw-plugin", 0)
    openclaw_plugin_routed_rows = state.get("openclaw_plugin_routed_rows", 0)
    eligible_outcomes = experience_summary.get("n_eligible_outcomes", 0)

    return {
        "routing_live": meta_router_server_healthy,
        "enforcement_live": meta_router_server_healthy,
        "experience_logging_live": n_events > 0,
        "outcome_enrichment_live": n_outcomes > 0,
        "learning_data_live": eligible_outcomes > 0,
        "learning_data_mature": experience_summary.get("promotion_ready", False),
        "deployment_artifact_live": active not in (None, "static-default"),
        "optimizer_live": n_cands > 0,
        "pareto_frontier_live": len(frontier.get("frontier", [])) > 0,
        "shadow_eval_live": n_eval > 0,
        "model_learning_live": has_insights,
        "skill_learning_live": has_skills,
        "promotion_ready": bool(deploy.get("promotion_ready", False)) and experience_summary.get("promotion_ready", False),
        "openclaw_plugin_loaded": plugin_loaded,
        "openclaw_shared_stream_live": openclaw_plugin_routed_rows > 0,
    }


# ── STATUS.md writer ───────────────────────────────────────────────────────────

def _phase_status(flags: dict, state: dict) -> list[tuple[str, str, str]]:
    """Return rows: (phase_num, phase_name, status_icon)."""
    n_eval = state["n_evaluated"]
    active = state["deployment"].get("active_candidate_id", "static-default")
    plugin_loaded = flags["openclaw_plugin_loaded"]
    shared_stream_live = flags["openclaw_shared_stream_live"]
    experience_summary = state.get("experience_summary", {})
    eligible_outcomes = experience_summary.get("n_eligible_outcomes", 0)
    min_eligible = experience_summary.get("min_eligible_outcomes", 50)

    rows = [
        ("0", "Status Reset",             "✅ Done (2026-04-14)"),
        ("1", "Unified Experience Plane",  "✅ Live" if flags["experience_logging_live"] else "🔄 In progress"),
        ("2", "Outcome Enrichment",        "✅ Live" if flags["outcome_enrichment_live"] else "❌ Not started"),
        ("3", "Deployable Routing Artifact",
              f"✅ Active ({active})" if flags["deployment_artifact_live"] else "🔄 Baseline only"),
        ("4", "Real Optimizer Loop",
              f"✅ Eligible data ready ({eligible_outcomes})" if flags["learning_data_mature"] else f"🟡 Bootstrap only ({eligible_outcomes}/{min_eligible} eligible)"),
        ("5", "Shadow/Canary Gate",
              f"✅ {n_eval} evaluated" if n_eval > 0 else "❌ Not started"),
        ("6", "Model Learning Loop",       "✅ Trustworthy" if flags["learning_data_live"] else "🟡 Artifact only / insufficient eligible data"),
        ("7", "Skill Learning Loop",       "✅ Trustworthy" if flags["learning_data_live"] else "🟡 Artifact only / insufficient eligible data"),
        (
            "8",
            "OpenClaw Plugin Reality Fix",
            "✅ Loaded + shared-stream live" if shared_stream_live else (
                "🟡 Plugin loaded, shared-stream pending" if plugin_loaded else "❌ Plugin not loaded"
            ),
        ),
    ]
    return rows


def _build_status_md(flags: dict, state: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n_ev = state["n_events"]
    n_out = state["n_outcomes"]
    deploy = state["deployment"]
    active = deploy.get("active_candidate_id", "static-default")
    n_cands = state["n_candidates"]
    n_eval = state["n_evaluated"]
    frontier_ids = state["frontier"].get("frontier", [])
    plugin_loaded = flags["openclaw_plugin_loaded"]
    source_counts = state["source_counts"]
    openclaw_plugin_events = source_counts.get("openclaw-plugin", 0)
    openclaw_plugin_routed_rows = state.get("openclaw_plugin_routed_rows", 0)
    experience_summary = state.get("experience_summary", {})
    eligible_outcomes = experience_summary.get("n_eligible_outcomes", 0)
    min_eligible = experience_summary.get("min_eligible_outcomes", 50)
    evidence_maturity = deploy.get("evidence_maturity", "unknown")
    rollout_mode = deploy.get("rollout_mode", "unknown")

    flag_lines = "\n".join(f"  {k}: {str(v).lower()}" for k, v in flags.items())

    live_rows = []
    if flags["routing_live"]:
        live_rows.append("| Hermes meta-router server | ✅ LIVE | /health returned status=ok and /classify matched the current bypass contract on :3120 |")
    if plugin_loaded:
        live_rows.append("| OpenClaw meta-router plugin package | ✅ LIVE | openclaw plugins inspect meta-router -> Status: loaded |")
    if flags["experience_logging_live"]:
        live_rows.append(f"| routing_events.jsonl | ✅ LIVE | {n_ev} events logged |")
    if flags["outcome_enrichment_live"]:
        live_rows.append(f"| routing_outcomes.jsonl | ✅ LIVE | {n_out} outcomes logged (eligible: {eligible_outcomes}) |")
    if flags["deployment_artifact_live"]:
        live_rows.append(
            f"| Adaptive routing artifact | ✅ ACTIVE | active: {active} | rollout_mode={rollout_mode}; evidence_maturity={evidence_maturity} |"
        )
    if flags["pareto_frontier_live"]:
        live_rows.append(f"| Pareto frontier | ✅ LIVE | {len(frontier_ids)} member(s) |")
    if flags["model_learning_live"]:
        live_rows.append("| Model insights artifact generation | ✅ LIVE | model_insights.json written |")
    if flags["skill_learning_live"]:
        live_rows.append("| Skill performance artifact generation | ✅ LIVE | skills_performance.json written |")

    not_live_rows = []
    if not flags["routing_live"]:
        not_live_rows.append("| Hermes meta-router server | Phase 1 | /health or /classify contract is not currently healthy on :3120 |")
    if eligible_outcomes < min_eligible:
        not_live_rows.append(
            f"| Adaptive-learning-ready dataset | Phase 4-7 | {eligible_outcomes} eligible outcome-enriched production rows (minimum {min_eligible}) |"
        )
    if not flags["promotion_ready"]:
        not_live_rows.append(
            f"| Promotion readiness | Phase 3-5 | rollout_mode={rollout_mode}; evidence_maturity={evidence_maturity}; promotion_ready=false |"
        )
    if not flags["openclaw_shared_stream_live"]:
        if plugin_loaded:
            not_live_rows.append(
                f"| OpenClaw shared ALS stream parity | Phase 8 | Plugin package is loaded, but routing_events.jsonl has {openclaw_plugin_routed_rows} routed `openclaw-plugin` rows ({openclaw_plugin_events} total rows) |"
            )
        else:
            not_live_rows.append("| OpenClaw meta-router plugin package | Phase 8 | openclaw plugins inspect meta-router does not report Status: loaded |")

    phase_rows = _phase_status(flags, state)
    phase_table = "\n".join(
        f"| {r[0]} | {r[1]} | {r[2]} |"
        for r in phase_rows
    )

    live_table = "\n".join(f"| {r}" if not r.startswith("|") else r for r in live_rows) if live_rows else "_No live components verified._"
    not_live_table = "\n".join(r for r in not_live_rows) if not_live_rows else "_All gaps closed._"

    return f"""---
generated: {now}
source_of_truth: true
auto_generated: true
---

# Meta-Router ALS — Runtime Status

> **This file is the canonical source of truth for MR-ALS live status.**
> Auto-generated by plugin_sync.py on {now}. All PRDs and reports defer to this file.
> Note: plugin package loading and shared ALS-stream parity are tracked separately. A loaded OpenClaw plugin does not, by itself, prove that shared experience-plane writes are live.

## Runtime Flags

```yaml
{flag_lines}
```

## What IS Live

| Component | Status | Evidence |
|---|---|---|
{live_table}

## What Is NOT Live

| Gap | Phase | Note |
|---|---|---|
{not_live_table}

## Phase Progress

| Phase | Name | Status |
|---|---|---|
{phase_table}

## Data Volume

| Stream | Count |
|---|---|
| routing_events.jsonl | {n_ev} |
| routing_outcomes.jsonl | {n_out} |
| eligible outcome-enriched production rows | {eligible_outcomes} |
| candidate artifacts | {n_cands} (evaluated: {n_eval}) |
| pareto frontier members | {len(frontier_ids)} |
| openclaw-plugin event rows | {openclaw_plugin_events} |
| routed openclaw-plugin rows | {openclaw_plugin_routed_rows} |

## Deployment Accountability

- active_candidate_id: {active}
- rollout_mode: {rollout_mode}
- evidence_maturity: {evidence_maturity}
- promotion_ready: {str(flags['promotion_ready']).lower()}

## Last Updated

{now} — auto-generated by plugin_sync.py
"""


# ── Main ───────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, report: bool = False) -> dict:
    """Sync STATUS.md and write plugin_report.json."""
    joined_records = load_joined_records(EVENTS_JSONL, OUTCOMES_JSONL)
    experience_summary = summarize_learning_dataset(joined_records, min_eligible_outcomes=MIN_ELIGIBLE_OUTCOMES)
    state = {
        "n_events":          _count_jsonl(EVENTS_JSONL),
        "n_outcomes":        _count_jsonl(OUTCOMES_JSONL),
        "deployment":        _read_json(DEPLOYMENT_STATE),
        "frontier":          _read_json(PARETO_FRONTIER),
        "source_counts":     _jsonl_source_counts(EVENTS_JSONL),
        "openclaw_plugin_routed_rows": _jsonl_routed_source_count(EVENTS_JSONL, "openclaw-plugin"),
        "openclaw_plugin_loaded": _openclaw_plugin_loaded(),
        "has_model_insights": MODEL_INSIGHTS.exists(),
        "has_skills_perf":   SKILLS_PERF.exists(),
        "experience_summary": experience_summary,
        "meta_router_server_healthy": _meta_router_server_healthy(),
    }
    state["n_candidates"], state["n_evaluated"] = _count_candidates()

    flags = _derive_flags(state)
    status_md = _build_status_md(flags, state)

    plugin_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flags": flags,
        "data_volume": {
            "n_events":     state["n_events"],
            "n_outcomes":   state["n_outcomes"],
            "n_eligible_outcomes": experience_summary["n_eligible_outcomes"],
            "n_candidates": state["n_candidates"],
            "n_evaluated":  state["n_evaluated"],
            "frontier_size": len(state["frontier"].get("frontier", [])),
            "openclaw_plugin_event_rows": state["source_counts"].get("openclaw-plugin", 0),
            "openclaw_plugin_routed_rows": state.get("openclaw_plugin_routed_rows", 0),
        },
        "experience_summary": experience_summary,
        "active_candidate_id": state["deployment"].get("active_candidate_id", "static-default"),
        "rollback_available":  state["deployment"].get("rollback_available", False),
        "rollout_mode": state["deployment"].get("rollout_mode"),
        "evidence_maturity": state["deployment"].get("evidence_maturity"),
    }

    if dry_run:
        print("[DRY-RUN] Would write STATUS.md:")
        print(status_md[:800] + "...\n")
        print("[DRY-RUN] Would write plugin_report.json")
    else:
        STATUS_MD.write_text(status_md)
        print(f"Wrote: {STATUS_MD}")
        PLUGIN_REPORT.write_text(json.dumps(plugin_report, indent=2))
        print(f"Wrote: {PLUGIN_REPORT}")

    if report:
        _print_report(flags, state)

    return plugin_report


def _print_report(flags: dict, state: dict) -> None:
    print("\n── Plugin Sync Report ────────────────────────────")
    for k, v in flags.items():
        icon = "✅" if v else "❌"
        print(f"  {icon} {k}")
    print(f"\n  Events:    {state['n_events']}")
    print(f"  Outcomes:  {state['n_outcomes']}")
    print(f"  Eligible:  {state.get('experience_summary', {}).get('n_eligible_outcomes', 0)}")
    print(f"  Candidates:{state['n_candidates']}  evaluated:{state['n_evaluated']}")
    active = state["deployment"].get("active_candidate_id", "static-default")
    print(f"  Active:    {active}")
    print("─────────────────────────────────────────────────\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MR-ALS Phase 8: Plugin State Sync")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true", help="Print summary to stdout")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, report=args.report)
    if not args.report:
        print(json.dumps({"flags": result["flags"],
                          "data_volume": result["data_volume"]}, indent=2))


if __name__ == "__main__":
    main()
