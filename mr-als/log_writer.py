"""
log_writer.py — MR-ALS Unified Experience Plane Writer (Phase 1)

Thread-safe, append-only JSONL writer for routing_events.jsonl and
routing_outcomes.jsonl. All routing surfaces (gateway, CLI, API,
OpenClaw plugin) should import this module to write to the shared
experience plane.

Usage:
    from skills.maintainer.meta_router.experience.log_writer import (
        log_routing_event, log_routing_outcome
    )
    log_routing_event(source="cli", task_text="write a CSV parser", ...)
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_EXPERIENCE_DIR = Path(__file__).parent
_EVENTS_PATH = _EXPERIENCE_DIR / "routing_events.jsonl"
_OUTCOMES_PATH = _EXPERIENCE_DIR / "routing_outcomes.jsonl"

_write_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _append(path: Path, record: dict) -> None:
    """Thread-safe append of one JSON record to a JSONL file."""
    line = json.dumps(record, ensure_ascii=False)
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def make_request_id() -> str:
    """Generate a unique request ID for joining events to outcomes."""
    return str(uuid.uuid4())


def log_routing_event(
    *,
    source: str,           # gateway | cli | api | openclaw-plugin
    surface: str = "",     # telegram | discord | cli | http | openclaw
    task_text: str,
    task_type: str,
    mode: str,
    confidence: float,
    bypassed: bool = False,
    bypass_reason: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    routing_artifact_version: str = "static-default",
    active_candidate_id: str = "baseline-0001",
) -> str:
    """
    Log a routing decision to routing_events.jsonl.
    Returns the request_id so callers can correlate with outcomes.
    """
    if request_id is None:
        request_id = make_request_id()

    # Map type to primary/secondary (SoM × 0.6 + EOP × 0.4 model)
    primary_map = {
        "code":        "som",
        "audit":       "eop-adv-pass",
        "research":    "som",
        "production":  "som",
        "integration": "som",
        "design":      "som",
        "config":      "som",
    }
    secondary_map = {
        "code":        "eop-adv-pass",
        "audit":       "som",
        "research":    None,
        "production":  "eop-adv-pass",
        "integration": "eop-adv-pass",
        "design":      None,
        "config":      None,
    }

    record = {
        "request_id": request_id,
        "timestamp": _now(),
        "source": source,
        "surface": surface or source,
        "session_id": session_id,
        "task_text_hash": _hash(task_text),
        "task_preview": task_text[:120],
        "bypassed": bypassed,
        "bypass_reason": bypass_reason,
        "task_type": task_type,
        "mode": mode,
        "primary": primary_map.get(task_type, "som"),
        "secondary": secondary_map.get(task_type),
        "confidence": round(confidence, 3),
        "route_source": "meta-router",
        "routing_artifact_version": routing_artifact_version,
        "active_candidate_id": active_candidate_id,
    }

    try:
        _append(_EVENTS_PATH, record)
    except Exception:
        pass  # Never crash the caller due to logging failure

    return request_id


def log_routing_outcome(
    *,
    request_id: str,
    task_type: str,
    composite_score: Optional[float] = None,
    som_score: Optional[float] = None,
    eop_score: Optional[float] = None,
    outcome_quality: Optional[float] = None,
    oracle_verdict: Optional[str] = None,   # PASS | FAIL | SKIPPED
    retried: bool = False,
    retry_count: int = 0,
    adv_pass_clean: Optional[bool] = None,
    adv_findings_count: Optional[int] = None,
    evidence_valid: Optional[bool] = None,
    delivery_gate_passed: Optional[bool] = None,
    verdict: Optional[str] = None,
    threshold: Optional[float] = None,
    latency_ms: Optional[float] = None,
    error: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    """Log a task completion outcome keyed by request_id."""
    record = {
        "request_id": request_id,
        "timestamp": _now(),
        "task_type": task_type,
        "composite_score": composite_score,
        "som_score": som_score,
        "eop_score": eop_score,
        "outcome_quality": outcome_quality,
        "oracle_verdict": oracle_verdict,
        "retried": retried,
        "retry_count": retry_count,
        "adv_pass_clean": adv_pass_clean,
        "adv_findings_count": adv_findings_count,
        "evidence_valid": evidence_valid,
        "delivery_gate_passed": delivery_gate_passed,
        "verdict": verdict,
        "threshold": threshold,
        "latency_ms": latency_ms,
        "error": error,
        "notes": notes,
    }
    try:
        _append(_OUTCOMES_PATH, record)
    except Exception:
        pass


def get_recent_events(n: int = 50) -> list[dict]:
    """Return the last n routing events."""
    if not _EVENTS_PATH.exists():
        return []
    lines = _EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    recent = lines[-n:]
    out = []
    for line in recent:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def get_stats() -> dict:
    """Return summary stats from routing_events.jsonl."""
    events = get_recent_events(n=10000)
    if not events:
        return {"total": 0, "by_type": {}, "by_source": {}, "bypassed": 0}

    by_type: dict[str, int] = {}
    by_source: dict[str, int] = {}
    bypassed = 0
    for e in events:
        tt = e.get("task_type", "unknown")
        src = e.get("source", "unknown")
        by_type[tt] = by_type.get(tt, 0) + 1
        by_source[src] = by_source.get(src, 0) + 1
        if e.get("bypassed"):
            bypassed += 1

    return {
        "total": len(events),
        "by_type": by_type,
        "by_source": by_source,
        "bypassed": bypassed,
    }
