---
name: solution-factory-orchestrator
description: Orchestrate the solution-factory production line with real parallel sub-agents, review gates, standardized artifacts, and downstream PPT handoff.
---

# Solution Factory Orchestrator

Use this skill when the user wants to build a solution proposal, decompose requirements, match company capabilities, or generate PPT scripts through the standardized solution-department production line.

## Version 1.0 Production Boundary

This unified plugin uses the server-safe script workbench contract as the default production boundary.

The verified first production path is:

```text
company knowledge base + customer requirement materials + operator instructions
-> reviewable page-level PPT script
-> page-level image-production prompts
-> Markdown / ZIP handoff package
```

Do not claim image PPT generation, image-only PPTX generation, or editable PPTX rebuild is connected unless the user explicitly invokes a verified downstream executor.

For server/direct use, route to:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py
```

Read `assets/script-workbench-contract.md` and `assets/server-deployment.md` when the user asks for server, colleague, or no-Codex-Desktop usage.

## Start In Plan Mode

Every new project must start with `solution-intake-planner`.

Before producing artifacts:

1. Ask the operator for project background, target audience, output goals, deadline, and expected depth.
2. Ask the operator to upload or point to all source materials.
3. Ask for approved company product/FRS/case materials.
4. Ask for existing customer systems, APIs, databases, devices, IT/OT boundaries, and third-party applications.
5. Ask for sensitive-material boundaries and forbidden-use rules.
6. Ask whether a specific PPT style is required.
7. If a specific style is required, ask for screenshots, PPTX, PDF, images, or previous approved decks, then use `style-template-agent` before PPT prompt generation.
8. Summarize received materials, missing materials, assumptions, expected artifacts, and review gates.
9. Ask for approval before executing.

Use:

- `assets/plan-mode-workflow.md`
- `assets/operator-intake-checklist.md`
- `assets/style-template-intake.md`
- `assets/sensitive-policy.md`
- `assets/script-workbench-contract.md`

Do not skip the intake summary. Do not generate PPT scripts or NotebookLM prompts before the operator approves the plan.

## Golden Rule

The source of truth is:

1. Requirement pack
2. Capability match matrix
3. Implementation blueprint
4. Page-level PPT script

NotebookLM or image PPT output is only a rendering layer.

## Workspace

Create each project under:

```text
outputs/solution-factory/<project-id>/
```

Use these artifact names exactly:

- `00_material_index.json`
- `01_company_capability_library.json`
- `02_requirement_pack.json`
- `03_capability_match_matrix.json`
- `04_implementation_blueprint.json`
- `05_ppt_script.json`
- `05_ppt_script.md`
- `06_visual_plan.json`
- `07_image_ppt/`
- `08_editable_ppt/`
- `09_scenario_deep_dive/`
- `10_overall_architecture/`
- `00_style_profile.md` when the operator provides a project-specific style reference

For server CLI jobs, use the script workbench layout under `storage/workspaces/{workspace_id}/jobs/{job_id}/` as defined in `assets/script-workbench-contract.md`.

## Orchestration Pattern

When the multi-agent tool is available, use real parallel sub-agents for non-overlapping work:

1. Material ingestion phase:
   - Agent A: presales solution materials
   - Agent B: product baseline materials
   - Agent C: company profile and case materials
2. Requirement decomposition phase:
   - Agent A: business scenarios and roles
   - Agent B: systems, data, and interfaces
   - Agent C: delivery constraints and acceptance indicators
3. Script phase:
   - Agent A: page-level content script
   - Agent B: visual plan and diagram type selection
4. Scenario prompt phase:
   - Agent A: scenario deep-dive content and source references
   - Agent B: NotebookLM image-PPT prompt and diagram instructions
5. Style-template phase, when references are provided:
   - Agent A: analyze PPT/PDF/screenshots/images for visual rules
   - Agent B: convert style rules into a project-level `00_style_profile.md`
6. Server script-workbench phase, when Codex UI is unavailable or teammates need direct server use:
   - Initialize a job with `solution_factory_workbench.py init`
   - Run a verified model adapter or import a reviewed `ppt-script.md`
   - Validate page count, P01/P02 roles, source grounding, and Page-specific source of truth
   - Package Markdown/ZIP handoff artifacts

Do not let sub-agents write final files independently unless their write scopes are disjoint. The orchestrator owns the final merged artifacts.

## Review Gates

Stop and ask for user review after:

1. `01_company_capability_library.json`
2. `02_requirement_pack.json` plus `03_capability_match_matrix.json`
3. `05_ppt_script.md`
4. Project-level style profile when the user provides style references
5. Scenario-level or overall NotebookLM prompt before image PPT rendering

Only continue past a gate when the user approves or explicitly asks to proceed.

In server/direct-use mode, never skip the script quality gate. Run:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py validate <job-root> --require-pages
```

## Sensitive Data

Use `assets/sensitive-policy.md`. Store summaries and paths only. Do not copy contract bodies, exact prices, invoice details, or personal identity data into reusable artifacts.

## Validation

Before presenting an artifact set as ready, run:

```bash
python3 plugins/solution-factory/scripts/validate_solution_factory.py outputs/solution-factory/<project-id>
```

Report any missing fields or boundary violations before moving to rendering.
