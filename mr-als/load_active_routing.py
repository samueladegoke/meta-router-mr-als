"""
load_active_routing.py — MR-ALS Phase 3: Deployable Routing Artifact Loader

Reads deployment_state.json to determine the active routing artifact,
loads it, and returns routing overrides (keyword weight adjustments,
type priority reordering, confidence thresholds).

The meta_router.py classify() function calls load_overrides() at module
load time (cached). When a new artifact is promoted, the server must
be restarted or call reload_overrides() to pick up the change.

Usage (in meta_router.py):
    from .load_active_routing import load_overrides
    _ACTIVE_OVERRIDES = load_overrides()

Artifact schema (artifacts/candidate-*.json):
{
  "candidate_id": "baseline-0001",
  "version": "1.0.0",
  "created_at": "...",
  "description": "...",
  "keyword_weight_adjustments": {
    "code": { "weight_multiplier": 1.0 },
    "config": { "weight_multiplier": 1.0 }
  },
  "confidence_thresholds": {
    "min_confidence_to_route": 0.5,
    "high_confidence_threshold": 0.8
  },
  "type_priority": ["audit", "design", "research", "production",
                    "integration", "config", "code"],
  "promoted_at": null,
  "pareto_score": null,
  "metrics": {}
}
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_BASE = Path(__file__).parent.parent
_DEPLOYMENT_STATE = _BASE / "experience" / "deployment_state.json"
_ARTIFACTS_DIR = _BASE / "artifacts"

# Default routing overrides — used when no artifact is active
_DEFAULT_OVERRIDES: dict[str, Any] = {
    "candidate_id": "static-default",
    "keyword_weight_adjustments": {},
    "confidence_thresholds": {
        "min_confidence_to_route": 0.0,
        "high_confidence_threshold": 0.8,
    },
    "type_priority": [
        "audit", "design", "research", "production",
        "integration", "config", "code"
    ],
}

_cached_overrides: Optional[dict[str, Any]] = None


def _load_deployment_state() -> Optional[dict]:
    if not _DEPLOYMENT_STATE.exists():
        return None
    try:
        return json.loads(_DEPLOYMENT_STATE.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_overrides(force_reload: bool = False) -> dict[str, Any]:
    """
    Load routing overrides from the active artifact.

    Returns default overrides if:
    - deployment_state.json is missing
    - active artifact file is missing or malformed
    - any unexpected error

    Never raises — fails closed to default routing.
    """
    global _cached_overrides

    if _cached_overrides is not None and not force_reload:
        return _cached_overrides

    state = _load_deployment_state()
    if state is None:
        _cached_overrides = _DEFAULT_OVERRIDES.copy()
        return _cached_overrides

    active_id = state.get("active_candidate_id")
    if not active_id or active_id == "static-default":
        _cached_overrides = _DEFAULT_OVERRIDES.copy()
        return _cached_overrides

    artifact_path = _ARTIFACTS_DIR / f"{active_id}.json"
    if not artifact_path.exists():
        _cached_overrides = _DEFAULT_OVERRIDES.copy()
        return _cached_overrides

    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        # Validate required fields
        if not isinstance(artifact.get("type_priority"), list):
            raise ValueError("type_priority must be a list")
        _cached_overrides = {
            "candidate_id": artifact.get("candidate_id", active_id),
            "keyword_weight_adjustments": artifact.get("keyword_weight_adjustments", {}),
            "confidence_thresholds": artifact.get("confidence_thresholds",
                                                   _DEFAULT_OVERRIDES["confidence_thresholds"]),
            "type_priority": artifact["type_priority"],
        }
        return _cached_overrides
    except Exception:
        # Malformed artifact — fail closed to defaults
        _cached_overrides = _DEFAULT_OVERRIDES.copy()
        return _cached_overrides


def reload_overrides() -> dict[str, Any]:
    """Force a reload from disk. Call after deploying a new artifact."""
    return load_overrides(force_reload=True)


def get_active_candidate_id() -> str:
    """Return the currently active candidate ID."""
    return load_overrides().get("candidate_id", "static-default")


def promote_artifact(
    candidate_id: str,
    artifact: dict,
    *,
    rollout_mode: str = "manual",
    activation_basis: str = "manual-promotion",
    eligible_outcomes: int | None = None,
) -> bool:
    """
    Promote a candidate artifact as active:
    1. Write artifact JSON to artifacts/{candidate_id}.json
    2. Update deployment_state.json with rollback info
    3. Reload overrides cache

    Returns True on success, False on failure.
    """
    try:
        # Write artifact
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = _ARTIFACTS_DIR / f"{candidate_id}.json"
        artifact["candidate_id"] = candidate_id
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

        # Update deployment state
        current_state = _load_deployment_state() or {}
        prev_id = current_state.get("active_candidate_id", "static-default")

        metrics = artifact.get("metrics", {})
        shadow_eval_n = metrics.get("shadow_eval_n")
        eligible_outcomes = 0 if eligible_outcomes is None else eligible_outcomes
        promotion_ready = bool(metrics.get("gate_passes")) and eligible_outcomes >= 50
        evidence_maturity = (
            "production-ready"
            if promotion_ready
            else ("shadow-only" if shadow_eval_n else "manual-unknown")
        )

        new_state = {
            "active_candidate_id": candidate_id,
            "promoted_at": _now_iso(),
            "previous_candidate_id": prev_id,
            "rollback_available": prev_id != "static-default",
            "rollback_candidate_id": prev_id if prev_id != "static-default" else None,
            "rollout_mode": rollout_mode,
            "activation_basis": activation_basis,
            "eligible_outcomes_at_promotion": eligible_outcomes,
            "shadow_eval_n_at_promotion": shadow_eval_n,
            "promotion_ready": promotion_ready,
            "evidence_maturity": evidence_maturity,
            "last_rollout_result": {
                "status": "promoted",
                "candidate_id": candidate_id,
                "activation_basis": activation_basis,
                "rollout_mode": rollout_mode,
            },
        }
        _DEPLOYMENT_STATE.parent.mkdir(parents=True, exist_ok=True)
        _DEPLOYMENT_STATE.write_text(json.dumps(new_state, indent=2), encoding="utf-8")

        # Reload cache
        reload_overrides()
        return True
    except Exception:
        return False


def rollback() -> bool:
    """Roll back to the previous candidate."""
    state = _load_deployment_state()
    if not state:
        return False
    rollback_id = state.get("rollback_candidate_id")
    if not rollback_id:
        return False
    artifact_path = _ARTIFACTS_DIR / f"{rollback_id}.json"
    if not artifact_path.exists():
        return False
    try:
        artifact = json.loads(artifact_path.read_text())
        return promote_artifact(rollback_id, artifact)
    except Exception:
        return False


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
