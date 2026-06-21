# Sharing And Installation

This plugin is designed to be used as:

1. A personal Codex plugin for the owner.
2. A shareable local plugin package for colleagues.
3. A browser-based web workbench for local or LAN operation.
4. A portable server-side CLI bundle for environments without Codex Desktop UI.

## Personal Plugin Location

Recommended personal plugin location:

```text
~/.agents/plugins/plugins/solution-factory/
```

Recommended personal marketplace:

```text
~/.agents/plugins/marketplace.json
```

## Share Package

Colleagues can install from a zip package containing:

- `.codex-plugin/plugin.json`
- `skills/`
- `assets/`
- `scripts/`
- `schemas/`
- `deploy/server/`
- `deploy/web-workbench/`
- `deploy/codex/install_personal.py`
- `README.md`

Do not include customer-sensitive output folders in the shared plugin package.

## Colleague Setup

1. Unzip the package.

2. Run the installer from the unzipped plugin root:

```bash
python3 deploy/codex/install_personal.py
```

The installer copies the plugin into:

```text
~/.agents/plugins/plugins/solution-factory/
```

It also creates or updates:

```text
~/.agents/plugins/marketplace.json
```

Manual marketplace entry, if needed:

```json
{
  "name": "solution-factory",
  "source": {
    "source": "local",
    "path": "./plugins/solution-factory"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

3. Restart or refresh Codex plugin discovery.

4. Start with this prompt:

```text
用 solution-factory 的Plan模式启动一个解决方案生产项目，先问我背景、材料和风格参考。
```

## Local Web Workbench

The web operation path is included in the shared package:

```bash
cd ~/.agents/plugins/plugins/solution-factory/deploy/web-workbench
cp .env.example .env
./install.sh
./start.sh
open http://127.0.0.1:3000/create
```

Daily use after first install:

```bash
cd ~/.agents/plugins/plugins/solution-factory/deploy/web-workbench
./start.sh
open http://127.0.0.1:3000/create
```

Stop:

```bash
./stop.sh
```

## Server Setup

On a server, unzip the package and run:

```bash
cd /path/to/solution-factory
./deploy/server/healthcheck.sh
./deploy/server/run-cli.sh --help
```

Create a server job:

```bash
./deploy/server/run-cli.sh init \
  --output-root /srv/solution-factory-workbench \
  --requester "同事姓名" \
  --title "客户项目解决方案汇报" \
  --pages 16 \
  --source /srv/uploads/customer \
  --knowledge-base /srv/knowledge/company-baseline
```

Then run `run-model`, `import-script`, `validate`, and `package`.

Server mode produces PPT scripts and page image-production prompts. It does not claim image PPTX or editable PPTX generation.
