# Telegram Mode Routing

## Purpose

Use one Telegram entry point as a front door for three distinct operating modes without forcing separate bots:

- `assistant`
- `vizier_work`
- `operator`

## Behavior

The Telegram mode router runs as a Hermes `pre_llm_call` hook and only applies when `platform="telegram"`.

It chooses a mode in this order:

1. Explicit override in the current message:
   - `/assist`
   - `/work`
   - `/ops`
2. Keyword inference from the current message:
   - personal-assistant cues -> `assistant`
   - deliverable/client cues -> `vizier_work`
   - repo/debug/code cues -> `operator`
3. Sticky override from recent user history if the current turn is ambiguous
4. Default fallback -> `assistant`

## Mode Intent

- `assistant`
  - personal help, reminders, drafting replies, planning, everyday questions
- `vizier_work`
  - posters, reports, proposals, campaigns, charts, deliverables
- `operator`
  - code changes, debugging, tests, pipeline maintenance, repo operations

## Boundaries

- This routing layer injects mode-specific guidance.
- It does not yet hard-hide tools by mode.
- It reduces confusion by steering Hermes before tool choice and generation planning.
- Artifact-specific brief normalization should only trigger after the turn is in `vizier_work`.

## Follow-on

Recommended next step:

- add mode-scoped tool exposure or tool-preference rules so `assistant` mode deprioritizes Vizier workflow tools even more strongly.
