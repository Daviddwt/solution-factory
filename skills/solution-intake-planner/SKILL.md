---
name: solution-intake-planner
description: Start a Solution Factory project in Plan mode by interviewing the operator, collecting materials, identifying gaps, and preparing a production plan before artifact generation.
---

# Solution Intake Planner

Use this skill at the start of every new Solution Factory project.

## Plan-First Rule

Do not produce final artifacts during intake. First collect context, ask for missing materials, summarize assumptions, and ask the operator to approve the production plan.

If Codex Plan mode and `request_user_input` are available, use them for the first one to three high-level intake questions. Otherwise ask concise plain-language questions.

## Required Intake

Use:

- `assets/plan-mode-workflow.md`
- `assets/operator-intake-checklist.md`
- `assets/sensitive-policy.md`
- `assets/material-whitelist.md`
- `assets/style-template-intake.md`

## Required Questions

Ask for:

- Project/customer name
- Industry/domain
- Target audience
- Proposal/PPT purpose
- Required output type
- All customer materials
- Company capability/product/case materials
- Existing systems, APIs, databases, devices, IT/OT boundaries
- Sensitive materials and forbidden-use boundaries
- PPT style references: screenshots, PPTX, PDF, previous decks, brand templates
- Known customer confirmations and open questions

## Material Upload Guidance

Tell the operator to upload or point to materials in buckets:

- Customer background and requirements
- Existing systems and interface descriptions
- Product baseline/FRS/company capability materials
- Case studies and company profile
- Delivery/security/deployment constraints
- PPT style reference materials

## Style Reference Rule

If the operator wants a non-default PPT style, ask for reference screenshots, PPTX, PDF, or images. Do not generate NotebookLM image-PPT prompts until the style reference has been analyzed by `style-template-agent`.

If no style reference is available, state that the plugin will use the default enterprise smart-logistics style in `assets/notebooklm-image-ppt-style.zh-CN.md`.

## Intake Summary

Before execution, return:

- Received materials
- Missing materials
- Approved source scope
- Sensitive-data handling rule
- Style template source
- Expected artifacts
- Proposed review gates
- Proposed sub-agent split
- Assumptions and open questions

Ask for approval to proceed.

