# Vizier Decision Notes

Decision notes are the durable record for why Vizier changed in a way that
affects architecture, governance, routing, metering, defaults, or operational
behavior.

Use this folder when a change is likely to trigger one of these questions later:

- Why did we change this behavior?
- Was this a regression or a deliberate constraint?
- What earlier subsystem or session were we trying to preserve?
- What invariant were we protecting?

## When To Write One

Add or update a decision note for changes that:

- alter default behavior
- reroute model or provider traffic
- tighten or relax metering/accounting boundaries
- change lifecycle, promotion, or quality-gate enforcement
- preserve an existing capability but constrain how it executes
- intentionally replace a prior architectural assumption

## Naming

Use:

- `YYYY-MM-DD-short-slug.md`

Examples:

- `2026-04-03-hermes-compression-metering-boundary.md`
- `2026-04-03-falai-default-for-posters.md`

## Minimum Structure

Each note should cover:

1. `Context`
2. `Decision`
3. `Preserved Behavior`
4. `Invariants`
5. `Validation`
6. `Follow-up`

Use the template in [`_template.md`](/Users/Executor/vizier-pro-max/docs/superpowers/decisions/_template.md).
