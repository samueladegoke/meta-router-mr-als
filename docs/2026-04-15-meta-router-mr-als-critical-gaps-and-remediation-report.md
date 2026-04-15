# Meta-Router + MR-ALS Critical Gaps and Remediation Report

Date: 2026-04-15  
Prepared for: Hermes continuation work in the VM  
Prepared from: local Claude Code transcript review, live VM inspection on 2026-04-15, prior Obsidian reports, and external research

## Purpose

This report is a correction-oriented handoff. It is meant to answer four questions clearly:

1. What is the real current orchestration architecture?
2. Is the meta-router still useful now that SoM v3 absorbed most of EOP?
3. What in the current meta-router and MR-ALS stack is actually broken, misleading, or under-specified?
4. What should Hermes fix first, in what order, and why?

The short answer is:

- The current architecture is no longer "route to SoM or EOP" in the older sense.
- The real live path is now "meta-router classification/control plane -> SoM v3 main execution -> optional ADV_PASS hardening pass".
- That means the meta-router still has a purpose, but it is narrower than earlier documents implied.
- The biggest current problem is not conceptual elegance. It is learning-plane contamination and promotion/gating discipline.

## Executive Summary

The architectural direction is mostly correct: SoM v3.1 is now the primary work engine, while EOP survives mostly as evidence/ADV_PASS discipline. That simplification is good. It reduces duplicated orchestration and matches current agent-design guidance that simpler composable systems are usually more reliable than complicated routers.

However, the current live MR-ALS stack has several critical gaps:

- Production learning data is mixed with test and e2e rows.
- The active candidate appears promoted ahead of evidence maturity.
- Optimizer and analytics artifacts do not appear to enforce strong dataset hygiene.
- Status and readiness claims are ahead of the actual evidence volume.
- The naming and documentation still reflect an old "SoM vs EOP router" model that is no longer the actual runtime model.
- The evidence contract is producing invalid evidence outcomes that should not be allowed to train or promote anything.

The most important recommendation is to keep the meta-router, but narrow and harden its role:

- Keep it as ingress classification, control policy, enforcement, telemetry, and adaptive-selection infrastructure.
- Stop treating it conceptually as a content-reasoning engine that competes with SoM.
- Make learning/promotion decisions only on clean, partitioned, outcome-valid data.

## Current Architecture Clarification

## What the live runtime is doing now

Live inspection on 2026-04-15 showed the following practical flow in Hermes:

1. `run_agent.py` invokes the meta-router before the main turn.
2. The meta-router classifies the incoming request and injects routing metadata like `[META-ROUTER | type | mode]`.
3. SoM Phase 1 then runs as the main reasoning scaffold.
4. After the main turn, SoM Phase 2 runs.
5. For relevant task classes such as `code`, `audit`, `production`, and `integration`, an `ADV_PASS` can run after SoM as an adversarial/evidence hardening layer.

That means the current live system is not really doing "choose SoM or choose EOP" in the older sense. It is doing:

`meta-router -> SoM -> optional ADV_PASS`

This is important because some earlier planning language still implies a two-framework content router where SoM and EOP are peer alternatives. That is no longer the best description of the live system.

## What the meta-router is still for

The meta-router still has a legitimate role even after SoM v3 absorbed most of EOP:

- classify the task at ingress
- set orchestration mode and enforcement policy
- inject structured control metadata
- collect experience and outcome telemetry
- manage adaptive routing/deployment artifacts
- enforce promotion and rollback policy
- support future abstain/clarify/escalate policies

So the correct question is not "why keep the meta-router if SoM does the main work?" The correct question is "what should the meta-router own now that SoM is the main work engine?"

The answer is:

- The meta-router should own control-plane responsibilities.
- SoM should own most content-level reasoning and task decomposition.
- ADV_PASS should own hardening/evidence challenge on the subset of tasks where that is warranted.

## Why this direction is strategically sound

This aligns with external agent-systems guidance:

- Anthropic's guidance on effective agents argues for using simple composable patterns instead of unnecessary orchestration complexity.
- Meta-Harness emphasizes improving the harness, preserving high-fidelity execution traces, and evaluating changes against fixed criteria instead of loosely changing many moving parts at once.
- Karpathy's `autoresearch` repo leans toward simple measurable loops, narrow mutable surfaces, and strong baseline discipline.

So the SoM-centric simplification is not the problem. The problem is that the live adaptive-learning plane has not yet fully caught up to the simplified execution model.

## Live-State Findings From 2026-04-15

All findings below are based on live inspection of the Hermes VM and the current adaptive-routing artifacts.

## Finding 1: The experience plane is contaminated by tests

Observed evidence:

- `routing_events.jsonl` had 127 rows.
- Event source counts included:
  - `cli`: 79
  - `e2e-test`: 21
  - `t`: 18
  - `api`: 6
  - `e2e-multiplier-test`: 2
  - `test`: 1
- Surface counts included:
  - `cli`: 121
  - `http`: 6

Why this matters:

- A learning system cannot safely optimize on production behavior if its event plane is mixing production interactions with e2e harness traffic and ad hoc test traffic.
- This contaminates difficulty priors, route frequencies, confidence estimates, and promotion decisions.
- It also makes artifact summaries look healthier than they really are because "lots of events" may not mean "lots of production-grade outcomes."

Correction required:

- Introduce explicit dataset partitioning and learning eligibility flags.
- Test traffic must be stored, but must not silently enter promotion or optimizer datasets.

## Finding 2: Outcome volume is far too small relative to the claims being made

Observed evidence:

- `routing_outcomes.jsonl` had only 4 rows.
- Three of the four rows were obviously test-related:
  - `test-rid-123`
  - `rid-test-append`
  - `rid-test-phase2`
- Only one row looked plausibly non-test:
  - `3f70bcaf-bc8c-49cd-99fa-433e17e448c5`

Why this matters:

- An adaptive-routing system should not sound production-confident when its true outcome set is this small.
- Four outcomes, with most apparently synthetic, is not enough to justify strong candidate claims, reliable confidence calibration, or meaningful skill/model insights.

Correction required:

- Tighten readiness language.
- Block candidate promotion unless minimum genuine outcome thresholds are met.
- Separate "telemetry alive" from "learning mature."

## Finding 3: The active candidate appears ahead of evidence maturity

Observed evidence:

- `deployment_state.json` contained:
  - `active_candidate_id: "candidate-0002"`
  - `previous_candidate_id: "static-default"`
  - `rollout_mode: null`
  - `last_rollout_result: null`
- `candidate-0002.json` showed:
  - strategy: `audit-prod-premium-v1`
  - `promoted_at: null`
  - `pareto_score: 0.8844`
  - `shadow_eval_n: 20`
  - `gate_passes: true`
- `pareto_frontier.json` showed:
  - `frontier: ["candidate-0002"]`
  - `baseline_candidate_id: "baseline-0001"`
  - `total_candidates_evaluated: 3`
- The same frontier artifact still notes that Phase 4 has not really started and that at least 50 outcome-enriched events are needed.

Why this matters:

- The system is simultaneously signaling "candidate-0002 is active" and "we do not yet have enough outcome-enriched data."
- The presence of an active candidate with null rollout metadata creates audit ambiguity.
- If a candidate is active because of shadow/bootstrap evidence only, that should be stated explicitly and durably in the artifact schema.

Correction required:

- Add explicit promotion lineage fields.
- Record whether activation is shadow-only, canary, manual, or full production.
- Consider reverting to baseline or freezing promotion until clean evidence thresholds are met.

## Finding 4: Status claims and analytics artifacts are drifting out of sync

Observed evidence:

- `STATUS.md` reported many components as live:
  - routing live
  - enforcement live
  - experience logging live
  - outcome enrichment live
  - deployment artifact live
  - optimizer live
  - pareto frontier live
  - shadow eval live
  - model learning live
  - skill learning live
- But `model_insights.json` still reported:
  - `n_outcomes: 1`
  - `n_events: 6`
  - `shadow_set_size: 20`
- `skills_performance.json` was generated from only `n_total_outcomes: 1`
- Most skill/task categories were still effectively `no_data`

Why this matters:

- The instrumentation may be live, but the learning products are not yet mature.
- Operators and future agents can be misled if "live" is read as "trustworthy for adaptation."
- Freshness and data sufficiency are first-class operational states and should not be hidden behind a binary live/not-live label.

Correction required:

- Replace overly coarse live-status reporting with freshness and sufficiency reporting.
- Example dimensions:
  - pipeline alive
  - last successful write
  - eligible production outcomes count
  - promotion-ready yes/no
  - confidence-calibrated yes/no

## Finding 5: The optimizer path does not appear to enforce robust dataset hygiene

Observed evidence:

- `optimize_weights.py` uses:
  - `MIN_OUTCOMES = 50`
  - shadow bootstrap from `shadow_eval_set.json`
  - live data from `routing_outcomes.jsonl`
- During inspection, no robust filtering was found for:
  - test/e2e sources
  - classification-only events
  - invalid evidence rows
  - session provenance tiers

Why this matters:

- Even if the optimizer has a minimum threshold, it still needs strict eligibility rules for what counts toward optimization.
- Otherwise the system can "learn" from rows that should have been retained only for audit, debugging, or synthetic eval tracking.

Correction required:

- Make optimizer eligibility explicit and centralized.
- Reject or quarantine rows unless they satisfy all required conditions.

## Finding 6: The evidence contract is not yet strong enough

Observed evidence:

- Recent outcome rows showed:
  - `evidence_valid = false`
  - empty `hypothesis.json`
  - empty evidence items
  - `adv_pass_clean = false`
  - `adv_findings = 2`

Why this matters:

- If evidence is invalid and ADV_PASS fails, the row should not silently behave like normal adaptive-learning fuel.
- Otherwise the system will reward incomplete or weakly evidenced executions.
- This is especially risky because the whole point of SoM+ADV discipline is to improve correctness and robustness under uncertainty.

Correction required:

- Invalid-evidence rows must be explicitly excluded from positive learning and promotion signals.
- They should instead feed a separate failure-analysis dataset.

## Finding 7: OpenClaw parity is still incomplete

Observed evidence:

- `STATUS.md` still reports:
  - `openclaw_plugin_loaded: true`
  - `openclaw_shared_stream_live: false`
- Event sources did not show the expected OpenClaw shared-stream parity.

Why this matters:

- The system currently claims a broader routing/learning fabric than it actually has.
- If OpenClaw is part of the product story, then it needs either real parity or explicit scoping language that says parity is not yet live.

Correction required:

- Either finish shared-stream integration or downgrade claims until it is real.

## Finding 8: Documentation language still reflects the older architecture

Observed evidence:

- Earlier reports and planning artifacts describe the meta-router as routing between SoM and EOP as if they are still co-equal content frameworks.
- Live runtime inspection shows that SoM now does the main work and EOP survives mainly as ADV_PASS/evidence discipline.

Why this matters:

- Documentation drift creates design drift.
- Future optimization work becomes confused if the written mental model does not match the runtime model.
- It also makes wrong fixes more likely, such as trying to restore a two-framework router that is no longer necessary.

Correction required:

- Rewrite the architectural narrative around:
  - control plane
  - main reasoning plane
  - hardening/evidence plane

## Is the Meta-Router Still Necessary?

Yes, but in a more constrained role.

It should not be justified as "the thing that chooses between two major reasoning frameworks" unless that is truly restored and made explicit again.

It should be justified as:

- task ingress classifier
- orchestration-policy selector
- enforcement and telemetry controller
- adaptive deployment and rollback manager
- future abstain/clarify/escalate gate

If the meta-router is not used for those control-plane functions, then it becomes redundant. But as long as the system wants adaptive policy selection, telemetry-backed deployment, and multi-mode enforcement, the meta-router still has a real purpose.

## Corrections and Recommendations

## Priority 0: Stop contaminated data from influencing learning

Actions:

- Add explicit fields such as:
  - `dataset_partition`
  - `event_origin`
  - `learning_eligible`
  - `outcome_eligible`
  - `evidence_eligible`
  - `classification_only`
- Default all synthetic, e2e, manual-test, replay, and debugging rows to `learning_eligible = false`.
- Require explicit opt-in for any row to enter optimizer or promotion datasets.

Reason:

- This is the most dangerous current gap because it can silently poison every adaptive artifact downstream.

Likely file targets:

- `~/.hermes/hermes-agent/gateway/meta_router.py`
- `~/.hermes/hermes-agent/gateway/meta_router_runtime.py`
- `~/.hermes/hermes-agent/gateway/meta_router_executor.py`
- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/optimize_weights.py`
- any artifact writers for `routing_events.jsonl` and `routing_outcomes.jsonl`

## Priority 1: Rework promotion semantics and candidate lineage

Actions:

- Do not allow an active candidate to exist without explicit activation metadata.
- Record:
  - activation reason
  - activation source
  - activation date
  - evaluation basis
  - rollout mode
  - rollback condition
- Add promotion gates that require:
  - minimum clean production outcomes
  - minimum clean evidence-valid outcomes
  - minimum calibration quality
  - minimum canary duration if applicable

Reason:

- `candidate-0002` currently appears more "active" than "accountably promoted."

Likely file targets:

- deployment artifact writers
- frontier selection logic
- `load_active_routing.py`
- any rollout/promotion command or skill scripts

## Priority 2: Split learning products into shadow, production, and failure-analysis planes

Actions:

- Maintain three clearly separated views:
  - shadow eval performance
  - production adaptive-learning performance
  - failure-analysis corpus
- Invalid evidence rows and failed ADV_PASS rows should land in the failure-analysis view, not the main adaptive-learning pool.

Reason:

- This preserves useful information without contaminating route optimization.

## Priority 3: Make status artifacts honest about maturity

Actions:

- Replace binary live flags with richer readiness indicators.
- Add fields such as:
  - `last_event_ingest_at`
  - `last_clean_outcome_at`
  - `eligible_production_outcomes`
  - `optimizer_ready`
  - `promotion_ready`
  - `calibration_ready`
  - `shared_stream_ready`

Reason:

- "Live" is not enough. The operator needs to know whether the system is merely emitting files or whether it is safe to adapt on the resulting data.

## Priority 4: Align docs and naming with the live architecture

Actions:

- Retire or annotate old "SoM vs EOP router" language.
- Replace it with:
  - meta-router = control plane
  - SoM = primary reasoning/execution plane
  - ADV_PASS = hardening/evidence challenge layer
- Audit skill docs, STATUS docs, and PRD text for outdated architecture claims.

Reason:

- This will prevent future agents from implementing the wrong thing.

## Priority 5: Add abstain/clarify handling for ambiguous prompts

Actions:

- Introduce a low-confidence or multi-intent route that can request clarification or enter a safer audit-first mode.
- Do not force every input into a confident task bucket when the router is uncertain.

Reason:

- A strong meta-router should improve safety and efficiency at ingress, not just decorate the prompt.

## Priority 6: Decide the truth about OpenClaw integration

Actions:

- Either complete the shared-stream integration and verify OpenClaw events appear in the same adaptive plane, or explicitly mark the parity work as not yet live.

Reason:

- Architectural truthfulness matters for both operations and future development.

## Recommended Hermes Execution Sequence

Hermes should implement the corrections in this order:

1. Trace how `routing_events.jsonl` and `routing_outcomes.jsonl` are written.
2. Add hard dataset partitioning and eligibility filtering.
3. Patch the optimizer so only eligible clean production outcomes are used.
4. Patch candidate activation/promotion artifacts so activation lineage is explicit.
5. Recompute or regenerate `model_insights.json`, `skills_performance.json`, and frontier artifacts from clean data only.
6. Reclassify current state honestly:
   - if necessary, demote or freeze `candidate-0002`
   - keep bootstrap/shadow evidence, but stop overstating production maturity
7. Update docs and status reporting to reflect the real `meta-router -> SoM -> ADV_PASS` architecture.
8. Decide whether OpenClaw parity will be completed now or downgraded in claims.

## What Hermes Should Not Do

Hermes should not:

- restore an older two-framework "SoM or EOP" router unless there is a deliberate new design decision to do so
- let test/e2e rows count toward adaptive learning or promotion
- treat invalid-evidence rows as normal successful learning outcomes
- preserve misleading readiness language just because the plumbing technically emits files

## Source Notes

## Internal sources reviewed

- `reports/2026-04-05-adaptive-learning-and-agent-harnesses.md`
- `reports/2026-04-05-meta-router-adaptive-learning-prd.md`
- `reports/2026-04-06-meta-router-als-integration-plan.md`
- `reports/2026-04-06-mr-als-final-production-readiness-report.md`
- `reports/2026-04-07-meta-router-als-execution-tracker.md`
- `reports/2026-04-07-meta-router-als-reality-based-prd.md`
- `reports/2026-04-07-som-v3-implementation-report.md`
- `reports/2026-04-10-meta-router-somv3-als-adversarial-audit.md`
- `reports/2026-04-14-meta-router-memory-authority-reconciliation/03-follow-up-live-state-2026-04-15.md`
- `resources/EOP_V2.1_POST_IMPLEMENTATION_REVIEW.md`

## Live VM files inspected on 2026-04-15

- `~/.hermes/hermes-agent/run_agent.py`
- `~/.hermes/hermes-agent/gateway/meta_router.py`
- `~/.hermes/hermes-agent/gateway/meta_router_runtime.py`
- `~/.hermes/hermes-agent/gateway/meta_router_executor.py`
- `~/.openclaw/workspace/skills/maintainer/meta-router/STATUS.md`
- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/optimize_weights.py`
- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/load_active_routing.py`
- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/*`
- `~/.openclaw/workspace/skills/som/SKILL.md`

## External references

- Meta-Harness paper: [https://arxiv.org/abs/2603.28052](https://arxiv.org/abs/2603.28052)
- Meta-Harness artifact repo README: [https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact)
- Karpathy `autoresearch` repo: [https://github.com/karpathy/autoresearch](https://github.com/karpathy/autoresearch)
- Anthropic, "Building effective agents": [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Final Recommendation

Keep the meta-router, but narrow its charter and harden its data discipline.

The architecture should now be treated as:

- meta-router for control plane
- SoM for main reasoning plane
- ADV_PASS for hardening/evidence challenge

The urgent work is not to invent a new orchestration abstraction. The urgent work is to make the existing adaptive-learning and promotion system trustworthy.

## Appendix: Hermes Kickoff Prompt

```text
Read this report first and use it as the source of truth for the current remediation task:

C:\Users\USER\Music\Obsidian-Vault\reports\2026-04-15-meta-router-mr-als-critical-gaps-and-remediation-report.md

Your task is to implement the critical fixes in the live Hermes / MR-ALS stack inside the VM.

Before making any fix, confirm the current reality first. Do not assume this report is perfectly current just because it is detailed. Treat it as a high-quality investigation and hypothesis set that must be verified against the live VM, current files, current artifacts, and current runtime behavior before you change anything.

Verification-first requirements:

1. Re-verify all major claims in this report against the live system before implementing remediations.
2. Distinguish clearly between:
   - claims you confirmed directly from live code or artifacts
   - claims that were historical from docs or prior reports
   - claims that are now outdated or contradicted by current reality
3. If any claim in this report is no longer true, update your execution plan to reflect the actual live state rather than forcing the system to match the report.
4. Produce a short "reality check" summary before major edits that states:
   - what you confirmed
   - what you falsified
   - what is still uncertain
5. Do not remediate based on stale assumptions.

Objectives:

1. Confirm the live execution architecture and preserve it as:
   meta-router -> SoM -> optional ADV_PASS
   Do not revert to an older "route between SoM and EOP as co-equal frameworks" design unless you find a deliberate current spec requiring that.

2. Fix learning-plane contamination:
   - trace exactly where routing_events.jsonl and routing_outcomes.jsonl are written
   - add explicit dataset partition / provenance / eligibility fields
   - ensure e2e, test, replay, debugging, and classification-only rows do not influence optimizer, promotion, or model/skill learning artifacts by default

3. Fix promotion and rollout lineage:
   - inspect how deployment_state.json, pareto_frontier.json, and candidate artifacts are produced
   - require explicit activation metadata
   - make it clear whether a candidate is shadow-only, canary, manual, or production-active
   - if candidate-0002 is ahead of evidence maturity, either freeze it, demote it, or reclassify it honestly

4. Fix optimizer eligibility:
   - inspect optimize_weights.py and any related artifact builders
   - allow only clean, eligible, production-grade outcomes into optimization and promotion calculations
   - invalid evidence rows and failed ADV_PASS rows should go into failure analysis, not positive adaptive learning

5. Fix status/reporting honesty:
   - replace coarse "live" signaling with freshness and sufficiency indicators where needed
   - regenerate model_insights.json / skills_performance.json / related artifacts from clean data only

6. Fix documentation drift:
   - update status/docs/comments so they reflect the real architecture
   - meta-router = control plane
   - SoM = main reasoning plane
   - ADV_PASS = hardening/evidence layer

7. Check OpenClaw parity:
   - verify whether shared-stream integration is actually live
   - if not, downgrade claims or finish the integration

Constraints:

- Preserve useful telemetry, but partition it correctly.
- Do not destroy historical data unless you create a safer archived/quarantine path.
- Prefer explicit schema fields over inference-by-source-name.
- Make the system more auditable, not just more passing.

Expected deliverables:

- code changes in the relevant Hermes/meta-router files
- updated artifact schemas and/or writers
- regenerated status/insight artifacts if appropriate
- a short remediation report summarizing:
  - what was changed
  - what was quarantined or excluded
  - whether candidate-0002 remains active
  - what still remains unresolved

Start by mapping the write path for routing_events.jsonl, routing_outcomes.jsonl, deployment_state.json, pareto_frontier.json, model_insights.json, and skills_performance.json, then patch the data eligibility and promotion logic before doing cosmetic doc updates.
```

## Appendix: Strict Verification-First Hermes Prompt

```text
Read this report first:

C:\Users\USER\Music\Obsidian-Vault\reports\2026-04-15-meta-router-mr-als-critical-gaps-and-remediation-report.md

You are not allowed to trust this report blindly.

Treat the report as a strong investigative brief, not as ground truth. Your first job is to verify the current live reality inside the VM before making any fix, remediation, cleanup, or documentation change.

Hard rules:

1. Do not make any code changes until you complete a reality-check pass.
2. Do not assume any architectural claim, artifact state, candidate status, or data-quality claim is still current.
3. Do not optimize, promote, demote, freeze, or rewrite logic based on stale assumptions.
4. If live reality differs from the report, follow live reality and explicitly record the mismatch.
5. Prefer direct verification from current code, runtime entrypoints, artifact files, and recent logs over older reports or comments.

Required phase order:

Phase 1: Reality Check
- Re-verify the actual execution path in the live Hermes system.
- Re-verify how `routing_events.jsonl`, `routing_outcomes.jsonl`, `deployment_state.json`, `pareto_frontier.json`, `model_insights.json`, and `skills_performance.json` are written and consumed.
- Re-verify whether the live runtime is actually:
  `meta-router -> SoM -> optional ADV_PASS`
- Re-verify whether `candidate-0002` is still the active candidate and whether its activation state is truly under-specified.
- Re-verify whether test/e2e/debugging rows are entering adaptive-learning paths.
- Re-verify whether OpenClaw shared-stream parity is actually live or still absent.

Phase 2: Reality-Check Summary
Before editing anything, produce a concise summary with exactly these sections:
- Confirmed
- Falsified
- Still Uncertain
- Remediation Plan

In that summary, explicitly separate:
- claims confirmed from live code/artifacts
- claims that were only historical
- claims disproven by the current system

Phase 3: Remediation
Only after the reality-check summary is complete, implement the fixes that are still warranted by the verified live state.

Primary remediation goals:

1. Preserve the correct live architecture.
- If verified, keep:
  `meta-router -> SoM -> optional ADV_PASS`
- Do not restore an old "SoM vs EOP as peer frameworks" router unless a current verified spec requires it.

2. Fix learning-plane contamination.
- Add explicit provenance/partition/eligibility fields.
- Ensure e2e, test, replay, debugging, and classification-only rows do not affect optimizer, promotion, or adaptive learning by default.

3. Fix promotion lineage and activation accountability.
- Make activation basis explicit.
- Make rollout mode explicit.
- Make it clear whether a candidate is shadow-only, canary, manual, or production-active.
- If `candidate-0002` is not actually mature enough, freeze it, demote it, or reclassify it honestly based on verified evidence.

4. Fix optimizer eligibility.
- Allow only clean, eligible, production-grade outcomes into optimization and promotion logic.
- Route invalid-evidence rows and failed ADV_PASS rows into failure-analysis paths instead of positive learning.

5. Fix status/reporting honesty.
- Do not use coarse "live" language where freshness, sufficiency, or eligibility is the real issue.
- Regenerate insights/status artifacts from clean data only, if warranted.

6. Fix documentation drift.
- Update docs/comments/status language so it reflects the verified current architecture, not outdated design assumptions.

7. Verify OpenClaw claims.
- If parity is not live, downgrade the claims.
- If parity is live, document exactly where and how it is verified.

Constraints:

- Preserve historical telemetry unless you intentionally quarantine it.
- Prefer quarantine/exclusion over destructive deletion.
- Make schema and artifact semantics more explicit, not more implicit.
- Favor auditability and reversibility.

Required deliverables:

1. A reality-check summary before edits.
2. The code and artifact changes required by the verified findings.
3. A remediation summary stating:
- what changed
- what report claims were confirmed
- what report claims were falsified
- what data was quarantined or excluded
- whether `candidate-0002` remains active
- what still needs follow-up

Begin with verification, not fixes.
```
