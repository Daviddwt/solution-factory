#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(os.environ.get("SOLUTION_FACTORY_PROJECT_ROOT", Path.cwd())).resolve()
ORG_ROOT = Path(os.environ.get("SOLUTION_FACTORY_WEDRIVE_ROOT", "~/EnterpriseWeDrive")).expanduser()

DEFAULT_BUCKETS = [
    ("presales", ORG_ROOT / "解决方案与销售部" / "A.售前方案"),
    ("company_profile", ORG_ROOT / "解决方案与销售部" / "C.公司概况简介"),
    ("product_baseline", ORG_ROOT / "产品部" / "产品标准文档"),
    ("product_solution_cases", ORG_ROOT / "产品部" / "敢为云解决方案&案例&产品手册"),
    ("local_kb", PROJECT_ROOT / "knowledge_base_md"),
]

SUPPORTED_SUFFIXES = {".pptx", ".ppt", ".pdf", ".docx", ".xlsx", ".md"}
SENSITIVE_HINTS = ("合同", "报价", "发票", "身份证", "银行", "回款", "付款", "PO")


def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path


def sensitivity_for(path: Path) -> str:
    text = str(path)
    if any(hint in text for hint in SENSITIVE_HINTS):
        return "sensitive-summary-only"
    return "normal-summary"


def tags_for(path: Path) -> list[str]:
    text = str(path).lower()
    tags: list[str] = []
    mapping = {
        "iot": "iot",
        "物联": "iot",
        "ioc": "ioc",
        "ai": "ai",
        "智能体": "ai-agent",
        "数字孪生": "digital-twin",
        "三维": "3d-visualization",
        "案例": "case",
        "frs": "frs",
        "标准": "baseline",
        "方案": "solution",
        "ppt": "presentation",
    }
    for key, tag in mapping.items():
        if key in text and tag not in tags:
            tags.append(tag)
    return tags


def build_index(limit: int | None = None) -> dict:
    materials = []
    missing_roots = []
    for bucket, root in DEFAULT_BUCKETS:
        if not root.exists():
            missing_roots.append({"source_bucket": bucket, "path": str(root)})
            continue
        for path in iter_files(root):
            stat = path.stat()
            materials.append({
                "id": f"M{len(materials) + 1:04d}",
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "file_type": path.suffix.lower().lstrip("."),
                "source_bucket": bucket,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "availability": "local",
                "sensitivity": sensitivity_for(path),
                "extract_policy": "summary-and-tags-only",
                "tags": tags_for(path),
            })
            if limit is not None and len(materials) >= limit:
                break
        if limit is not None and len(materials) >= limit:
            break

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "policy": "whitelist-only; no body extraction",
            "supported_suffixes": sorted(SUPPORTED_SUFFIXES),
        },
        "missing_roots": missing_roots,
        "materials": materials,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a safe material index for solution-factory.")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "outputs/solution-factory/material-index.json")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    data = build_index(limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
