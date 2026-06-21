# Web Workbench Local Usage

`solution-factory` includes the marker-1 web workbench under:

```text
plugins/solution-factory/deploy/web-workbench/
```

This is the browser-based operation path for local Codex use.

## First Run

```bash
cd "<path-to-solution-factory>/deploy/web-workbench"
cp .env.example .env
./install.sh
./start.sh
./healthcheck.sh
```

Open:

```text
http://127.0.0.1:3000/create
```

## Daily Start

```bash
cd "<path-to-solution-factory>/deploy/web-workbench"
./start.sh
open http://127.0.0.1:3000/create
```

## Stop

```bash
cd "<path-to-solution-factory>/deploy/web-workbench"
./stop.sh
```

## What The Web Page Does

- Upload customer materials and paste supplementary notes.
- Fill requester, title, page count, audience, scenario, and style prompt.
- Manage company knowledge-base files for this local workbench.
- Create isolated jobs under `storage/workspaces/`.
- Produce and review page-level PPT scripts and page-level image-production prompts.
- Export Markdown and ZIP script packages.

## Capability Boundary

The web workbench is a script-production workbench. It does not honestly claim final image PPT or editable PPTX generation unless those downstream executors are separately connected and verified.

