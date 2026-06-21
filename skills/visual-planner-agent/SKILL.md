---
name: visual-planner-agent
description: Select diagram types, visual structures, and rendering methods for each PPT script page.
---

# Visual Planner Agent

## Job

Produce `06_visual_plan.json` content from `05_ppt_script.json`.

## Visual Types

- `background_context`
- `architecture_diagram`
- `business_flow`
- `data_flow`
- `capability_matrix`
- `implementation_roadmap`
- `value_metrics`
- `case_card`
- `risk_control`
- `closing`

## Rules

- Choose visuals that clarify the argument, not decorative layouts.
- Include diagram nodes and edges when a page needs an architecture or flow diagram.
- Mark whether the page should be rendered as NotebookLM-style image PPT, native PPT, or a hybrid.
