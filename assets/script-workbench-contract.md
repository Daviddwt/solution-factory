# Script Workbench Contract

This contract is inherited from the marker-1 server version and is now the default production boundary for `solution-factory`.

## Production Capability

The verified first production path is:

```text
company knowledge base + customer requirement materials + operator instructions
-> reviewable page-level PPT script
-> page-level image-production prompts
-> Markdown / ZIP handoff package
```

This path does not claim to generate slide images, image-only PPTX, or editable PPTX unless a verified downstream capability is explicitly connected and approved.

## Job Layout

Server and CLI workspaces use:

```text
storage/workspaces/{workspace_id}/jobs/{job_id}/
  input/
  work/
    01_requirements/
      01_requirements.md
      source-inventory.md
      knowledge-base-inventory.md
      facts.md
      open-questions.md
      generation-mode.md
      page-index.json
      pages/page-XX.md
      ppt-script.md
    02_image_ppt/
      style-prompt.md
      prompts/slide-XX.md
      results/page-XX.md
  output/
    script-package.zip
  prompt.md
  status.json
  logs.txt
```

## Quality Gates

`ppt-script.md` must pass these checks before it can be packaged as a ready script:

- Page count matches the requested total.
- P01 is a cover page.
- P02 is an agenda or scope page.
- No placeholder titles such as "专题深化 9", "补充页", "未命名页面", or "待定页面".
- No duplicate page titles.
- Every page includes source basis, diagram structure, `Page-specific source of truth`, design brief, narration, and review notes.
- `Page-specific source of truth` includes page goal, layout requirements, diagram nodes, required keywords, on-slide copy, visual notes, fact/capability boundaries, and forbidden claims.
- Customer-specific facts come from uploaded/pasted materials or are marked as待确认/待补充.
- Company knowledge base is used only for capability wording, baseline language, style, and reusable architecture, not for customer facts.

## Boundary Rules

- Do not expose shell access, arbitrary local paths, or model credentials to teammates.
- Do not let user input become a shell command.
- Do not label local HTML/SVG screenshots, deterministic renderers, historical artifacts, or mocks as formal image PPT generation.
- Do not claim a deck is editable when core diagrams, cards, tables, labels, or arrows are still large PNG bodies.
- Downstream image PPT or editable PPT stages must remain separate reviewed handoffs.

## Portable CLI

Use the bundled CLI when Codex UI is not available:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py init \
  --output-root /path/to/workbench \
  --requester "David" \
  --title "某项目解决方案汇报" \
  --pages 12 \
  --source /path/to/customer-materials \
  --knowledge-base /path/to/company-baseline
```

Then run a verified model adapter:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py run-model \
  /path/to/workbench/storage/workspaces/person_xxx/jobs/job_xxx \
  --provider codex
```

Or import a model-generated script:

```bash
python3 plugins/solution-factory/scripts/solution_factory_workbench.py import-script \
  /path/to/job \
  --script /path/to/ppt-script.md \
  --pages 12
```

