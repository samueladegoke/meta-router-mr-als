# Meta-Router

This directory contains the Hermes-side Meta-Router integration extracted from the live system.

Included files
- `meta_router.py` — classifier rules and routing logic
- `meta_router_runtime.py` — shared runtime decision path and bypass semantics
- `meta_router_server.py` — HTTP `/classify` service on port 3120
- `meta_router_executor.py` — SoM / ADV_PASS bridge and routed delivery handling
- test files covering runtime, server, delivery, and Telegram parity

Current verified behavior
- shared ingress routing for Hermes
- receipt-based delivery reporting
- explicit score-gate reporting
- threshold-only blocked delivery explanation
