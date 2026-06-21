#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = {
    "material_index": "00_material_index.json",
    "company_capability_library": "01_company_capability_library.json",
    "requirement_pack": "02_requirement_pack.json",
    "capability_match_matrix": "03_capability_match_matrix.json",
    "implementation_blueprint": "04_implementation_blueprint.json",
    "ppt_script": "05_ppt_script.json",
    "visual_plan": "06_visual_plan.json",
}

FIT_LEVELS = {"existing", "configurable", "integration", "custom_dev", "unclear"}
SENSITIVE_TOKENS = ("¥", "身份证", "发票号码", "银行账号", "开户行")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{path.name}: cannot read JSON: {exc}") from exc


def ensure(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def require_fields(obj: dict, fields: list[str], errors: list[str], label: str) -> None:
    for field in fields:
        ensure(field in obj and obj[field] not in (None, "", []), errors, f"{label}: missing {field}")


def scan_sensitive(value: Any, errors: list[str], path: str = "$") -> None:
    if isinstance(value, str):
        for token in SENSITIVE_TOKENS:
            if token in value:
                errors.append(f"{path}: contains sensitive token {token!r}")
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            scan_sensitive(item, errors, f"{path}[{idx}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            scan_sensitive(item, errors, f"{path}.{key}")


def validate_workspace(workspace: Path) -> list[str]:
    errors: list[str] = []
    docs: dict[str, Any] = {}

    for key, filename in REQUIRED_FILES.items():
        path = workspace / filename
        ensure(path.exists(), errors, f"missing required file: {filename}")
        if path.exists():
            docs[key] = load_json(path)

    if errors:
        return errors

    materials = docs["material_index"].get("materials", [])
    ensure(isinstance(materials, list) and materials, errors, "00_material_index.json: materials must be a non-empty list")
    for idx, item in enumerate(materials):
        require_fields(item, ["id", "path", "file_type", "source_bucket", "availability", "extract_policy"], errors, f"material[{idx}]")

    capabilities = docs["company_capability_library"].get("capabilities", [])
    ensure(isinstance(capabilities, list) and capabilities, errors, "01_company_capability_library.json: capabilities must be a non-empty list")
    capability_ids = set()
    for idx, item in enumerate(capabilities):
        require_fields(item, ["id", "name", "product_family", "capability_type", "scenarios", "source_refs", "confidence"], errors, f"capability[{idx}]")
        capability_ids.add(item.get("id"))

    requirements = docs["requirement_pack"].get("requirements", [])
    ensure(isinstance(requirements, list) and requirements, errors, "02_requirement_pack.json: requirements must be a non-empty list")
    requirement_ids = set()
    for idx, item in enumerate(requirements):
        require_fields(item, ["id", "scene", "roles", "pains", "target_state", "processes", "data_objects", "interfaces", "metrics", "capability_refs", "source_refs", "open_questions"], errors, f"requirement[{idx}]")
        requirement_ids.add(item.get("id"))

    matches = docs["capability_match_matrix"].get("matches", [])
    ensure(isinstance(matches, list) and matches, errors, "03_capability_match_matrix.json: matches must be a non-empty list")
    matched_req_ids = set()
    for idx, item in enumerate(matches):
        require_fields(item, ["requirement_id", "capability_ids", "fit_level", "rationale", "source_refs"], errors, f"match[{idx}]")
        matched_req_ids.add(item.get("requirement_id"))
        ensure(item.get("fit_level") in FIT_LEVELS, errors, f"match[{idx}]: invalid fit_level {item.get('fit_level')!r}")
        for cap_id in item.get("capability_ids", []):
            ensure(cap_id in capability_ids, errors, f"match[{idx}]: unknown capability_id {cap_id!r}")
    ensure(requirement_ids.issubset(matched_req_ids), errors, "not every requirement has a capability match")

    blueprint = docs["implementation_blueprint"]
    require_fields(blueprint, ["meta", "work_items", "stages"], errors, "implementation_blueprint")

    slides = docs["ppt_script"].get("slides", [])
    ensure(isinstance(slides, list) and slides, errors, "05_ppt_script.json: slides must be a non-empty list")
    slide_ids = set()
    for idx, item in enumerate(slides):
        require_fields(item, ["page_id", "title", "core_message", "narration", "visual_type", "requirement_refs", "capability_refs", "source_refs"], errors, f"slide[{idx}]")
        slide_ids.add(item.get("page_id"))
        for req_id in item.get("requirement_refs", []):
            ensure(req_id in requirement_ids, errors, f"slide[{idx}]: unknown requirement_ref {req_id!r}")
        for cap_id in item.get("capability_refs", []):
            ensure(cap_id in capability_ids, errors, f"slide[{idx}]: unknown capability_ref {cap_id!r}")

    visual_slides = docs["visual_plan"].get("slides", [])
    ensure(isinstance(visual_slides, list) and visual_slides, errors, "06_visual_plan.json: slides must be a non-empty list")
    visual_ids = set()
    for idx, item in enumerate(visual_slides):
        require_fields(item, ["page_id", "visual_type", "diagram_spec", "generation_method", "source_refs"], errors, f"visual_slide[{idx}]")
        visual_ids.add(item.get("page_id"))
    ensure(slide_ids.issubset(visual_ids), errors, "not every PPT script slide has a visual plan")

    for key in ("company_capability_library", "requirement_pack", "capability_match_matrix", "implementation_blueprint", "ppt_script", "visual_plan"):
        scan_sensitive(docs[key], errors, key)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a solution-factory artifact workspace.")
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()

    errors = validate_workspace(args.workspace)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
