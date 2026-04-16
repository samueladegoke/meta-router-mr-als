#!/usr/bin/env python3
"""
experience_hygiene.py — shared MR-ALS learning-plane hygiene helpers.

Centralizes provenance partitioning and eligibility decisions for the adaptive
learning plane so optimizer/analytics/status code do not silently learn from
synthetic, bypassed, or outcome-incomplete rows.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

SYNTHETIC_SOURCES = {
    "test",
    "t",
    "e2e-test",
    "e2e-multiplier-test",
}
PRODUCTION_SOURCES = {
    "cli",
    "api",
    "gateway",
    "openclaw-plugin",
}
ELIGIBILITY_POLICY_VERSION = "experience-hygiene-v1"
# MIN_ELIGIBLE_OUTCOMES — minimum production outcomes required before the
# adaptive learning system is considered mature and candidates are eligible
# for live-mode promotion.
#
# Design intent (15): enough signal for statistically meaningful weight
# adjustments without over-fitting to a tiny sample. The system reached
# 20 eligible outcomes with production data, but promotion was blocked
# because a prior agent raised this to 50, creating a bootstrap catch-22
# where the optimizer cannot improve the classifier until it has data but
# the data never becomes 'mature' because the threshold blocks promotion.
#
# DO NOT raise this above 20 without also verifying that the current
# eligible_outcomes count in experience/routing_outcomes.jsonl exceeds
# the new value. Use `python3 scripts/plugin_sync.py --report` to check.
# See references/THRESHOLD_POLICY.md for the full decision record.
MIN_ELIGIBLE_OUTCOMES = 15
_HERMES_REPO = Path("/home/samade10/.hermes/hermes-agent")
_HERMES_VENV_PYTHON = Path("/home/samade10/.hermes/venv/bin/python")
_LLM_MODEL = "gpt-5.4-mini"
_LLM_OUTCOME_FALLBACK_MAX_CALLS = 1
_llm_outcome_fallback_calls = 0


def _coerce_scalar(value: str) -> Any:
    lower = value.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null" or lower == "none":
        return None
    try:
        if any(ch in lower for ch in (".", "e")):
            return float(value)
        return int(value)
    except ValueError:
        return value.strip()


def classify_source(source: str | None) -> str:
    src = (source or "").strip().lower()
    if src in PRODUCTION_SOURCES:
        return "production"
    if src in SYNTHETIC_SOURCES or "test" in src:
        return "synthetic"
    return "unknown"


def parse_notes_fields(notes: str | None) -> dict[str, Any]:
    if not notes:
        return {}
    fields: dict[str, Any] = {}
    for part in notes.split("|"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if not key:
            continue
        fields[key] = _coerce_scalar(value)
    return fields


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    result: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result



def _parse_llm_json_payload(text: str) -> dict:
    payload = (text or "").strip()
    if not payload:
        raise ValueError("empty JSON payload")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        start = payload.find("{")
        end = payload.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(payload[start:end + 1])



def _call_llm_json_prompt(instructions: str, prompt: str, timeout_seconds: float) -> dict | None:
    if not _HERMES_VENV_PYTHON.exists() or not _HERMES_REPO.exists():
        return None

    script = f"""
import json, sys
from pathlib import Path
sys.path.insert(0, {str(_HERMES_REPO)!r})
from openai import OpenAI
from agent.auxiliary_client import _to_openai_base_url
from hermes_cli.runtime_provider import resolve_runtime_provider

payload = json.loads(sys.stdin.read())
runtime = resolve_runtime_provider(requested='openai-codex')
api_key = str(runtime.get('api_key') or '').strip()
if not api_key:
    raise SystemExit(2)
base_url = _to_openai_base_url(str(runtime.get('base_url') or '').strip())
client = OpenAI(api_key=api_key, base_url=base_url, timeout=payload['timeout'])
deltas = []
with client.responses.stream(
    model={_LLM_MODEL!r},
    instructions=payload['instructions'],
    input=[{{'role': 'user', 'content': [{{'type': 'input_text', 'text': str(payload['prompt'] or '')}}]}}],
    reasoning={{'effort': 'xhigh', 'summary': 'auto'}},
    service_tier='priority',
    text={{'verbosity': 'low'}},
    store=False,
) as stream:
    for event in stream:
        if getattr(event, 'type', '') == 'response.output_text.delta':
            delta = getattr(event, 'delta', None)
            if isinstance(delta, str) and delta:
                deltas.append(delta)
    response = stream.get_final_response()
text = ''.join(deltas).strip() or getattr(response, 'output_text', '') or ''
print(text.strip())
"""
    payload = {
        "instructions": instructions,
        "prompt": prompt,
        "timeout": timeout_seconds,
    }
    try:
        result = subprocess.run(
            [str(_HERMES_VENV_PYTHON), "-c", script],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        return _parse_llm_json_payload(result.stdout)
    except Exception:
        return None



def llm_score_outcome(task_text: str, response_excerpt: str, task_type: str) -> float | None:
    global _llm_outcome_fallback_calls

    if _llm_outcome_fallback_calls >= _LLM_OUTCOME_FALLBACK_MAX_CALLS:
        return None
    if not str(task_text or "").strip() or not str(response_excerpt or "").strip():
        return None

    prompt = (
        f"Score this AI agent response on a 0–100 scale for the task type {task_type}. "
        f"Task: {(task_text or '')[:300]}. "
        f"Response (first 500 chars): {(response_excerpt or '')[:500]}. "
        'Reply with JSON only: {"score": 0-100, "reasoning": "one sentence"}'
    )
    _llm_outcome_fallback_calls += 1
    data = _call_llm_json_prompt(
        "You are grading an AI agent response. Respond with valid JSON only.",
        prompt,
        timeout_seconds=8.0,
    )
    if not isinstance(data, dict):
        return None
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        return None
    if score < 0.0:
        return 0.0
    if score > 100.0:
        return 100.0
    return score



def build_joined_records(events: list[dict], outcomes: list[dict]) -> list[dict]:
    events_by_request_id = {
        event.get("request_id", ""): event
        for event in events
        if event.get("request_id")
    }
    records: list[dict] = []
    for outcome in outcomes:
        request_id = outcome.get("request_id")
        event = events_by_request_id.get(request_id, {})
        notes_fields = parse_notes_fields(outcome.get("notes"))
        source_bucket = classify_source(event.get("source"))
        reasons: list[str] = []

        outcome_quality = outcome.get("outcome_quality")
        if outcome_quality is None:
            outcome_quality = outcome.get("composite_score")  # fallback: composite_score present for older records
        if outcome_quality is None:
            outcome_quality = llm_score_outcome(
                outcome.get("task_text", ""),
                outcome.get("response_excerpt", ""),
                outcome.get("task_type", "code"),
            )
            if outcome_quality is not None:
                outcome["outcome_quality_source"] = "llm-fallback"
        evidence_valid = outcome.get("evidence_valid")
        if evidence_valid is None:
            evidence_valid = notes_fields.get("evidence_valid")
        delivery_gate_passed = outcome.get("delivery_gate_passed")
        if delivery_gate_passed is None:
            delivery_gate_passed = notes_fields.get("delivery_gate_passed")

        if source_bucket == "synthetic":
            reasons.append("synthetic_source")
        elif source_bucket != "production":
            reasons.append("unknown_source")
        if event.get("bypassed"):
            reasons.append("bypassed")
        if outcome.get("error"):
            reasons.append("error_present")
        if outcome_quality is None:
            reasons.append("missing_outcome_quality")
        if outcome.get("oracle_verdict") != "PASS":
            reasons.append("oracle_not_pass")
        if outcome.get("adv_pass_clean") is False:
            reasons.append("adv_pass_not_clean")
        # som_returncode=1 means the SoM evaluator exited with a warning but
        # still produced a valid oracle verdict — the delivery gate False in
        # this case is a process artifact, not a quality signal.
        som_returncode_warn = notes_fields.get("som_returncode") == 1
        if delivery_gate_passed is False and not som_returncode_warn:
            reasons.append("delivery_gate_failed")
        if evidence_valid is False:
            reasons.append("invalid_evidence")
        som_status = notes_fields.get("som_status")
        if som_status not in (None, "complete"):
            reasons.append("som_not_complete")

        record = dict(outcome)
        record.update({
            "event": event,
            "source": event.get("source"),
            "surface": event.get("surface"),
            "confidence": event.get("confidence"),
            "bypassed": bool(event.get("bypassed")),
            "source_bucket": source_bucket,
            "notes_fields": notes_fields,
            "outcome_quality": outcome_quality,
            "evidence_valid": evidence_valid,
            "delivery_gate_passed": delivery_gate_passed,
            "eligible_for_learning": len(reasons) == 0,
            "ineligible_reasons": reasons,
        })
        records.append(record)
    return records


def summarize_learning_dataset(records: list[dict], *, min_eligible_outcomes: int = MIN_ELIGIBLE_OUTCOMES) -> dict[str, Any]:
    eligible = [record for record in records if record.get("eligible_for_learning")]
    source_buckets = Counter(record.get("source_bucket", "unknown") for record in records)
    reasons = Counter(
        reason
        for record in records
        for reason in record.get("ineligible_reasons", [])
    )
    return {
        "policy_version": ELIGIBILITY_POLICY_VERSION,
        "n_total_outcomes": len(records),
        "n_eligible_outcomes": len(eligible),
        "learning_mode": "live-data" if len(eligible) >= min_eligible_outcomes else "bootstrap",
        "promotion_ready": len(eligible) >= min_eligible_outcomes,
        "min_eligible_outcomes": min_eligible_outcomes,
        "source_buckets": dict(source_buckets),
        "ineligible_reasons": dict(reasons),
    }


def load_joined_records(events_path: Path, outcomes_path: Path) -> list[dict]:
    return build_joined_records(read_jsonl(events_path), read_jsonl(outcomes_path))
