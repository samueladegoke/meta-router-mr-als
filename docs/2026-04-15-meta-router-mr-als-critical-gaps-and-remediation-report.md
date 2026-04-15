> Current-state note (validated 2026-04-15 21:28 UTC): this report is historical context, not the live source of truth.
> Defer to `reports/2026-04-15-meta-router-mr-als-production-readiness-follow-up.md`, `reports/2026-04-15-meta-router-mr-als-current-state-validation.md`, and `~/.openclaw/workspace/skills/maintainer/meta-router/STATUS.md` for current machine truth.
> Verified current state in this pass:
> - live flow: `meta-router -> SoM -> optional ADV_PASS`
> - active artifact: `candidate-0010` in `shadow` mode (`promotion_ready=false`, `evidence_maturity=shadow-only`)
> - telemetry: `routing_events.jsonl=238`, `routing_outcomes.jsonl=34`, `eligible_outcomes=19`, `pareto_frontier=4`
> - validation: Hermes meta-router tests `29 passed`; MR-ALS workspace tests `22 passed`; OpenClaw local + gateway runs now succeed on `openrouter/openai/gpt-4o-mini`

     1|> Current-state note (validated 2026-04-15 20:34 UTC): this report is historical context, not the live source of truth.
     2|> Defer to `reports/2026-04-15-meta-router-mr-als-production-readiness-follow-up.md`, `reports/2026-04-15-meta-router-mr-als-current-state-validation.md`, and `~/.openclaw/workspace/skills/maintainer/meta-router/STATUS.md` for current machine truth.
     3|> Verified current state in this pass:
     4|> - live flow: `meta-router -> SoM -> optional ADV_PASS`
     5|> - active artifact: `candidate-0002` in `shadow` mode (`promotion_ready=false`, `evidence_maturity=shadow-only`)
     6|> - telemetry: `routing_events.jsonl=216`, `routing_outcomes.jsonl=28`, `eligible_outcomes=5`, `pareto_frontier=4`
     7|> - validation: Hermes meta-router tests `29 passed`; MR-ALS workspace tests `17 passed`; MR-ALS dry-run semantics and live classify contract were fixed and re-verified
     8|
     9|# Meta-Router + MR-ALS Critical Gaps and Remediation Report
    10|
    11|Date: 2026-04-15  
    12|Prepared for: Hermes continuation work in the VM  
    13|Prepared from: local Claude Code transcript review, live VM inspection on 2026-04-15, prior Obsidian reports, and external research
    14|
    15|## Purpose
    16|
    17|This report is a correction-oriented handoff. It is meant to answer four questions clearly:
    18|
    19|1. What is the real current orchestration architecture?
    20|2. Is the meta-router still useful now that SoM v3 absorbed most of EOP?
    21|3. What in the current meta-router and MR-ALS stack is actually broken, misleading, or under-specified?
    22|4. What should Hermes fix first, in what order, and why?
    23|
    24|The short answer is:
    25|
    26|- The current architecture is no longer "route to SoM or EOP" in the older sense.
    27|- The real live path is now "meta-router classification/control plane -> SoM v3 main execution -> optional ADV_PASS hardening pass".
    28|- That means the meta-router still has a purpose, but it is narrower than earlier documents implied.
    29|- The biggest current problem is not conceptual elegance. It is learning-plane contamination and promotion/gating discipline.
    30|
    31|## Executive Summary
    32|
    33|The architectural direction is mostly correct: SoM v3.1 is now the primary work engine, while EOP survives mostly as evidence/ADV_PASS discipline. That simplification is good. It reduces duplicated orchestration and matches current agent-design guidance that simpler composable systems are usually more reliable than complicated routers.
    34|
    35|However, the current live MR-ALS stack has several critical gaps:
    36|
    37|- Production learning data is mixed with test and e2e rows.
    38|- The active candidate appears promoted ahead of evidence maturity.
    39|- Optimizer and analytics artifacts do not appear to enforce strong dataset hygiene.
    40|- Status and readiness claims are ahead of the actual evidence volume.
    41|- The naming and documentation still reflect an old "SoM vs EOP router" model that is no longer the actual runtime model.
    42|- The evidence contract is producing invalid evidence outcomes that should not be allowed to train or promote anything.
    43|
    44|The most important recommendation is to keep the meta-router, but narrow and harden its role:
    45|
    46|- Keep it as ingress classification, control policy, enforcement, telemetry, and adaptive-selection infrastructure.
    47|- Stop treating it conceptually as a content-reasoning engine that competes with SoM.
    48|- Make learning/promotion decisions only on clean, partitioned, outcome-valid data.
    49|
    50|## Current Architecture Clarification
    51|
    52|## What the live runtime is doing now
    53|
    54|Live inspection on 2026-04-15 showed the following practical flow in Hermes:
    55|
    56|1. `run_agent.py` invokes the meta-router before the main turn.
    57|2. The meta-router classifies the incoming request and injects routing metadata like `[META-ROUTER | type | mode]`.
    58|3. SoM Phase 1 then runs as the main reasoning scaffold.
    59|4. After the main turn, SoM Phase 2 runs.
    60|5. For relevant task classes such as `code`, `audit`, `production`, and `integration`, an `ADV_PASS` can run after SoM as an adversarial/evidence hardening layer.
    61|
    62|That means the current live system is not really doing "choose SoM or choose EOP" in the older sense. It is doing:
    63|
    64|`meta-router -> SoM -> optional ADV_PASS`
    65|
    66|This is important because some earlier planning language still implies a two-framework content router where SoM and EOP are peer alternatives. That is no longer the best description of the live system.
    67|
    68|## What the meta-router is still for
    69|
    70|The meta-router still has a legitimate role even after SoM v3 absorbed most of EOP:
    71|
    72|- classify the task at ingress
    73|- set orchestration mode and enforcement policy
    74|- inject structured control metadata
    75|- collect experience and outcome telemetry
    76|- manage adaptive routing/deployment artifacts
    77|- enforce promotion and rollback policy
    78|- support future abstain/clarify/escalate policies
    79|
    80|So the correct question is not "why keep the meta-router if SoM does the main work?" The correct question is "what should the meta-router own now that SoM is the main work engine?"
    81|
    82|The answer is:
    83|
    84|- The meta-router should own control-plane responsibilities.
    85|- SoM should own most content-level reasoning and task decomposition.
    86|- ADV_PASS should own hardening/evidence challenge on the subset of tasks where that is warranted.
    87|
    88|## Why this direction is strategically sound
    89|
    90|This aligns with external agent-systems guidance:
    91|
    92|- Anthropic's guidance on effective agents argues for using simple composable patterns instead of unnecessary orchestration complexity.
    93|- Meta-Harness emphasizes improving the harness, preserving high-fidelity execution traces, and evaluating changes against fixed criteria instead of loosely changing many moving parts at once.
    94|- Karpathy's `autoresearch` repo leans toward simple measurable loops, narrow mutable surfaces, and strong baseline discipline.
    95|
    96|So the SoM-centric simplification is not the problem. The problem is that the live adaptive-learning plane has not yet fully caught up to the simplified execution model.
    97|
    98|## Live-State Findings From 2026-04-15
    99|
   100|All findings below are based on live inspection of the Hermes VM and the current adaptive-routing artifacts.
   101|
   102|## Finding 1: The experience plane is contaminated by tests
   103|
   104|Observed evidence:
   105|
   106|- `routing_events.jsonl` had 127 rows.
   107|- Event source counts included:
   108|  - `cli`: 79
   109|  - `e2e-test`: 21
   110|  - `t`: 18
   111|  - `api`: 6
   112|  - `e2e-multiplier-test`: 2
   113|  - `test`: 1
   114|- Surface counts included:
   115|  - `cli`: 121
   116|  - `http`: 6
   117|
   118|Why this matters:
   119|
   120|- A learning system cannot safely optimize on production behavior if its event plane is mixing production interactions with e2e harness traffic and ad hoc test traffic.
   121|- This contaminates difficulty priors, route frequencies, confidence estimates, and promotion decisions.
   122|- It also makes artifact summaries look healthier than they really are because "lots of events" may not mean "lots of production-grade outcomes."
   123|
   124|Correction required:
   125|
   126|- Introduce explicit dataset partitioning and learning eligibility flags.
   127|- Test traffic must be stored, but must not silently enter promotion or optimizer datasets.
   128|
   129|## Finding 2: Outcome volume is far too small relative to the claims being made
   130|
   131|Observed evidence:
   132|
   133|- `routing_outcomes.jsonl` had only 4 rows.
   134|- Three of the four rows were obviously test-related:
   135|  - `test-rid-123`
   136|  - `rid-test-append`
   137|  - `rid-test-phase2`
   138|- Only one row looked plausibly non-test:
   139|  - `3f70bcaf-bc8c-49cd-99fa-433e17e448c5`
   140|
   141|Why this matters:
   142|
   143|- An adaptive-routing system should not sound production-confident when its true outcome set is this small.
   144|- Four outcomes, with most apparently synthetic, is not enough to justify strong candidate claims, reliable confidence calibration, or meaningful skill/model insights.
   145|
   146|Correction required:
   147|
   148|- Tighten readiness language.
   149|- Block candidate promotion unless minimum genuine outcome thresholds are met.
   150|- Separate "telemetry alive" from "learning mature."
   151|
   152|## Finding 3: The active candidate appears ahead of evidence maturity
   153|
   154|Observed evidence:
   155|
   156|- `deployment_state.json` contained:
   157|  - `active_candidate_id: "candidate-0002"`
   158|  - `previous_candidate_id: "static-default"`
   159|  - `rollout_mode: null`
   160|  - `last_rollout_result: null`
   161|- `candidate-0002.json` showed:
   162|  - strategy: `audit-prod-premium-v1`
   163|  - `promoted_at: null`
   164|  - `pareto_score: 0.8844`
   165|  - `shadow_eval_n: 20`
   166|  - `gate_passes: true`
   167|- `pareto_frontier.json` showed:
   168|  - `frontier: ["candidate-0002"]`
   169|  - `baseline_candidate_id: "baseline-0001"`
   170|  - `total_candidates_evaluated: 3`
   171|- The same frontier artifact still notes that Phase 4 has not really started and that at least 50 outcome-enriched events are needed.
   172|
   173|Why this matters:
   174|
   175|- The system is simultaneously signaling "candidate-0002 is active" and "we do not yet have enough outcome-enriched data."
   176|- The presence of an active candidate with null rollout metadata creates audit ambiguity.
   177|- If a candidate is active because of shadow/bootstrap evidence only, that should be stated explicitly and durably in the artifact schema.
   178|
   179|Correction required:
   180|
   181|- Add explicit promotion lineage fields.
   182|- Record whether activation is shadow-only, canary, manual, or full production.
   183|- Consider reverting to baseline or freezing promotion until clean evidence thresholds are met.
   184|
   185|## Finding 4: Status claims and analytics artifacts are drifting out of sync
   186|
   187|Observed evidence:
   188|
   189|- `STATUS.md` reported many components as live:
   190|  - routing live
   191|  - enforcement live
   192|  - experience logging live
   193|  - outcome enrichment live
   194|  - deployment artifact live
   195|  - optimizer live
   196|  - pareto frontier live
   197|  - shadow eval live
   198|  - model learning live
   199|  - skill learning live
   200|- But `model_insights.json` still reported:
   201|  - `n_outcomes: 1`
   202|  - `n_events: 6`
   203|  - `shadow_set_size: 20`
   204|- `skills_performance.json` was generated from only `n_total_outcomes: 1`
   205|- Most skill/task categories were still effectively `no_data`
   206|
   207|Why this matters:
   208|
   209|- The instrumentation may be live, but the learning products are not yet mature.
   210|- Operators and future agents can be misled if "live" is read as "trustworthy for adaptation."
   211|- Freshness and data sufficiency are first-class operational states and should not be hidden behind a binary live/not-live label.
   212|
   213|Correction required:
   214|
   215|- Replace overly coarse live-status reporting with freshness and sufficiency reporting.
   216|- Example dimensions:
   217|  - pipeline alive
   218|  - last successful write
   219|  - eligible production outcomes count
   220|  - promotion-ready yes/no
   221|  - confidence-calibrated yes/no
   222|
   223|## Finding 5: The optimizer path does not appear to enforce robust dataset hygiene
   224|
   225|Observed evidence:
   226|
   227|- `optimize_weights.py` uses:
   228|  - `MIN_OUTCOMES = 50`
   229|  - shadow bootstrap from `shadow_eval_set.json`
   230|  - live data from `routing_outcomes.jsonl`
   231|- During inspection, no robust filtering was found for:
   232|  - test/e2e sources
   233|  - classification-only events
   234|  - invalid evidence rows
   235|  - session provenance tiers
   236|
   237|Why this matters:
   238|
   239|- Even if the optimizer has a minimum threshold, it still needs strict eligibility rules for what counts toward optimization.
   240|- Otherwise the system can "learn" from rows that should have been retained only for audit, debugging, or synthetic eval tracking.
   241|
   242|Correction required:
   243|
   244|- Make optimizer eligibility explicit and centralized.
   245|- Reject or quarantine rows unless they satisfy all required conditions.
   246|
   247|## Finding 6: The evidence contract is not yet strong enough
   248|
   249|Observed evidence:
   250|
   251|- Recent outcome rows showed:
   252|  - `evidence_valid = false`
   253|  - empty `hypothesis.json`
   254|  - empty evidence items
   255|  - `adv_pass_clean = false`
   256|  - `adv_findings = 2`
   257|
   258|Why this matters:
   259|
   260|- If evidence is invalid and ADV_PASS fails, the row should not silently behave like normal adaptive-learning fuel.
   261|- Otherwise the system will reward incomplete or weakly evidenced executions.
   262|- This is especially risky because the whole point of SoM+ADV discipline is to improve correctness and robustness under uncertainty.
   263|
   264|Correction required:
   265|
   266|- Invalid-evidence rows must be explicitly excluded from positive learning and promotion signals.
   267|- They should instead feed a separate failure-analysis dataset.
   268|
   269|## Finding 7: OpenClaw parity is still incomplete
   270|
   271|Observed evidence:
   272|
   273|- `STATUS.md` still reports:
   274|  - `openclaw_plugin_loaded: true`
   275|  - `openclaw_shared_stream_live: false`
   276|- Event sources did not show the expected OpenClaw shared-stream parity.
   277|
   278|Why this matters:
   279|
   280|- The system currently claims a broader routing/learning fabric than it actually has.
   281|- If OpenClaw is part of the product story, then it needs either real parity or explicit scoping language that says parity is not yet live.
   282|
   283|Correction required:
   284|
   285|- Either finish shared-stream integration or downgrade claims until it is real.
   286|
   287|## Finding 8: Documentation language still reflects the older architecture
   288|
   289|Observed evidence:
   290|
   291|- Earlier reports and planning artifacts describe the meta-router as routing between SoM and EOP as if they are still co-equal content frameworks.
   292|- Live runtime inspection shows that SoM now does the main work and EOP survives mainly as ADV_PASS/evidence discipline.
   293|
   294|Why this matters:
   295|
   296|- Documentation drift creates design drift.
   297|- Future optimization work becomes confused if the written mental model does not match the runtime model.
   298|- It also makes wrong fixes more likely, such as trying to restore a two-framework router that is no longer necessary.
   299|
   300|Correction required:
   301|
   302|- Rewrite the architectural narrative around:
   303|  - control plane
   304|  - main reasoning plane
   305|  - hardening/evidence plane
   306|
   307|## Is the Meta-Router Still Necessary?
   308|
   309|Yes, but in a more constrained role.
   310|
   311|It should not be justified as "the thing that chooses between two major reasoning frameworks" unless that is truly restored and made explicit again.
   312|
   313|It should be justified as:
   314|
   315|- task ingress classifier
   316|- orchestration-policy selector
   317|- enforcement and telemetry controller
   318|- adaptive deployment and rollback manager
   319|- future abstain/clarify/escalate gate
   320|
   321|If the meta-router is not used for those control-plane functions, then it becomes redundant. But as long as the system wants adaptive policy selection, telemetry-backed deployment, and multi-mode enforcement, the meta-router still has a real purpose.
   322|
   323|## Corrections and Recommendations
   324|
   325|## Priority 0: Stop contaminated data from influencing learning
   326|
   327|Actions:
   328|
   329|- Add explicit fields such as:
   330|  - `dataset_partition`
   331|  - `event_origin`
   332|  - `learning_eligible`
   333|  - `outcome_eligible`
   334|  - `evidence_eligible`
   335|  - `classification_only`
   336|- Default all synthetic, e2e, manual-test, replay, and debugging rows to `learning_eligible = false`.
   337|- Require explicit opt-in for any row to enter optimizer or promotion datasets.
   338|
   339|Reason:
   340|
   341|- This is the most dangerous current gap because it can silently poison every adaptive artifact downstream.
   342|
   343|Likely file targets:
   344|
   345|- `~/.hermes/hermes-agent/gateway/meta_router.py`
   346|- `~/.hermes/hermes-agent/gateway/meta_router_runtime.py`
   347|- `~/.hermes/hermes-agent/gateway/meta_router_executor.py`
   348|- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/optimize_weights.py`
   349|- any artifact writers for `routing_events.jsonl` and `routing_outcomes.jsonl`
   350|
   351|## Priority 1: Rework promotion semantics and candidate lineage
   352|
   353|Actions:
   354|
   355|- Do not allow an active candidate to exist without explicit activation metadata.
   356|- Record:
   357|  - activation reason
   358|  - activation source
   359|  - activation date
   360|  - evaluation basis
   361|  - rollout mode
   362|  - rollback condition
   363|- Add promotion gates that require:
   364|  - minimum clean production outcomes
   365|  - minimum clean evidence-valid outcomes
   366|  - minimum calibration quality
   367|  - minimum canary duration if applicable
   368|
   369|Reason:
   370|
   371|- `candidate-0002` currently appears more "active" than "accountably promoted."
   372|
   373|Likely file targets:
   374|
   375|- deployment artifact writers
   376|- frontier selection logic
   377|- `load_active_routing.py`
   378|- any rollout/promotion command or skill scripts
   379|
   380|## Priority 2: Split learning products into shadow, production, and failure-analysis planes
   381|
   382|Actions:
   383|
   384|- Maintain three clearly separated views:
   385|  - shadow eval performance
   386|  - production adaptive-learning performance
   387|  - failure-analysis corpus
   388|- Invalid evidence rows and failed ADV_PASS rows should land in the failure-analysis view, not the main adaptive-learning pool.
   389|
   390|Reason:
   391|
   392|- This preserves useful information without contaminating route optimization.
   393|
   394|## Priority 3: Make status artifacts honest about maturity
   395|
   396|Actions:
   397|
   398|- Replace binary live flags with richer readiness indicators.
   399|- Add fields such as:
   400|  - `last_event_ingest_at`
   401|  - `last_clean_outcome_at`
   402|  - `eligible_production_outcomes`
   403|  - `optimizer_ready`
   404|  - `promotion_ready`
   405|  - `calibration_ready`
   406|  - `shared_stream_ready`
   407|
   408|Reason:
   409|
   410|- "Live" is not enough. The operator needs to know whether the system is merely emitting files or whether it is safe to adapt on the resulting data.
   411|
   412|## Priority 4: Align docs and naming with the live architecture
   413|
   414|Actions:
   415|
   416|- Retire or annotate old "SoM vs EOP router" language.
   417|- Replace it with:
   418|  - meta-router = control plane
   419|  - SoM = primary reasoning/execution plane
   420|  - ADV_PASS = hardening/evidence challenge layer
   421|- Audit skill docs, STATUS docs, and PRD text for outdated architecture claims.
   422|
   423|Reason:
   424|
   425|- This will prevent future agents from implementing the wrong thing.
   426|
   427|## Priority 5: Add abstain/clarify handling for ambiguous prompts
   428|
   429|Actions:
   430|
   431|- Introduce a low-confidence or multi-intent route that can request clarification or enter a safer audit-first mode.
   432|- Do not force every input into a confident task bucket when the router is uncertain.
   433|
   434|Reason:
   435|
   436|- A strong meta-router should improve safety and efficiency at ingress, not just decorate the prompt.
   437|
   438|## Priority 6: Decide the truth about OpenClaw integration
   439|
   440|Actions:
   441|
   442|- Either complete the shared-stream integration and verify OpenClaw events appear in the same adaptive plane, or explicitly mark the parity work as not yet live.
   443|
   444|Reason:
   445|
   446|- Architectural truthfulness matters for both operations and future development.
   447|
   448|## Recommended Hermes Execution Sequence
   449|
   450|Hermes should implement the corrections in this order:
   451|
   452|1. Trace how `routing_events.jsonl` and `routing_outcomes.jsonl` are written.
   453|2. Add hard dataset partitioning and eligibility filtering.
   454|3. Patch the optimizer so only eligible clean production outcomes are used.
   455|4. Patch candidate activation/promotion artifacts so activation lineage is explicit.
   456|5. Recompute or regenerate `model_insights.json`, `skills_performance.json`, and frontier artifacts from clean data only.
   457|6. Reclassify current state honestly:
   458|   - if necessary, demote or freeze `candidate-0002`
   459|   - keep bootstrap/shadow evidence, but stop overstating production maturity
   460|7. Update docs and status reporting to reflect the real `meta-router -> SoM -> ADV_PASS` architecture.
   461|8. Decide whether OpenClaw parity will be completed now or downgraded in claims.
   462|
   463|## What Hermes Should Not Do
   464|
   465|Hermes should not:
   466|
   467|- restore an older two-framework "SoM or EOP" router unless there is a deliberate new design decision to do so
   468|- let test/e2e rows count toward adaptive learning or promotion
   469|- treat invalid-evidence rows as normal successful learning outcomes
   470|- preserve misleading readiness language just because the plumbing technically emits files
   471|
   472|## Source Notes
   473|
   474|## Internal sources reviewed
   475|
   476|- `reports/2026-04-05-adaptive-learning-and-agent-harnesses.md`
   477|- `reports/2026-04-05-meta-router-adaptive-learning-prd.md`
   478|- `reports/2026-04-06-meta-router-als-integration-plan.md`
   479|- `reports/2026-04-06-mr-als-final-production-readiness-report.md`
   480|- `reports/2026-04-07-meta-router-als-execution-tracker.md`
   481|- `reports/2026-04-07-meta-router-als-reality-based-prd.md`
   482|- `reports/2026-04-07-som-v3-implementation-report.md`
   483|- `reports/2026-04-10-meta-router-somv3-als-adversarial-audit.md`
   484|- `reports/2026-04-14-meta-router-memory-authority-reconciliation/03-follow-up-live-state-2026-04-15.md`
   485|- `resources/EOP_V2.1_POST_IMPLEMENTATION_REVIEW.md`
   486|
   487|## Live VM files inspected on 2026-04-15
   488|
   489|- `~/.hermes/hermes-agent/run_agent.py`
   490|- `~/.hermes/hermes-agent/gateway/meta_router.py`
   491|- `~/.hermes/hermes-agent/gateway/meta_router_runtime.py`
   492|- `~/.hermes/hermes-agent/gateway/meta_router_executor.py`
   493|- `~/.openclaw/workspace/skills/maintainer/meta-router/STATUS.md`
   494|- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/optimize_weights.py`
   495|- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/load_active_routing.py`
   496|- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/*`
   497|- `~/.openclaw/workspace/skills/som/SKILL.md`
   498|
   499|## External references