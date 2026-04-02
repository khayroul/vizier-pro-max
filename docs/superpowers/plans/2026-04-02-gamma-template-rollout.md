# Gamma Template Rollout Plan

Date: 2 April 2026

## Goal

Move Gamma from a flexible export target to a premium, repeatable client presentation system.

This plan assumes the current Gamma API integration is already live in:

- `scripts/document/gamma_generate.py`
- `pipelines/presentation_deck_generate.py`
- `pipelines/structured_nonfiction_generate.py`
- `pipelines/marketing_plan_generate.py`

The remaining work is about consistency and quality, not basic connectivity.

## Why This Matters

The current `from-text` Gamma path is useful, but premium client work needs more control.

The biggest quality gains come from:

- template-based generation via `POST /generations/from-template`
- stable house-style decks
- client-specific `themeId` and `folderIds`
- deck-native planning rather than document condensation alone

## Deck Families To Standardize

Create these Gamma master templates first:

1. Marketing strategy deck
2. Proposal / pitch deck
3. Quarterly business review deck
4. Campaign performance deck

Optional later:

5. One-page executive briefing
6. Internal team planning deck

## Required Gamma Assets

For each template family, define and record:

- Gamma template ID
- Gamma theme ID
- Gamma folder ID
- intended audience
- preferred card count range
- default image source
- default card dimensions
- header/footer rules

## Repo Changes Planned

### Phase 1: Client Mapping

- [ ] Extend client config loading so clients can optionally declare:
  - `gamma_theme_id`
  - `gamma_folder_ids`
  - `gamma_template_ids`
  - `gamma_header_footer`
- [ ] Add validation for missing or malformed Gamma config
- [ ] Add tests for client-level Gamma mapping

### Phase 2: Template Profiles

- [ ] Define deck profiles in `presentation_deck_generate`
  - `marketing_strategy`
  - `proposal`
  - `qbr`
  - `campaign_performance`
- [ ] Add per-profile defaults for:
  - card count
  - text density
  - image strategy
  - template usage
- [ ] Add a profile-to-template resolution layer

### Phase 3: Better Deck Planning

- [ ] Add a deck-outline planning step before Gamma generation
- [ ] Produce card-by-card source structure:
  - title card
  - executive summary
  - context
  - key insights
  - recommendations
  - next steps
- [ ] Feed Gamma template runs with deck-native prompts rather than only merged markdown

### Phase 4: Deck QA

- [ ] Add presentation-specific quality checks:
  - card count in expected range
  - no over-dense cards
  - brand/theme/template selected
  - export file present
  - Gamma URL present
- [ ] Add review fixtures for each deck family

### Phase 5: Delivery

- [ ] Allow Telegram/Hermes flows to request:
  - deck only
  - deck + PDF doc
  - deck + posters + creative pack
- [ ] Add client-facing handoff packaging for Gamma deck exports

## Recommended Runtime Defaults

For client-facing decks:

- `gamma_format=presentation`
- `gamma_card_dimensions=16x9`
- `gamma_text_amount=brief`
- `gamma_export_as=pdf`
- `gamma_image_source=themeAccent` when a theme is available
- `gamma_template_id=<family template>` whenever possible

For reports that still need a deck:

- source through `structured_nonfiction_generate`
- export via Gamma only after the structured document is assembled

## Acceptance Criteria

This rollout is done when:

- each core client deck family has a real Gamma master template
- Vizier can choose the right template from client/profile context
- `presentation_deck_generate` produces repeatably branded decks
- Hermes/Telegram can request those decks directly
- tests cover config mapping, profile selection, and deck QA

## Out Of Scope

- replacing Typst/PDF as the premium long-form document path
- using Gamma for novels or children’s books
- broad client-config redesign unrelated to presentations
