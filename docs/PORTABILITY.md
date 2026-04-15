# Portability Notes

These files are extracted from a live Hermes/OpenClaw deployment and are not yet packaged as a standalone framework.

Current assumptions
- hard-coded local paths under `/home/samade10/...`
- Hermes/OpenClaw repo layout already exists
- SoM / ADV_PASS / RQL scripts are available locally
- some status generation expects the live experience-plane JSONL files

Before external reuse
- parameterize paths via env vars or config files
- add install/setup instructions
- define a standalone config schema
- separate framework code from environment-specific artifacts
- add CI and packaging metadata
