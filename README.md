# meta-router-mr-als

Standalone sync repo for the Meta-Router and MR-ALS frameworks extracted from the live Hermes/OpenClaw workspace.

Repository layout
- `meta-router/` — Hermes-side routing runtime, server, executor bridge, and regression tests
- `mr-als/` — adaptive-learning scripts, log writer, status sync, and regression tests
- `docs/` — the critical-gaps remediation report used for the hardening pass

Current exported state
- active candidate: `candidate-0002`
- rollout mode: `shadow`
- evidence maturity: `shadow-only`
- eligible outcome-enriched production rows: `3`

Important caveat
- These files are synced as extracted from the live system and still contain local-path assumptions and Hermes/OpenClaw integration details.
- They are shareable as reference implementations, but not yet packaged as a standalone installable framework.
