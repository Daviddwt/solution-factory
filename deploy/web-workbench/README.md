# Solution Factory Web Workbench

This is the marker-1 web workbench path packaged inside `solution-factory`.

## Scope

The current production capability is:

```text
company knowledge base + customer materials + operator notes
-> page-level PPT scripts
-> page-level image-production prompts
-> Markdown / ZIP export
```

The web workbench does not generate final slide images, image-only PPTX, or editable PPTX unless those downstream executors are separately connected and verified.

## Local Start

```bash
cd deploy/web-workbench
cp .env.example .env
./install.sh
./start.sh
./healthcheck.sh
```

Open:

```text
http://127.0.0.1:3000/create
```

## Stop

```bash
./stop.sh
```

## Important Paths

- Uploaded project jobs: `storage/workspaces/`
- Company knowledge-base uploads: `storage/knowledge_base/`
- Backend logs: `output/logs/backend.log`
- Frontend logs: `output/logs/frontend.log`

## Required Runtime

- Python 3.11+
- Node.js 20+
- npm
- `codex` CLI on `PATH` when `PIPELINE_WORKER_MODE=codex`
- `hermes` CLI on `PATH` when `PIPELINE_WORKER_MODE=hermes`

