# 2026-04-03 Metering Closure Plan

## Goal

Close the gap between Vizier-recorded usage and provider-billed usage by making
Vizier the single metered inference boundary for Hermes and pipeline traffic.

## What is closed now

### 1. Shared chat metering

- Hermes is configured to use the local Vizier gateway in [config/hermes.yaml](/Users/Executor/vizier-pro-max/config/hermes.yaml).
- Shared pipeline chat calls route through the gateway in [adapter/llm_client.py](/Users/Executor/vizier-pro-max/adapter/llm_client.py).
- The ledger records provider, modality, source, status, and failure reason in [middleware/cost_ledger.py](/Users/Executor/vizier-pro-max/middleware/cost_ledger.py).

### 2. Poster image metering

- The gateway now accepts `POST /v1/images/generations` in [middleware/inference_gateway.py](/Users/Executor/vizier-pro-max/middleware/inference_gateway.py).
- Poster hero generation no longer calls OpenAI directly; it routes through the gateway in [pipelines/poster_generate.py](/Users/Executor/vizier-pro-max/pipelines/poster_generate.py).
- Standard Vizier inference headers are now built from execution context in [middleware/deliverable_context.py](/Users/Executor/vizier-pro-max/middleware/deliverable_context.py).

## Remaining work by segment

### A. Gateway runtime ownership

Problem:
- Hermes can point at the gateway, but the launcher does not yet ensure the
  gateway process is actually up and healthy before Hermes starts.

Files:
- [scripts/delivery/run_inference_gateway.py](/Users/Executor/vizier-pro-max/scripts/delivery/run_inference_gateway.py)
- [scripts/delivery/run_hermes_telegram.py](/Users/Executor/vizier-pro-max/scripts/delivery/run_hermes_telegram.py)

Actions:
- Start or health-check the local gateway before Hermes launch.
- Fail fast when Hermes is configured for the gateway but the gateway is down.
- Add one operator-visible status command for the gateway.

Acceptance:
- Hermes launch fails closed when the gateway is unavailable.
- Hermes launch succeeds without a provider key in the Hermes-facing env.

### B. Provider key isolation

Problem:
- The upstream OpenAI key is still effectively repo-global.
- The gateway still falls back to `OPENAI_API_KEY`, and the repo env loader
  still treats that key as a default override.

Files:
- [adapter/env_loader.py](/Users/Executor/vizier-pro-max/adapter/env_loader.py)
- [middleware/inference_gateway.py](/Users/Executor/vizier-pro-max/middleware/inference_gateway.py)
- [scripts/delivery/run_hermes_telegram.py](/Users/Executor/vizier-pro-max/scripts/delivery/run_hermes_telegram.py)

Actions:
- Introduce `VIZIER_UPSTREAM_OPENAI_API_KEY` as the only upstream cloud key the
  gateway will read.
- Remove `OPENAI_API_KEY` from repo-wide override loading.
- Keep the local dummy key behavior only for Hermes client compatibility when
  targeting the local gateway.

Acceptance:
- Hermes and pipelines can run against the local gateway without the real
  provider key present in their environment.
- Only the gateway process needs the upstream provider key.

### C. Session and run attribution

Problem:
- Chat and image paths now stamp `source`, `deliverable_id`, and `client_id`,
  but true Hermes session attribution is still thin.

Files:
- [middleware/deliverable_context.py](/Users/Executor/vizier-pro-max/middleware/deliverable_context.py)
- [adapter/llm_client.py](/Users/Executor/vizier-pro-max/adapter/llm_client.py)
- [.hermes/plugins/vizier_tools/__init__.py](/Users/Executor/vizier-pro-max/.hermes/plugins/vizier_tools/__init__.py)

Actions:
- Propagate `session_id` from Hermes session startup into gateway headers.
- Standardize header stamping for all Vizier-owned callers.
- Add one trace/query surface that can answer “what did this Hermes session spend?”

Acceptance:
- Ledger queries can roll up by session as well as deliverable and client.

### D. Distillation bypass removal

Problem:
- Distillation compiler and evaluator still talk to providers directly through
  DSPy model strings and Ollama base URLs.

Files:
- [augments/distillation/compiler.py](/Users/Executor/vizier-pro-max/augments/distillation/compiler.py)
- [augments/distillation/evaluator.py](/Users/Executor/vizier-pro-max/augments/distillation/evaluator.py)

Actions:
- Route teacher and student evaluation traffic through the Vizier gateway.
- Stamp distillation-specific metadata such as `source=distillation`,
  `pipeline_name=distillation`, and step names for compile/evaluate phases.
- Preserve current functional behavior while removing direct provider URLs from
  the augment code.

Acceptance:
- Distillation traffic appears in the same append-only ledger as chat and image work.

### E. Modality expansion

Problem:
- The gateway currently covers non-streaming chat and image generation only.

Files:
- [middleware/inference_gateway.py](/Users/Executor/vizier-pro-max/middleware/inference_gateway.py)

Actions:
- Add explicit support for streaming chat when Hermes needs it.
- Add metered gateway routes for any TTS/STT paths that become active.
- Keep modality-specific ledger fields inside one evidence trail instead of
  creating separate accounting islands.

Acceptance:
- No active model modality uses a direct provider client outside the gateway.

### F. No-bypass enforcement

Problem:
- The architecture is improved, but nothing yet prevents future direct provider
  calls from reappearing.

Files:
- new repo guard tests under [tests/](/Users/Executor/vizier-pro-max/tests)

Actions:
- Add one repo-level test that flags direct `openai.OpenAI(` use outside the
  gateway-owned boundary.
- Add one repo-level test that flags direct `ollama_chat/` or equivalent
  provider wiring in production paths.
- Allow narrowly scoped exceptions only where explicitly documented.

Acceptance:
- New direct provider calls fail CI instead of silently reopening the metering gap.

### G. Historical reconciliation

Problem:
- Forward metering is much better now, but it does not yet explain the old
  mismatch between Vizier totals and provider billing.

Files:
- new reconciliation tool or report under [tools/](/Users/Executor/vizier-pro-max/tools)

Actions:
- Build a one-off reconciliation script/report comparing provider billing
  exports against ledgered Vizier runs.
- Categorize unaccounted spend by likely source: Hermes direct traffic, image
  generation, distillation, retries, or non-Vizier workloads.

Acceptance:
- We can explain the historical gap in a bounded, auditable way.

## Execution order

1. Gateway runtime ownership
2. Provider key isolation
3. Session and run attribution
4. Distillation bypass removal
5. No-bypass enforcement
6. Historical reconciliation
7. Modality expansion as new active paths require it

## Definition of done

Metering closure is done when all of the following are true:

- Hermes cannot reach the provider directly in normal operation.
- Pipelines cannot reach the provider directly in normal operation.
- Chat, image, and distillation traffic all land in one append-only ledger.
- Every metered row carries enough metadata to answer who spent what, for what,
  and in which run/session.
- CI catches new bypasses before they land.
