# MR-ALS

This directory contains the adaptive-learning and status-sync side of the Meta-Router stack.

Included files
- `log_writer.py` — shared event/outcome writer
- `experience_hygiene.py` — source partitioning and learning eligibility rules
- `optimize_weights.py` — optimizer using eligible outcome rows
- `load_active_routing.py` — deployment artifact loader and promotion metadata
- `shadow_eval.py` — shadow/canary evaluation
- `model_learner.py` — outcome-derived model insights
- `skill_learner.py` — task-type performance summaries
- `plugin_sync.py` — honest runtime/status artifact generation
- tests covering hygiene, honesty, and promotion metadata

Current verified behavior
- raw vs eligible outcomes separated
- promotion readiness tracked explicitly
- shadow-only activation state recorded for `candidate-0002`
- status files report learning maturity honestly
