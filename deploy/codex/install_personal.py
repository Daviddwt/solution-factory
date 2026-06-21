#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


EXCLUDE_NAMES = {".DS_Store", "__pycache__", ".git"}
PLUGIN_NAME = "solution-factory"


def copy_plugin(source: Path, destination: Path) -> None:
    if destination.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = destination.with_name(f"{destination.name}.backup-{stamp}")
        destination.rename(backup)
        print(f"Backed up existing plugin to {backup}")

    def ignore(_: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in EXCLUDE_NAMES or name.endswith(".pyc")}
        return ignored

    shutil.copytree(source, destination, ignore=ignore)


def update_marketplace(marketplace_path: Path) -> None:
    if marketplace_path.exists():
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    else:
        marketplace = {"name": "local-plugins", "interface": {"displayName": "Local Plugins"}, "plugins": []}

    marketplace.setdefault("name", "local-plugins")
    marketplace.setdefault("interface", {}).setdefault("displayName", "Local Plugins")
    plugins = marketplace.setdefault("plugins", [])
    entry = {
        "name": PLUGIN_NAME,
        "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }
    for index, item in enumerate(plugins):
        if item.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            break
    else:
        plugins.append(entry)
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_path.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_source(raw: str) -> Path:
    if raw:
        source = Path(raw).expanduser().resolve()
    else:
        source = Path(__file__).resolve().parents[2]
    manifest = source / ".codex-plugin" / "plugin.json"
    if not manifest.exists():
        raise SystemExit(f"Plugin manifest not found: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("name") != PLUGIN_NAME:
        raise SystemExit(f"Expected plugin name {PLUGIN_NAME}, got {data.get('name')!r}")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description="Install solution-factory into the current user's Codex local plugin marketplace.")
    parser.add_argument("--source", default="", help="Plugin root. Defaults to the unpacked solution-factory folder.")
    parser.add_argument("--dest-root", default="~/.agents/plugins", help="Personal plugin marketplace root.")
    args = parser.parse_args()

    source = resolve_source(args.source)
    dest_root = Path(args.dest_root).expanduser().resolve()
    destination = dest_root / "plugins" / PLUGIN_NAME
    if source == destination.resolve():
        print(f"Plugin is already at {destination}; only updating marketplace.")
    else:
        copy_plugin(source, destination)
    update_marketplace(dest_root / "marketplace.json")
    print(f"{PLUGIN_NAME} is ready at {destination}")
    print(f"Marketplace updated at {dest_root / 'marketplace.json'}")
    print("Restart or refresh Codex plugin discovery before first use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
