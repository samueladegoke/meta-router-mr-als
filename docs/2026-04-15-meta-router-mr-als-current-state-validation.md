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
     9|# Meta-Router + MR-ALS Current-State Validation
    10|
    11|Date: 2026-04-15  
    12|Validated at: 2026-04-15 18:29 UTC  
    13|Scope: live VM validation of the Hermes meta-router runtime and the OpenClaw MR-ALS workspace after the 2026-04-15 remediation work.
    14|
    15|## Executive summary
    16|
    17|This pass re-ran the live validation surface for both frameworks and then updated the report set so older PRDs and audits no longer read like current-state truth.
    18|
    19|The validated current state is:
    20|
    21|- Hermes meta-router is live and healthy.
    22|- The live execution model is still `meta-router -> SoM -> optional ADV_PASS`.
    23|- Routed Hermes CLI delivery gating is working in both directions:
    24|  - a passing task was delivered with a receipt and score-gate PASS
    25|  - an under-threshold draft was blocked even though Oracle and ADV_PASS both passed
    26|- MR-ALS runtime status is live but still bootstrap-constrained:
    27|  - `candidate-0002` is active
    28|  - rollout mode is `shadow`
    29|  - `promotion_ready` is `false`
    30|  - only `4` eligible outcome-enriched production rows exist against a `50`-row maturity target
    31|- During validation, one real MR-ALS regression was found and fixed:
    32|  - several Phase 4/5/6 scripts failed when invoked with system `python3`
    33|  - root cause: they imported `gateway.meta_router`, which dragged in the full Hermes package tree and required PyYAML from the Hermes venv
    34|  - fix: load the live Hermes `meta_router.py` rules directly by file path via a new helper, and add script-level CLI smoke tests
    35|
    36|Bottom line: the tested Hermes meta-router and MR-ALS paths are working as expected after the fix above. The remaining limitation is not a breakage in the tested path; it is maturity. The learning plane is still bootstrap-only, not promotion-ready.
    37|
    38|## Canonical current-state references
    39|
    40|Use these as the live truth anchors before trusting older reports:
    41|
    42|- `reports/2026-04-15-meta-router-mr-als-current-state-validation.md` — this validation report
    43|- `~/.openclaw/workspace/skills/maintainer/meta-router/STATUS.md` — canonical live MR-ALS status file
    44|- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/plugin_report.json` — machine-readable live state summary
    45|- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/model_insights.json`
    46|- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/skills_performance.json`
    47|- `~/.openclaw/workspace/skills/maintainer/meta-router/experience/deployment_state.json`
    48|
    49|## Verified current state
    50|
    51|### Hermes meta-router runtime
    52|
    53|Verified live:
    54|
    55|- `meta-router.service` was active
    56|- `http://127.0.0.1:3120/health` returned `{"status":"ok","version":"2.0.0"}`
    57|- classify returned a directive successfully during this pass
    58|- the shared Hermes tests still passed after re-validation
    59|
    60|Verified behavior:
    61|
    62|- the system still classifies first and routes through the shared runtime
    63|- the live path remains `meta-router -> SoM -> optional ADV_PASS`
    64|- receipt persistence and threshold-aware delivery messaging remain working
    65|
    66|### Hermes routed end-to-end checks
    67|
    68|Two routed CLI checks were re-run:
    69|
    70|1. Passing flow
    71|- Prompt: `safe_divide(...)` implementation request with type hints, docstring, assertions, and verified-at-runtime section
    72|- Result:
    73|  - `RQL Score: 70/100 (ACCEPTABLE)`
    74|  - `threshold 65`
    75|  - `Score gate: PASS`
    76|  - `Oracle: PASS`
    77|  - `ADV_PASS: PASS (0 findings)`
    78|- Delivery artifact:
    79|  - `~/.openclaw/workspace/rql/state/write-a-python-function-safe-d-1b9b/delivery.json`
    80|
    81|2. Threshold-blocked flow
    82|- Prompt: `Return only the shortest possible Python multiply(a, b) function. No explanation.`
    83|- Result:
    84|  - `RQL Score: 46/100 (NEEDS_WORK)`
    85|  - `threshold 65`
    86|  - `Score gate: FAIL`
    87|  - `Oracle: PASS`
    88|  - `ADV_PASS: PASS (0 findings)`
    89|  - final delivery correctly blocked
    90|- Delivery artifact:
    91|  - `~/.openclaw/workspace/rql/state/return-only-the-shortest-possi-1c06/delivery.json`
    92|
    93|This confirms the earlier delivery-honesty fix is still working.
    94|
    95|### MR-ALS live status after re-validation
    96|
    97|From `STATUS.md` and `plugin_report.json` after re-running plugin sync:
    98|
    99|- `routing_live: true`
   100|- `enforcement_live: true`
   101|- `experience_logging_live: true`
   102|- `outcome_enrichment_live: true`
   103|- `learning_data_live: true`
   104|- `learning_data_mature: false`
   105|- `deployment_artifact_live: true`
   106|- `optimizer_live: true`
   107|- `pareto_frontier_live: true`
   108|- `shadow_eval_live: true`
   109|- `model_learning_live: true`
   110|- `skill_learning_live: true`
   111|- `promotion_ready: false`
   112|- `openclaw_plugin_loaded: true`
   113|- `openclaw_shared_stream_live: true`
   114|
   115|Current counts:
   116|
   117|- `routing_events.jsonl`: 177
   118|- `routing_outcomes.jsonl`: 19
   119|- eligible outcome-enriched production rows: 4
   120|- candidate artifacts: 3
   121|- evaluated candidates: 3
   122|- Pareto frontier members: 2
   123|- `openclaw-plugin` event rows in the canonical event stream: 1
   124|
   125|Deployment accountability:
   126|
   127|- `active_candidate_id: candidate-0002`
   128|- `rollout_mode: shadow`
   129|- `evidence_maturity: shadow-only`
   130|- `promotion_ready: false`
   131|
   132|## Validation work run in this pass
   133|
   134|### Hermes checks
   135|
   136|Service and runtime checks:
   137|- `systemctl --user is-active meta-router.service`
   138|- `curl -fsS http://127.0.0.1:3120/health`
   139|- classify POST against `http://127.0.0.1:3120/classify`
   140|- `script -q -c "openclaw plugins inspect meta-router" /dev/null`
   141|
   142|Hermes regression suite:
   143|- `/home/samade10/.hermes/venv/bin/python -m pytest tests/gateway/test_meta_router_runtime.py tests/gateway/test_meta_router_server.py tests/gateway/test_meta_router_delivery.py tests/gateway/test_telegram_meta_router.py tests/hermes_cli/test_doctor.py -q -o addopts=''`
   144|- result: `29 passed, 1 warning`
   145|
   146|Compile checks:
   147|- `python3 -m py_compile` on the touched Hermes meta-router files
   148|
   149|Hermes routed E2E:
   150|- `hermes chat -Q --source mr-doc-audit -q 'Write a Python function safe_divide(...)'`
   151|- `hermes chat -Q --source mr-doc-audit -q 'Return only the shortest possible Python multiply(a, b) function. No explanation.'`
   152|
   153|### MR-ALS checks
   154|
   155|Workspace regression suite:
   156|- `/home/samade10/.hermes/venv/bin/python -m pytest skills/maintainer/meta-router/tests -q`
   157|- result after adding the new smoke tests and fixing the script loader path: `13 passed`
   158|
   159|MR-ALS script execution with system `python3`:
   160|- `python3 shadow_eval.py --all`
   161|- `python3 pareto_manager.py --rebuild`
   162|- `python3 optimize_weights.py --dry-run`
   163|- `python3 model_learner.py --report`
   164|- `python3 skill_learner.py --report`
   165|- `python3 plugin_sync.py --report`
   166|
   167|Observed outputs of note:
   168|- `shadow_eval.py --all`
   169|  - baseline accuracy: `90.0%`
   170|  - `candidate-0002`: PASS
   171|  - `candidate-0001`: PASS
   172|  - `candidate-0003`: FAIL
   173|- `pareto_manager.py --rebuild`
   174|  - frontier: `candidate-0002`, `candidate-0003`
   175|- `optimize_weights.py --dry-run`
   176|  - raw outcomes: `19`
   177|  - eligible outcomes: `4`
   178|  - mode: `bootstrap`
   179|- `model_learner.py --report`
   180|  - still flags `production` as the weakest type on the shadow set because it is frequently confused with `integration`
   181|- `skill_learner.py --report`
   182|  - eligible data currently covers only `code`; other task types still show `no_data`
   183|- `plugin_sync.py --report`
   184|  - regenerated `STATUS.md` and `plugin_report.json` with the current counts above
   185|
   186|## Regression found and fixed in this pass
   187|
   188|### Issue
   189|
   190|Several MR-ALS scripts failed when run with system `python3`:
   191|
   192|- `shadow_eval.py`
   193|- `optimize_weights.py`
   194|- `model_learner.py`
   195|
   196|Observed failure shape:
   197|- importing `gateway.meta_router` pulled in the full Hermes package tree
   198|- the system interpreter then hit `ModuleNotFoundError: No module named 'yaml'`
   199|- after moving to direct file loading, a dataclass/module-registration edge case also surfaced and was fixed by registering the loaded module in `sys.modules` before execution
   200|
   201|### Root cause
   202|
   203|The MR-ALS scripts were written with `#!/usr/bin/env python3`, but their rules loader depended on importing the Hermes package as a package, not just the live `meta_router.py` rule definitions. That made the scripts accidentally depend on the Hermes venv instead of being truly portable under system `python3`.
   204|
   205|### Fix applied
   206|
   207|New helper added:
   208|- `~/.openclaw/workspace/skills/maintainer/meta-router/scripts/meta_router_rules.py`
   209|
   210|Patched scripts:
   211|- `scripts/shadow_eval.py`
   212|- `scripts/optimize_weights.py`
   213|- `scripts/model_learner.py`
   214|
   215|Tests added/updated:
   216|- `tests/test_script_cli_entrypoints.py` — safe subprocess smoke tests for the CLI entrypoints under system `python3`
   217|- `tests/test_optimizer_and_status_honesty.py` — updated monkeypatch target after the loader refactor
   218|
   219|Validation after fix:
   220|- new smoke suite passed: `6 passed`
   221|- full workspace suite passed: `13 passed`
   222|- the previously failing scripts all executed successfully with system `python3`
   223|
   224|## What is working now
   225|
   226|Working and verified in this pass:
   227|
   228|- Hermes meta-router health and classify endpoint
   229|- shared Hermes runtime tests
   230|- Hermes routed delivery pass/fail honesty
   231|- MR-ALS workspace tests
   232|- MR-ALS script execution under system `python3`
   233|- shadow evaluation, Pareto rebuild, learning reports, and plugin sync regeneration
   234|
   235|## What is still not mature
   236|
   237|These are not new breakages. They are current-state maturity limits:
   238|
   239|1. Learning plane maturity is still below threshold.
   240|- eligible outcomes: `4`
   241|- maturity target: `50`
   242|- result: `learning_data_mature=false`
   243|
   244|2. Promotion readiness is still intentionally blocked.
   245|- `candidate-0002` is active in `shadow` mode
   246|- `promotion_ready=false`
   247|- `evidence_maturity=shadow-only`
   248|
   249|3. Coverage across task types is still thin.
   250|- eligible learning data is currently concentrated in `code`
   251|- `audit`, `research`, `production`, `integration`, `config`, and `design` remain `no_data` in `skills_performance.json`
   252|
   253|4. Model learner still sees one clear routing weakness.
   254|- `production` remains the weakest shadow-set type because it is confused with `integration`
   255|
   256|## Adjacent caveat outside the primary fix set
   257|
   258|An optional attempt to generate a fresh OpenClaw-driven plugin event via `openclaw agent` did not succeed in this pass.
   259|
   260|Observed blockers on that adjacent path included:
   261|- gateway pairing requirement on the loopback gateway path
   262|- provider/network failures after fallback to embedded mode
   263|- an OpenClaw main-session lock conflict on one local-agent attempt
   264|
   265|Important interpretation:
   266|- this does **not** invalidate the Hermes meta-router or MR-ALS results above
   267|- it does mean that this pass did not freshly re-prove new plugin-emitted shared-stream rows end-to-end
   268|- the `openclaw_shared_stream_live=true` status still rests on the existing canonical event-plane evidence (`openclaw-plugin` row present) plus plugin-load verification, not a brand-new plugin-produced row from this pass
   269|
   270|## Report-set writeback decision
   271|
   272|Older meta-router / MR-ALS reports in `reports/` were updated with a current-state banner pointing to this report and to `STATUS.md` so older snapshots stop reading as current operational truth.
   273|
   274|Interpretation rule going forward:
   275|- older reports remain valuable as design history, audits, and remediation context
   276|- for current machine state, defer first to:
   277|  - this report
   278|  - `STATUS.md`
   279|  - the machine-readable `plugin_report.json`
   280|
   281|## Final judgment
   282|
   283|Within the tested scope, there are no newly uncovered unresolved failures in the Hermes meta-router or MR-ALS runtime after the fixes applied in this pass.
   284|
   285|The current limitation is maturity, not breakage:
   286|- the control plane is live
   287|- delivery gating is honest
   288|- telemetry is live
   289|- adaptive artifacts are live
   290|- script entrypoints now work under system `python3`
   291|- but the learning dataset is still bootstrap-scale and promotion remains correctly blocked