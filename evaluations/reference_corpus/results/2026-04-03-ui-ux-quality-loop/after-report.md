# Poster/UI Artifact Eval

Label: ui-ux-loop-after
Git ref: `WORKTREE` (`87b50c15`)
Generated at: 2026-04-03T01:38:06+00:00

## Summary

- Average objective score: 88.3/100
- Check averages: {'reference_usage': 100.0, 'copy_discipline': 100.0, 'template_fit': 88.8, 'prompt_guardrails': 81.2, 'trace_persistence': 100.0, 'hero_presence': 67.1, 'text_zone_readability': 77.2, 'cta_salience': 70.2}

## Cases

| Prompt | Template | Objective | Hero | Readability | CTA | Reference Tools |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| swiss_analytics_hero | floating-card-square | 91.4 | 100.0 | 85.7 | 46.5 | search_ui_styles, search_ux_guidelines |
| retro_event_poster | stacked-type-square | 87.3 | 25.6 | 83.1 | 97.1 | search_ui_styles, search_ux_guidelines |
| donation_trust_landing | hero-bottom-text-square | 89.9 | 100.0 | 57.2 | 57.5 | search_ui_styles, search_ux_guidelines |
| premium_product_drop | stacked-type-square | 84.8 | 42.7 | 83.0 | 79.9 | search_ui_styles, search_ux_guidelines |

## Notes

- swiss_analytics_hero: Book Demo CTA, template `floating-card-square`, manual focus = ['Check whether the composition feels deliberately grid-led instead of generic SaaS.', 'Check whether the CTA reads clearly without overpowering the trust tone.']
- retro_event_poster: Get Tickets CTA, template `stacked-type-square`, manual focus = ['Check whether the poster is still readable instead of becoming pure moodboard material.', 'Check whether the headline feels intentionally oversized and premium.']
- donation_trust_landing: Donate Now CTA, template `hero-bottom-text-square`, manual focus = ['Check whether the tone feels trustworthy rather than generic or melodramatic.', 'Check whether the CTA is obvious and the body copy remains easy to read.']
- premium_product_drop: Shop Now CTA, template `stacked-type-square`, manual focus = ['Check whether the hero subject feels dominant rather than thumbnail-sized.', 'Check whether the CTA has enough presence in the final hierarchy.']
