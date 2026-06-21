---
name: scenario-ppt-prompt-agent
description: Generate scenario-level deep dives and NotebookLM-ready image-PPT prompts from approved requirement and capability artifacts.
---

# Scenario PPT Prompt Agent

Use this skill after a requirement has passed Gate 2 and the user wants one scenario expanded into detailed PPT content or NotebookLM image-PPT prompts.

## Inputs

- Approved requirement item from `02_requirement_pack.json`
- Related matches from `03_capability_match_matrix.json`
- Relevant implementation items from `04_implementation_blueprint.json`
- Capability evidence from product baseline materials and approved source references
- User-supplied customer confirmations and open questions

## Outputs

Write scenario artifacts under:

```text
outputs/solution-factory/<project-id>/09_scenario_deep_dive/
```

Use stable names:

- `<REQ-ID>-<slug>.json`：machine-readable deep dive
- `<REQ-ID>-<slug>.md`：human-review deep dive
- `<REQ-ID>-ppt-style-prompt.md`：reusable style prompt when needed
- `<REQ-ID>-notebooklm-image-ppt-prompt.md`：copy-ready NotebookLM prompt

## Required Sections

Each scenario deep dive must include:

- Scenario positioning: short-term path and long-term evolution
- Confirmed defaults and open questions
- Requirement decomposition
- Current-state process problems
- Target-state process
- Function and product capability mapping
- AI capability application
- Implementation path and integration boundary
- PPT page expansion plan
- Source references or assumption markers

## NotebookLM Prompt Rules

The NotebookLM prompt must be self-contained. Assume NotebookLM has no memory of prior discussion.

For each page include:

- Page title
- Page goal
- Layout requirement
- Diagram or table structure
- Required keywords
- Presenter narration
- Visual cautions and forbidden claims

Every architecture or process page must specify nodes, layers, arrows, exceptions, and boundary labels. Do not write vague instructions such as "make a professional diagram" without saying what the diagram contains.

## Style

Use project-level `outputs/solution-factory/<project-id>/00_style_profile.md` when it exists.

If the user provides a different deck style, use `style-template-agent` first to analyze the reference screenshots, PPTX, PDF, images, or previous decks. Do not generate the NotebookLM prompt until the style profile is reviewed or the user explicitly approves proceeding.

Use `assets/notebooklm-image-ppt-style.zh-CN.md` only when no project-specific style reference is provided. Keep the visual language aligned with the default smart-logistics requirement screenshots: blue title bar, light blue-gray background, deep-blue table headers, technical diagrams, and restrained enterprise tone.

## Boundary Rules

- Do not promote `integration`, `custom_dev`, or `unclear` items as existing product capabilities.
- Mark system APIs, data quality, resource ownership, and cross-system boundaries as assumptions or customer-confirmation items when not confirmed.
- Do not include contract text, prices, invoice data, or personal details.
- NotebookLM output is a rendering layer. The scenario deep dive remains the source of truth.
- When operating in server/direct-use mode, stop at page-level scripts and image-production prompts unless a verified image-generation executor is explicitly connected.
