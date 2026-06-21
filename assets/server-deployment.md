# Server Deployment

`solution-factory` can be used on a server without the Codex Desktop UI through the portable CLI.

When a browser workbench is required, use:

```text
deploy/web-workbench/
```

and open:

```text
http://<server-ip>:3000/create
```

## Minimum Runtime

- Python 3.10+
- Optional: `codex` CLI for `--provider codex`
- Optional: `hermes` CLI for `--provider hermes`

No Node.js runtime is required for the plugin CLI path.

## Install

Copy the plugin folder to the server:

```text
solution-factory/
  .codex-plugin/plugin.json
  skills/
  assets/
  scripts/
  schemas/
  deploy/server/
  README.md
```

Run:

```bash
cd /path/to/solution-factory
python3 scripts/solution_factory_workbench.py --help
```

## Create A Job

```bash
python3 scripts/solution_factory_workbench.py init \
  --output-root /srv/solution-factory-workbench \
  --requester "同事姓名" \
  --title "客户项目解决方案汇报" \
  --pages 16 \
  --scenario "客户汇报" \
  --audience "客户领导" \
  --source /srv/uploads/customer \
  --knowledge-base /srv/knowledge/company-baseline
```

The command prints the created job directory.

## Generate Script

If Codex CLI is configured:

```bash
python3 scripts/solution_factory_workbench.py run-model /path/to/job --provider codex
```

If Hermes CLI is configured:

```bash
python3 scripts/solution_factory_workbench.py run-model /path/to/job --provider hermes
```

If the model is executed elsewhere, import its reviewed Markdown:

```bash
python3 scripts/solution_factory_workbench.py import-script /path/to/job --script /path/to/ppt-script.md --pages 16
```

## Validate And Package

```bash
python3 scripts/solution_factory_workbench.py validate /path/to/job --require-pages
python3 scripts/solution_factory_workbench.py package /path/to/job
```

The handoff package is:

```text
/path/to/job/output/script-package.zip
```

## Capability Boundary

This server path produces PPT scripts and image-production prompts. It does not produce final slide images, image-only PPTX, or editable PPTX unless those downstream capabilities are separately installed and explicitly invoked.
