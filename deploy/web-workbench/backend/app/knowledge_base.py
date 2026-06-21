from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import time

from .config import KNOWLEDGE_BASE_DIR, settings
from .codex_runner import run_codex_in_job
from .hermes_runner import run_hermes_oneshot
from .models import safe_job_path_name


EDITABLE_SUFFIXES = {".md", ".txt", ".csv"}
TEXT_CONTEXT_SUFFIXES = {".md", ".txt", ".csv"}
DIGEST_FILE = KNOWLEDGE_BASE_DIR / ".knowledge-base-digest.md"
DIGEST_META_FILE = KNOWLEDGE_BASE_DIR / ".knowledge-base-digest.meta.json"


def ensure_knowledge_base_seed() -> None:
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    readme = KNOWLEDGE_BASE_DIR / "00-知识库基线说明.md"
    if not readme.exists():
        readme.write_text(
            """# 公司知识库基线说明

这里放 Operator 登记的公司基线材料，例如标准能力说明、已审定方案片段、常用架构口径、PPT 风格规范和禁用表述。

当前版本先显示清单，帮助提交人知道系统会参考哪些基线。正式启用某份材料进入生成链路前，需要由 Operator 明确登记为安全基线。
""",
            encoding="utf-8",
        )


def list_knowledge_base_items() -> list[dict[str, object]]:
    ensure_knowledge_base_seed()
    items: list[dict[str, object]] = []
    for path in sorted(KNOWLEDGE_BASE_DIR.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        items.append(knowledge_base_item(path))
    return items


def knowledge_base_signature() -> str:
    ensure_knowledge_base_seed()
    payload = []
    for item in list_knowledge_base_items():
        payload.append(
            {
                "name": item["name"],
                "size_bytes": item["size_bytes"],
                "updated_at": round(float(item["updated_at"]), 3),
            }
        )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_knowledge_base_digest() -> dict[str, object]:
    ensure_knowledge_base_seed()
    items = list_knowledge_base_items()
    signature = knowledge_base_signature()
    meta = read_digest_meta()
    if not DIGEST_FILE.exists():
        return {
            "status": "empty",
            "content": "尚未整理公司知识库。请点击“交给 Codex 整理基线”，让大模型读取当前基线并生成可审阅摘要。",
            "updated_at": None,
            "stale": bool(items),
            "item_count": len(items),
            "provider": meta.get("provider", "codex"),
            "processing": bool(meta.get("processing")),
            "error": meta.get("error"),
        }

    content = DIGEST_FILE.read_text(encoding="utf-8", errors="replace").strip()
    return {
        "status": "ready",
        "content": content or "摘要文件为空，请重新整理基线。",
        "updated_at": meta.get("updated_at"),
        "stale": meta.get("signature") != signature,
        "item_count": len(items),
        "provider": meta.get("provider", "codex"),
        "processing": bool(meta.get("processing")),
        "error": meta.get("error"),
    }


def read_digest_meta() -> dict[str, object]:
    if not DIGEST_META_FILE.exists():
        return {}
    try:
        return json.loads(DIGEST_META_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def generate_knowledge_base_digest() -> dict[str, object]:
    ensure_knowledge_base_seed()
    mark_knowledge_base_digest_running()
    provider = "hermes" if settings.worker_mode == "hermes" else "codex"
    prompt = build_knowledge_base_digest_prompt()
    if provider == "hermes":
        prompt += "\n\n注意：当前通过 Hermes oneshot 调用，请直接输出摘要 Markdown 正文，不要使用代码块围栏，不要解释。后端会负责写入 `.knowledge-base-digest.md`。\n"
    if provider == "hermes":
        returncode, stdout, stderr, _command = run_hermes_oneshot(KNOWLEDGE_BASE_DIR, prompt)
    else:
        returncode, stdout, stderr, _command = run_codex_in_job(KNOWLEDGE_BASE_DIR, prompt)
    if returncode != 0:
        detail = (stderr or stdout or f"{provider} 整理基线失败").strip()
        mark_knowledge_base_digest_failed(detail[:1200])
        raise RuntimeError(detail[:1200])

    if provider == "hermes" and stdout.strip():
        content = stdout.strip()
        if content.startswith("```"):
            content = content.strip("`").strip()
        DIGEST_FILE.write_text(content + "\n", encoding="utf-8")
    else:
        content = DIGEST_FILE.read_text(encoding="utf-8", errors="replace").strip() if DIGEST_FILE.exists() else ""
    if not content and stdout.strip():
        content = stdout.strip()
        DIGEST_FILE.write_text(content + "\n", encoding="utf-8")
    if not content:
        mark_knowledge_base_digest_failed("大模型未生成基线消化摘要，请重试。")
        raise RuntimeError("大模型未生成基线消化摘要，请重试。")

    DIGEST_META_FILE.write_text(
        json.dumps(
            {
                "provider": provider,
                "processing": False,
                "error": None,
                "updated_at": int(time()),
                "signature": knowledge_base_signature(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return read_knowledge_base_digest()


def mark_knowledge_base_digest_running() -> None:
    provider = "hermes" if settings.worker_mode == "hermes" else "codex"
    DIGEST_META_FILE.write_text(
        json.dumps(
            {
                **read_digest_meta(),
                "provider": provider,
                "processing": True,
                "error": None,
                "started_at": int(time()),
                "signature": knowledge_base_signature(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def mark_knowledge_base_digest_failed(error: str) -> None:
    DIGEST_META_FILE.write_text(
        json.dumps(
            {
                **read_digest_meta(),
                "provider": "codex",
                "processing": False,
                "error": error,
                "failed_at": int(time()),
                "signature": knowledge_base_signature(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_knowledge_base_digest_prompt() -> str:
    inventory = build_knowledge_base_inventory(max_chars_per_file=8000, max_total_chars=60000)
    return f"""你是解决方案部 PPT 脚本生产台的公司知识库整理员。

任务：读取当前目录下已经登记的公司知识库基线，生成一份给普通同事看的“基线消化摘要”。

硬性要求：
- 必须使用中文。
- 必须把结果写入当前目录的 `.knowledge-base-digest.md`。
- 不要输出任何绝对本地路径。
- 不要编造文件正文里没有的能力、客户事实、金额、比例、上线时间或对接状态。
- 对无法可靠读取正文的 PPTX/DOCX/XLSX/PDF/图片，必须明确写“仅根据文件名/文件类型识别，正文未可靠消化”或“需补充文本版摘要”。
- 这份摘要用于后续 PPT 脚本生成，不是对外材料；要帮助同事知道系统会参考哪些公司口径、哪些内容没有被消化。

请按以下结构写 `.knowledge-base-digest.md`：

# 公司知识库基线消化摘要

## 1. 当前已登记基线
用表格列出：材料名称、识别状态、可用于脚本生成的内容、风险或需补充。

## 2. 已消化的公司通用口径
提炼稳定可复用的表达口径、方案能力、风格要求和禁用表述。

## 3. 生成 PPT 脚本时应优先遵循
列出后续脚本生成应遵守的 8-15 条规则，重点包括事实边界、能力边界、客户汇报表达、页面风格、待确认写法。

## 4. 暂未可靠识别的基线
列出无法从正文可靠读取的文件，并说明需要 Operator 或资料维护人补充什么文本说明。

## 5. 给同事的使用提醒
用小白能看懂的话说明：哪些内容系统已经能参考，哪些仍需要上传到具体任务或人工确认。

当前知识库清单和可读摘录如下：

{inventory}
"""


def knowledge_base_item(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "name": path.name,
        "size_bytes": stat.st_size,
        "kind": describe_kind(path),
        "updated_at": stat.st_mtime,
        "editable": is_editable_knowledge_base_item(path),
    }


def safe_knowledge_base_path(name: str) -> Path:
    ensure_knowledge_base_seed()
    safe_name = safe_job_path_name((name or "").strip())
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Invalid knowledge base filename")
    path = (KNOWLEDGE_BASE_DIR / safe_name).resolve()
    base = KNOWLEDGE_BASE_DIR.resolve()
    if path.parent != base:
        raise ValueError("Invalid knowledge base filename")
    return path


def is_editable_knowledge_base_item(path: Path) -> bool:
    return path.suffix.lower() in EDITABLE_SUFFIXES


def read_knowledge_base_content(name: str) -> str:
    path = safe_knowledge_base_path(name)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(name)
    if not is_editable_knowledge_base_item(path):
        raise ValueError("This knowledge base file is not editable as text")
    return path.read_text(encoding="utf-8", errors="replace")


def write_knowledge_base_content(name: str, content: str) -> dict[str, object]:
    path = safe_knowledge_base_path(name)
    if not is_editable_knowledge_base_item(path):
        raise ValueError("This knowledge base file is not editable as text")
    path.write_text(content, encoding="utf-8")
    return knowledge_base_item(path)


def delete_knowledge_base_item(name: str) -> None:
    path = safe_knowledge_base_path(name)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(name)
    path.unlink()


def build_knowledge_base_inventory(max_chars_per_file: int = 6000, max_total_chars: int = 36000) -> str:
    ensure_knowledge_base_seed()
    lines = ["# 公司知识库清单", ""]
    total_chars = 0
    items = list_knowledge_base_items()
    if not items:
        return "# 公司知识库清单\n\n- 暂无公司知识库基线。\n"
    for item in items:
        name = str(item["name"])
        path = safe_knowledge_base_path(name)
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- 类型：{item['kind']}")
        lines.append(f"- 大小：{item['size_bytes']} bytes")
        if path.suffix.lower() in TEXT_CONTEXT_SUFFIXES and total_chars < max_total_chars:
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if content:
                excerpt = content[:max_chars_per_file]
                total_chars += len(excerpt)
                if total_chars > max_total_chars:
                    overflow = total_chars - max_total_chars
                    excerpt = excerpt[:-overflow] if overflow < len(excerpt) else ""
                    total_chars = max_total_chars
                if excerpt:
                    lines.extend(["", "### 可读内容摘录", "", excerpt])
                if len(content) > len(excerpt):
                    lines.append("\n- 备注：内容较长，已截取前部进入生成上下文。")
            else:
                lines.append("- 备注：文本为空。")
        else:
            lines.append("- 备注：非文本类基线，本轮只进入清单，不抽取正文。")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def describe_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return "文本基线"
    if suffix in {".pptx", ".pdf", ".docx"}:
        return "方案资料"
    if suffix in {".xlsx", ".csv"}:
        return "表格资料"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "图片参考"
    return "基线资料"
