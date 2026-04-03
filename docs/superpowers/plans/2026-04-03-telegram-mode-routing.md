# Telegram Mode Routing

## Purpose

Use one Telegram entry point as a front door for three distinct operating modes without forcing separate bots:

- `assistant`
- `vizier_work`
- `operator`

## Behavior

The Telegram mode router primes state in the Hermes `pre_tool_resolution` hook and adds mode guidance in `pre_llm_call`. It only applies when `platform="telegram"`.

It chooses a mode in this order:

1. Explicit override in the current message:
   - `/assist`
   - `/work`
   - `/ops`
2. Keyword inference from the current message:
   - support, planning, thinking, or drafting cues -> `assistant`
   - clear deliverable or Vizier workflow cues -> `vizier_work`
   - repo/debug/maintenance cues -> `operator`
3. Sticky override from recent user history if the current turn is ambiguous
4. Default fallback -> `assistant`

## Mode Intent

- `assistant`
  - support for personal life and professional life
  - reminders, planning, prioritization, drafting replies, decision support, everyday questions
- `vizier_work`
  - polished deliverables and Vizier production workflows
  - posters, reports, proposals, campaigns, charts, content packages
- `operator`
  - system and repo maintenance
  - code changes, debugging, tests, logs, pipeline maintenance, repo operations

## Boundaries

- This routing layer injects mode-specific guidance.
- It also gates key Vizier tools by mode for the Telegram front door:
  - `assistant` starts with Vizier workflow tools hidden
  - clear `vizier_work` requests can auto-activate the matching workflow surface for the turn when the deliverable type is obvious
  - `switch_toolset` remains available when the user intentionally wants a different Vizier workflow surface
  - `operator` keeps repo-oriented guidance active without automatically exposing marketing-style tools
- It reduces confusion by steering Hermes before tool choice and generation planning.
- Artifact-specific brief normalization should only trigger after the turn is in `vizier_work`.

## Follow-on

Recommended next step:

- extend mode-scoped gating beyond the current Vizier plugin tools if we want even tighter separation between personal-assistant and operator behaviors.
