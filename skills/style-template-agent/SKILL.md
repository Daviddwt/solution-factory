---
name: style-template-agent
description: Analyze reference PPT/PDF/screenshots/images and produce a project-specific PPT style profile for NotebookLM image-PPT prompts.
---

# Style Template Agent

Use this skill whenever the operator provides reference images, PPTX, PDF, screenshots, brand templates, or previous decks for PPT style matching.

## Goal

Create a project-specific style profile that can be embedded into NotebookLM image-PPT prompts.

## Inputs

- Reference screenshots/images
- Reference PPTX or PDF
- Brand or customer template rules
- Operator notes on preferred style

## Output

Write:

```text
outputs/solution-factory/<project-id>/00_style_profile.md
```

When the operator explicitly asks to change the global default, update:

```text
plugins/solution-factory/assets/notebooklm-image-ppt-style.zh-CN.md
```

## Analyze

- Canvas size and aspect ratio
- Page margins and title placement
- Header/footer style
- Color palette
- Typography and text density
- Table treatment
- Diagram style
- Icon and image style
- Background and section layout
- Page-number conventions
- Do-not-use patterns

## Rules

- Do not copy customer confidential content from reference decks into reusable templates.
- Extract style rules, not business content.
- If the reference style harms readability or looks unsuitable for executive reporting, propose a restrained adaptation.
- Keep the style prompt explicit enough for NotebookLM: describe colors, structure, table style, diagram style, spacing, and forbidden visuals.
- Use project-level style profiles by default to avoid changing the global template for every user.

