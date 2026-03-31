# Vizier Pro-Max

Global rules (Python, immutability, testing, git, security, halal) apply.

## Architecture
- **Spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-01-gate-1-implementation.md`
- **Foundation:** Hermes Agent v0.6.0 at ~/hermes-agent/
- **Model:** GPT-5.4-mini (free 10M/day) via Hermes
- **Registry API:** ~/hermes-agent/tools/registry.py

## Conventions
- Manifests in `manifests/{workflow}/` — YAML, one per tool
- Scripts in `scripts/{workflow}/` — stable Python executables
- Pipelines in `pipelines/` — collapsed deterministic sequences
- Bridge in `bridge/` — Claude Code <-> Vizier awareness
- Custom Hermes tools in `tools/` — registered via registry.register()
- Hermes lifecycle hooks in `plugins/` — NOT tools
- Test files mirror source: `adapter/loader.py` -> `tests/adapter/test_loader.py`

## No litellm. Ever.
Supply chain compromise confirmed. Use direct provider SDKs via Hermes.
