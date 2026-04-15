# meta-router-mr-als

Standalone sync repo for the Meta-Router and MR-ALS frameworks extracted from the live Hermes/OpenClaw workspace.

Repository layout
- `meta-router/` — Hermes-side routing runtime, server, executor bridge, and regression tests
- `mr-als/` — adaptive-learning scripts, status sync, reconciliation tooling, and regression tests
- `docs/` — remediation and portability notes

Current exported state
- active candidate: `candidate-0010`
- rollout mode: `shadow`
- evidence maturity: `shadow-only`
- eligible outcome-enriched production rows: `19`
- openclaw plugin routed rows: `5`
- hard maturity gate: `50 eligible outcomes`

This repo is meant as a shareable reference extraction. It is not yet a fully packaged standalone product.
