# Vizier Pro-Max

Global rules (Python, immutability, testing, git, security, halal) apply.

## Architecture
- **Spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`
- **Plan:** `docs/superpowers/plans/2026-04-01-gate-1-implementation.md`
- **Foundation:** Hermes Agent v0.6.0 as git submodule at `./hermes-agent/` (fork: khayroul/hermes-agent, branch: vizier-gate2-patch)
- **Model:** GPT-5.4-mini via OpenAI API (OPENAI_API_KEY), Qwen 3.5 9B via Ollama as fallback
- **Registry API:** `./hermes-agent/tools/registry.py`

## Conventions
- Manifests in `manifests/{workflow}/` — YAML, one per tool
- Scripts in `scripts/{workflow}/` — stable Python executables
- Pipelines in `pipelines/` — collapsed deterministic sequences
- Bridge in `bridge/` — Codex <-> Vizier awareness
- Custom Hermes tools in `tools/` — registered via registry.register()
- Hermes lifecycle hooks in `plugins/` — NOT tools
- Test files mirror source: `adapter/loader.py` -> `tests/adapter/test_loader.py`

## No litellm. Ever.
Supply chain compromise confirmed. Use direct provider SDKs via Hermes.

## Ported from Vizier Ultimate (2 April 2026)

- 30 visual templates in `templates/visual/` (8 design patterns x 3 aspect ratios + 6 specials)
- Stock hero catalog in `templates/visual/stock-heroes.json`
- 6 document templates in `templates/documents/` (article, ebook-chapter, invoice, one-pager, proposal, report)
- 2 Typst templates in `templates/typst/` (ebook, long-report)
- Listening engine in `augments/listening/` (5 social sources + 2 ads library adapters)
- Assembly tools: PDF (`weasyprint`), EPUB (`ebooklib`), PPTX (`python-pptx`)
- YouTube research: search + transcript extraction
- Client brand config in `config/clients/{id}.yaml` with auto-theming

## Ultimate Port Closeout Boundary (2 April 2026)

- Verification for this phase is the targeted green matrix recorded in `docs/superpowers/plans/2026-04-02-ultimate-port-closeout.md`
- Legacy blockers remain out of scope for this closeout: `tests/pipelines/test_content_generate.py`, `tests/pipelines/test_competitive_analysis.py`, `tests/pipelines/test_clone_converge_full.py`, and top-level `tests/test_integration*.py`
- The current legacy stalls are network-bound through `httpcore`, and `pytest-timeout` is not installed in this repo
