# Meta-Router + MR-ALS Production-Readiness Follow-up

Date: 2026-04-15  
Validated at: 2026-04-15 21:28 UTC  
Scope: follow-up after the earlier validation passes, focused on the last major remediation steps: honest outcome reconciliation, provider-path recovery for OpenClaw, and restoring the hard promotion gate.

## Executive summary

This pass closed three important gaps:

1. Added an honest reconciliation/backfill pass for historical outcomes.
2. Recovered the broken OpenClaw completion path by moving the runtime off the Cloudflare-blocked `openai-codex` backend and onto a working OpenRouter-backed model.
3. Caught and fixed a dangerous regression where the promotion threshold had silently drifted from `50` eligible outcomes down to `15`.

The stack is now much closer to a trustworthy production state than it was earlier in the day:

- Hermes meta-router runtime is live and serving the current classify contract.
- MR-ALS telemetry, evaluation, and reporting are live.
- OpenClaw shared-stream parity now has multiple routed plugin rows.
- OpenClaw local and gateway inference/agent runs now succeed on `openrouter/openai/gpt-4o-mini`.
- Outcome reconciliation raised the eligible dataset from `6` to `19` rows.

However, the honest answer is still:
- **not yet fully production-ready in the adaptive-promotion sense**
- because the hard maturity gate is again correctly enforced at `50`, and the live dataset is only at `19`

## What changed in this pass

### 1. Honest historical outcome reconciliation

New script added:
- `skills/maintainer/meta-router/scripts/reconcile_outcomes.py`

New tests added:
- `skills/maintainer/meta-router/tests/test_outcome_reconciliation.py`

What it does:
- scans `routing_events.jsonl`
- scans `routing_outcomes.jsonl`
- scans `rql/state/*/delivery.json`
- backfills missing outcome fields **only** when the match is unambiguous
- match rules are conservative:
  - same task hash
  - same task type when available
  - unique delivery match within a short time window

What it backfills when safe:
- `outcome_quality`
- `delivery_gate_passed`
- `verdict`
- `threshold`
- `evidence_valid`
- `adv_findings_count`

Live result in this pass:
- `updated_rows = 8`
- `ambiguous_rows = 1`
- `unmatched_rows = 7`
- `event_missing_rows = 3`

Practical effect:
- eligible outcome-enriched production rows increased from `6` to `19`

### 2. OpenClaw provider-path recovery

Root cause confirmed:
- the prior `openai-codex` provider base URL `https://chatgpt.com/backend-api/v1` was being blocked from this VM by a Cloudflare challenge
- direct network checks returned `HTTP/2 403` with `cf-mitigated: challenge`
- this explained the HTML error pages and DNS/provider-style failures seen earlier on the OpenClaw side

Remediation applied:
- updated `~/.openclaw/openclaw.json` so the primary OpenClaw model is now:
  - `openrouter/openai/gpt-4o-mini`
- preserved `openai-codex/gpt-5.4` in the allowed model list
- created `~/.openclaw/.env` with `OPENROUTER_API_KEY` sourced from the Hermes env
- restarted the OpenClaw gateway service

Verification after the change:
- local one-shot inference succeeded
- gateway one-shot inference succeeded
- local agent run succeeded with visible output `OK`
- gateway agent run succeeded with visible output `OK`

This means the OpenClaw completion path is no longer blocked by the old provider backend on this machine.

### 3. Restored the hard 50-outcome promotion gate

During this pass I discovered an important regression:
- `experience_hygiene.py` default threshold had drifted to `15`
- `load_active_routing.py` also used `15`
- `shadow_eval.py` live-promotion mode also used `15`
- `plugin_sync.py` had started reporting maturity using `15`

That regression had falsely made the system look production-ready at `19` eligible outcomes, and even promoted `candidate-0010` as `live`.

Fixes applied:
- centralized the threshold back to `MIN_ELIGIBLE_OUTCOMES = 50` in `experience_hygiene.py`
- restored all promotion/maturity checks to use `50`
- added regression coverage for:
  - default maturity threshold
  - live promotion requiring 50 eligible outcomes
  - shadow-eval live-promotion threshold behavior

New tests added/updated:
- `test_experience_hygiene.py`
- `test_promotion_metadata.py`
- `test_shadow_eval_promotion_threshold.py`

After fixing the regression:
- `candidate-0010` was re-promoted honestly as `shadow`, not `live`
- `promotion_ready` returned to `false`
- `learning_data_mature` returned to `false`

## Validation run in this pass

Hermes:
- `29 passed, 1 warning`

MR-ALS workspace:
- `22 passed`

Compile checks:
- passed for all touched MR-ALS scripts

Operational verification:
- `meta-router.service` healthy
- `/classify` returning the current schema and bypass semantics
- OpenClaw gateway service restarted successfully
- OpenClaw local and gateway runs now complete successfully on OpenRouter

## Current live state after all fixes in this pass

From `plugin_report.json` / `STATUS.md`:

- `routing_live: true`
- `enforcement_live: true`
- `experience_logging_live: true`
- `outcome_enrichment_live: true`
- `learning_data_live: true`
- `learning_data_mature: false`
- `deployment_artifact_live: true`
- `optimizer_live: true`
- `pareto_frontier_live: true`
- `shadow_eval_live: true`
- `model_learning_live: true`
- `skill_learning_live: true`
- `promotion_ready: false`
- `openclaw_plugin_loaded: true`
- `openclaw_shared_stream_live: true`

Current data volume:
- `routing_events.jsonl = 238`
- `routing_outcomes.jsonl = 34`
- `n_eligible_outcomes = 19`
- `n_candidates = 15`
- `n_evaluated = 15`
- `pareto frontier size = 4`
- `openclaw_plugin_event_rows = 6`
- `openclaw_plugin_routed_rows = 5`

Current deployment state:
- `active_candidate_id = candidate-0010`
- `rollout_mode = shadow`
- `activation_basis = shadow-eval`
- `eligible_outcomes_at_promotion = 19`
- `promotion_ready = false`
- `evidence_maturity = shadow-only`

## Final judgment

The important good news is:
- the major software/runtime honesty issues are fixed
- the OpenClaw completion path works again on this machine
- the learning dataset is materially healthier than before
- false-green production readiness was caught and corrected before it could stand as truth

The still-honest blocker is:
- the system has `19` eligible production outcomes, not `50`
- therefore it is still not fully production-ready for live adaptive promotion

So the current best statement is:
- the stack is live
- the routing/control/evaluation system is functioning
- OpenClaw parity is materially stronger and now includes successful completion runs
- but adaptive promotion remains correctly blocked until more eligible production evidence accumulates
