#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 "$ROOT_DIR/scripts/solution_factory_workbench.py" --help >/dev/null
python3 -m py_compile "$ROOT_DIR/scripts/solution_factory_workbench.py"
echo "ok"

