# PPT Style Template Intake

Use this guide when the operator wants a PPT style different from the default Solution Factory style.

## When To Ask For Style References

Ask for reference screenshots, PPTX, PDF, or images when:

- The operator mentions a customer template, brand style, previous deck, board-report style, government-report style, product-launch style, or any non-default look.
- The output will be rendered as NotebookLM image PPT.
- The operator wants the PPT to match an existing customer or company deck.

## What To Analyze

Analyze the reference for:

- Canvas ratio and safe margins
- Title bar placement and hierarchy
- Dominant colors and accent colors
- Fonts and text density
- Table style
- Diagram style
- Icon style
- Page number/footer style
- Background treatment
- Common page layouts
- Forbidden or unsuitable visual patterns

## Output

For each project, create or update:

```text
outputs/solution-factory/<project-id>/00_style_profile.md
```

Include:

- Visual positioning
- Color palette
- Typography rules
- Layout rules
- Table rules
- Diagram rules
- Image/icon rules
- Do-not-use list
- NotebookLM style prompt block

## Global vs Project Template

- Use project-level `00_style_profile.md` by default.
- Update `assets/notebooklm-image-ppt-style.zh-CN.md` only when the operator explicitly wants to change the global default.
- If the reference material conflicts with readability or enterprise reporting standards, state the issue and propose a safer adaptation.

