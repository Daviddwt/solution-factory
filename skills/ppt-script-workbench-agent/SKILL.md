---
name: ppt-script-workbench-agent
description: Use the server-safe workbench contract to initialize, validate, package, or run a direct server/CLI PPT script-production job.
---

# PPT Script Workbench Agent

Use this skill when the user wants `solution-factory` to run outside Codex Desktop, share with colleagues through a server, or produce the first verified artifact package: page-level PPT scripts and page-level image-production prompts.

## Plan-Mode Intake Still Applies

Before initializing a CLI job, collect:

- Project/customer name, industry, audience, purpose, expected output, deadline, and depth.
- Customer materials, existing-system/API/database/device/IT/OT information, and operator notes.
- Company product/FRS/case/company-profile materials approved for use.
- Sensitive-material boundaries and forbidden-use rules.
- PPT style requirements. If a non-default style is required, ask for PPTX/PDF/screenshots/images before script production and write or import a project-level style prompt.

If a required material bucket is missing, ask the operator whether to upload it, mark it as unavailable, or proceed with assumptions. Do not silently invent facts or capabilities.

## Production Boundary

The verified first production path is:

```text
company knowledge base + customer materials + operator instructions
-> page-level PPT scripts
-> page-level image-production prompts
-> Markdown / ZIP package
```

Do not claim image PPT, image-only PPTX, or editable PPTX generation unless a separate verified executor is connected.

## Required References

Read as needed:

- `assets/script-workbench-contract.md`
- `assets/server-deployment.md`

## CLI

Initialize:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py init \
  --output-root outputs/solution-factory/server-workbench \
  --requester "<name>" \
  --title "<title>" \
  --pages <n> \
  --source <customer-material-path> \
  --knowledge-base <company-baseline-path>
```

Generate or import:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py run-model <job-root> --provider codex
python3 plugins/solution-factory/scripts/solution_factory_workbench.py run-model <job-root> --provider hermes
python3 plugins/solution-factory/scripts/solution_factory_workbench.py import-script <job-root> --script <ppt-script.md> --pages <n>
```

Validate and package:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py validate <job-root> --require-pages
python3 plugins/solution-factory/scripts/solution_factory_workbench.py package <job-root>
```

## Quality Gate

Reject outputs with:

- Wrong page count.
- P01 not cover.
- P02 not agenda/scope.
- Placeholder or duplicate page titles.
- Missing source basis, diagram structure, `Page-specific source of truth`, design brief, narration, or review notes.
- Weak `Page-specific source of truth` that does not define nodes, layout, keywords, on-slide copy, visual notes, boundaries, and forbidden claims.
