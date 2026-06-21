#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STYLE_ASSET = PLUGIN_ROOT / "assets" / "notebooklm-image-ppt-style.zh-CN.md"
WORKER_TIMEOUT_SECONDS = int(os.environ.get("SOLUTION_FACTORY_WORKER_TIMEOUT_SECONDS", "1200"))
ALLOWED_EXTENSIONS = {
    ".docx",
    ".pdf",
    ".xlsx",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".md",
    ".txt",
    ".csv",
}
EDITABLE_TEXT_EXTENSIONS = {".md", ".txt", ".csv"}
TEXT_CONTEXT_EXTENSIONS = {".md", ".txt", ".csv"}
MAX_PAGES = 80


@dataclass(slots=True)
class UploadedFile:
    filename: str
    stored_name: str
    size_bytes: int


@dataclass(slots=True)
class JobStatus:
    job_id: str
    requester_name: str
    title: str
    pages: int | None
    scenario: str = ""
    audience: str = ""
    style: str = "解决方案风"
    status: str = "created"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    error: str | None = None
    uploaded_files: list[UploadedFile] = field(default_factory=list)
    stage_artifacts: dict[str, list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class SourceText:
    filename: str
    stored_name: str
    size_bytes: int
    text: str
    status: str
    note: str


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_path_name(value: str) -> str:
    name = Path(value or "upload.bin").name.replace("/", "_").replace("\\", "_")
    return name or "upload.bin"


def workspace_id(requester_name: str) -> str:
    digest = hashlib.sha1(requester_name.strip().encode("utf-8")).hexdigest()[:10]
    return f"person_{digest}"


def job_root_from_args(args: argparse.Namespace) -> Path:
    if getattr(args, "job_root", None):
        return Path(args.job_root).expanduser().resolve()
    output_root = Path(getattr(args, "output_root", "outputs/solution-factory/server-workbench")).expanduser().resolve()
    requester = safe_path_name(getattr(args, "requester", "operator"))
    job_id = getattr(args, "job_id", "") or f"job_{uuid.uuid4().hex[:12]}"
    return output_root / "storage" / "workspaces" / workspace_id(requester) / "jobs" / safe_path_name(job_id)


def create_job_dirs(job_dir: Path) -> None:
    for relative in (
        "input",
        "work/01_requirements/pages",
        "work/02_image_ppt/prompts",
        "work/02_image_ppt/results",
        "output",
    ):
        (job_dir / relative).mkdir(parents=True, exist_ok=True)


def read_status(job_dir: Path) -> JobStatus:
    data = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    data["uploaded_files"] = [UploadedFile(**item) for item in data.get("uploaded_files", [])]
    return JobStatus(**data)


def write_status(job_dir: Path, status: JobStatus) -> None:
    status.updated_at = now()
    payload = asdict(status)
    (job_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_log(job_dir: Path, message: str) -> None:
    log_path = job_dir / "logs.txt"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now()}] {message.rstrip()}\n")


def expand_sources(paths: list[str]) -> list[Path]:
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in ALLOWED_EXTENSIONS:
                    expanded.append(child)
        elif path.is_file():
            expanded.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in expanded:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def copy_inputs(job_dir: Path, source_paths: list[Path], source_text: str) -> list[UploadedFile]:
    uploaded: list[UploadedFile] = []
    for path in source_paths:
        suffix = path.suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            continue
        safe_name = safe_path_name(path.name)
        stored_name = f"{uuid.uuid4().hex[:10]}-{safe_name}"
        destination = job_dir / "input" / stored_name
        shutil.copy2(path, destination)
        uploaded.append(UploadedFile(filename=safe_name, stored_name=stored_name, size_bytes=destination.stat().st_size))
    if source_text.strip():
        stored_name = f"{uuid.uuid4().hex[:10]}-pasted-material.md"
        destination = job_dir / "input" / stored_name
        destination.write_text("# 粘贴文字资料\n\n" + source_text.strip() + "\n", encoding="utf-8")
        uploaded.append(UploadedFile(filename="粘贴文字资料.md", stored_name=stored_name, size_bytes=destination.stat().st_size))
    return uploaded


def extract_text(path: Path) -> tuple[str, str, str]:
    suffix = path.suffix.lower()
    if not path.exists():
        return "", "missing", "文件不存在"
    if suffix in TEXT_CONTEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="replace"), "readable", "已读取文本"
    if suffix in {".docx", ".pptx", ".xlsx"}:
        return extract_office_zip_text(path, suffix)
    if suffix == ".pdf":
        raw = path.read_bytes()
        decoded = raw.decode("utf-8", errors="ignore")
        text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff，。；：、（）《》！？%./_ -]+", " ", decoded)
        if len(text.strip()) >= 80:
            return text, "partial", "PDF 已尝试读取可见文本；复杂 PDF 仍建议后续接 OCR/解析器"
        return "", "needs_parser", "PDF 暂未接入可靠解析器，需要后续解析或人工补充"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "", "needs_ocr", "图片暂未接入 OCR，需要后续 OCR 或人工补充"
    return "", "unsupported", f"暂不支持 {suffix} 自动抽取"


def extract_office_zip_text(path: Path, suffix: str) -> tuple[str, str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if suffix == ".docx":
                candidates = [name for name in names if name.startswith("word/") and name.endswith(".xml")]
            elif suffix == ".pptx":
                candidates = sorted(
                    [name for name in names if name.startswith("ppt/slides/") and name.endswith(".xml")],
                    key=office_slide_sort_key,
                )
            else:
                candidates = [name for name in names if name.startswith("xl/") and name.endswith(".xml")]
            chunks: list[str] = []
            for name in candidates[:100]:
                values = iter_xml_text(archive.read(name))
                if suffix == ".pptx" and values:
                    chunks.append(f"[PPT第{office_slide_sort_key(name)}页] " + " ".join(values))
                else:
                    chunks.extend(values)
    except Exception as exc:  # noqa: BLE001
        return "", "parse_failed", f"解析失败：{exc}"
    text = "\n".join(chunks)
    if text.strip():
        return text, "readable", "已读取 Office XML 文本"
    return "", "empty", "未抽取到可读文本"


def office_slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 9999


def iter_xml_text(xml: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        text = re.sub(r"<[^>]+>", " ", xml.decode("utf-8", errors="ignore"))
        return [text.strip()] if text.strip() else []
    values: list[str] = []
    for node in root.iter():
        if node.text and node.text.strip():
            values.append(node.text.strip())
    return values


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def meaningful_lines(text: str, limit: int = 36) -> list[str]:
    lines: list[str] = []
    for raw in re.split(r"[\n。；;]+", text):
        line = raw.strip(" -\t")
        if len(line) < 6:
            continue
        if line not in lines:
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def collect_source_texts(job_dir: Path, status: JobStatus) -> list[SourceText]:
    sources: list[SourceText] = []
    for item in status.uploaded_files:
        path = job_dir / "input" / item.stored_name
        text, extract_status, note = extract_text(path)
        sources.append(SourceText(item.filename, item.stored_name, item.size_bytes, clean_text(text), extract_status, note))
    return sources


def build_source_inventory(sources: list[SourceText]) -> str:
    if not sources:
        return "# 资料清单\n\n- 无上传文件；本次只能依据任务表单信息生成需求草稿。\n"
    rows = ["# 资料清单", "", "| 文件 | 大小 | 抽取状态 | 说明 |", "|---|---:|---|---|"]
    for source in sources:
        rows.append(f"| {source.filename} | {source.size_bytes} bytes | {source.status} | {source.note} |")
    rows.append("")
    rows.append("## 可读资料摘要")
    for source in sources:
        excerpt = "\n".join(meaningful_lines(source.text, limit=8)) if source.text else "无可读文本。"
        rows.extend(["", f"### {source.filename}", "", excerpt])
    return "\n".join(rows).strip() + "\n"


def build_knowledge_inventory(paths: list[str], max_chars_per_file: int = 4000, max_total_chars: int = 30000) -> str:
    files = expand_sources(paths)
    if not files:
        return "# 公司知识库清单\n\n- 未提供公司知识库或基线材料。\n"
    rows = ["# 公司知识库清单", "", "| 材料 | 类型 | 识别状态 | 可用摘录 |", "|---|---|---|---|"]
    used = 0
    for path in files:
        text, status, note = extract_text(path)
        excerpt = "；".join(meaningful_lines(clean_text(text), limit=6))
        excerpt = excerpt[:max_chars_per_file]
        used += len(excerpt)
        if used > max_total_chars:
            excerpt = "已达到知识库上下文上限，本文件仅登记清单。"
        rows.append(f"| {path.name} | {path.suffix.lower().lstrip('.')} | {status} | {note}；{excerpt or '无可读摘录'} |")
    rows.append("")
    rows.append("说明：公司知识库只作为能力口径、标准表述和风格参考；客户事实仍必须来自当前任务材料或标注待确认。")
    return "\n".join(rows).strip() + "\n"


def build_facts(status: JobStatus, sources: list[SourceText]) -> str:
    lines = ["# 事实摘录", "", "## 表单事实"]
    lines.append(f"- PPT 标题：{status.title}")
    lines.append(f"- 提交人：{status.requester_name}")
    lines.append(f"- 建议页数：{status.pages or '未填写，系统按材料建议'}")
    lines.append(f"- 使用场景：{status.scenario or '未填写'}")
    lines.append(f"- 受众对象：{status.audience or '未填写'}")
    lines.append("")
    lines.append("## 材料事实")
    material_lines: list[str] = []
    for source in sources:
        for line in meaningful_lines(source.text, limit=12):
            material_lines.append(f"- [{source.filename}] {line}")
    lines.extend(material_lines[:60] if material_lines else ["- 未从上传资料中抽取到可用文本事实。"])
    return "\n".join(lines).strip() + "\n"


def build_open_questions(status: JobStatus, sources: list[SourceText]) -> str:
    questions = [
        "# 待确认事项",
        "",
        "- 客户已有系统、接口开放程度、数据权限和账号边界需要确认。",
        "- 页面中涉及数量、比例、金额、点位、上线时间、组织名称时，必须有材料依据后才能写成确定事实。",
        "- 图片、扫描 PDF 或无法抽取文本的资料，需要 OCR/人工补充后才能纳入事实。",
    ]
    if not status.audience:
        questions.append("- 受众对象未填写，需确认是客户领导、业务负责人、技术团队还是内部评审。")
    if not status.scenario:
        questions.append("- 使用场景未填写，需确认是客户汇报、投标、内部评审还是方案预沟通。")
    unreadable = [source.filename for source in sources if source.status not in {"readable", "partial"}]
    if unreadable:
        questions.append("- 以下资料未可靠抽取文本：" + "、".join(unreadable))
    return "\n".join(questions).strip() + "\n"


def build_requirement_summary(status: JobStatus, sources: list[SourceText], facts: str, open_questions: str) -> str:
    readable_count = sum(1 for source in sources if source.status in {"readable", "partial"})
    return f"""# 需求梳理

## 结论

本次已基于任务表单和上传资料生成当前任务的资料清单、事实摘录、待确认事项和模型执行提示。

- 标题：{status.title}
- 可读资料数：{readable_count}
- 上传资料数：{len(sources)}
- 风格：{status.style}

## 事实摘录

{facts.strip()}

## 待确认事项

{open_questions.strip()}
"""


def read_style_prompt(path: str | None) -> str:
    if path:
        candidate = Path(path).expanduser()
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace").strip()
    if DEFAULT_STYLE_ASSET.exists():
        return DEFAULT_STYLE_ASSET.read_text(encoding="utf-8", errors="replace").strip()
    return "蓝色企业汇报风，16:9，浅蓝灰背景，深蓝标题条，技术图示清晰，中文文字可读。"


def build_model_prompt(job_dir: Path, status: JobStatus, style_prompt: str) -> str:
    page_count = max(2, min(int(status.pages or 8), MAX_PAGES))
    return f"""你是解决方案部 PPT 脚本生产台的执行者。请只在当前任务目录内读写文件。

目标：根据 `prompt.md`、`input/` 上传材料、已有 `work/01_requirements/source-inventory.md`、`knowledge-base-inventory.md`、`facts.md`、`open-questions.md`，生成可审阅的逐页 PPT 生产脚本和逐页图片生产提示词。

当前产品只生成脚本和提示词，不生成图片 PPT，不生成 PPTX，不生成可编辑 PPT。

硬性要求：
- 必须生成 {page_count} 页，不能少页，不能多页；封面和目录包含在总页数内。
- P01 必须是封面页，标题为项目/方案名称。
- P02 必须是目录页，列出后续正文页章节结构。
- 所有用户可见内容必须是中文。
- 不要编造客户名称、设备数量、金额、比例、接口状态、上线时间、品牌型号或已完成状态。
- 材料没有明确依据的内容写成“待确认”或“待补充”。
- 严禁使用“专题深化 9”“补充页”“未命名页面”“待定页面”等占位标题。
- 每页必须有明确来源依据、图示结构、Page-specific source of truth、页面设计 Brief、讲稿、审核备注。
- Page-specific source of truth 必须写清页面目标、版式要求、图示结构、模块节点、必须出现的关键词、上屏文字、讲稿要点、视觉注意、事实与能力边界和禁止事项。
- “公司知识库”只能作为能力口径和表达方式依据；客户现场情况必须来自上传材料或标注待确认。

使用场景：{status.scenario or "未填写"}
受众对象：{status.audience or "未填写"}
风格：{status.style}

风格提示：
{style_prompt}

请写回这些文件：
1. `work/01_requirements/01_requirements.md`
2. `work/01_requirements/facts.md`
3. `work/01_requirements/open-questions.md`
4. `work/01_requirements/generation-mode.md`
5. `work/01_requirements/model-generation.md`
6. `work/01_requirements/ppt-script.md`

`ppt-script.md` 必须严格使用下面格式，每页一个二级标题，页码连续：

# 当前任务逐页PPT脚本

## P01 页面标题

- 核心观点：一句话说明本页要让受众形成什么判断。
- 页面类型：cover / agenda / background / requirement_analysis / architecture / business_flow / data_flow / ai_capability / implementation_roadmap / value_summary / deep_dive 等。
- 使用场景：{status.scenario or "待确认"}
- 受众对象：{status.audience or "待确认"}

来源依据：

- 区分“客户材料事实”和“公司知识库口径”；没有客户材料依据就写“待补充/待客户确认”。

图示结构：

- 说明本页适合使用的图示结构，必须可被图片 PPT 阶段直接理解。

Page-specific source of truth：

- 页面目标：
- 版式要求：
- 图示结构：
- 必须出现的关键词：
- 上屏文字：
- 讲稿要点：
- 视觉注意：
- 事实与能力边界：
- 禁止事项：

页面设计 Brief：

- 用 5 到 8 条中文摘要复述当前页设计真值。

讲稿：

用 1 到 3 段中文说明本页讲述逻辑。

审核备注：列出本页进入图片 PPT 前必须确认的边界。
"""


def write_initial_artifacts(job_dir: Path, status: JobStatus, knowledge_paths: list[str], style_prompt: str) -> None:
    sources = collect_source_texts(job_dir, status)
    source_inventory = build_source_inventory(sources)
    knowledge_inventory = build_knowledge_inventory(knowledge_paths)
    facts = build_facts(status, sources)
    open_questions = build_open_questions(status, sources)
    requirement_dir = job_dir / "work" / "01_requirements"
    image_dir = job_dir / "work" / "02_image_ppt"
    (requirement_dir / "source-inventory.md").write_text(source_inventory, encoding="utf-8")
    (requirement_dir / "knowledge-base-inventory.md").write_text(knowledge_inventory, encoding="utf-8")
    (requirement_dir / "facts.md").write_text(facts, encoding="utf-8")
    (requirement_dir / "open-questions.md").write_text(open_questions, encoding="utf-8")
    (requirement_dir / "01_requirements.md").write_text(build_requirement_summary(status, sources, facts, open_questions), encoding="utf-8")
    (requirement_dir / "generation-mode.md").write_text(
        "# 生成模式\n\n- 当前逐页脚本生成模式：empty_initial\n- 说明：新任务默认不生成占位页。请运行模型生成或导入经审核的逐页脚本后，再导出脚本包。\n",
        encoding="utf-8",
    )
    (requirement_dir / "page-index.json").write_text("[]\n", encoding="utf-8")
    (image_dir / "style-prompt.md").write_text(style_prompt.rstrip() + "\n", encoding="utf-8")
    status.stage_artifacts = {
        "requirement_intake": [
            "work/01_requirements/01_requirements.md",
            "work/01_requirements/source-inventory.md",
            "work/01_requirements/knowledge-base-inventory.md",
            "work/01_requirements/facts.md",
            "work/01_requirements/open-questions.md",
            "work/01_requirements/generation-mode.md",
            "work/01_requirements/page-index.json",
        ],
        "script_prompts": ["work/02_image_ppt/style-prompt.md"],
    }
    prompt = build_model_prompt(job_dir, status, style_prompt)
    (job_dir / "prompt.md").write_text(prompt, encoding="utf-8")


def parse_ppt_script(script: str) -> list[dict[str, object]]:
    pattern = re.compile(r"^##\s*P(\d{1,2})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(script))
    pages: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        page_no = int(match.group(1))
        title = match.group(2).strip()
        content = script[start:end].strip()
        if title and content:
            pages.append({"page_no": page_no, "title": title, "script": content})
    pages.sort(key=lambda page: int(page["page_no"]))
    return pages


def extract_model_script(stdout: str) -> str:
    text = stdout.strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(# 当前任务逐页PPT脚本.*?)(?:\n```|$)", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("# 当前任务逐页PPT脚本")
    if start >= 0:
        text = text[start:].strip()
    elif match := re.search(r"^##\s*P\d{2}\s+", text, flags=re.MULTILINE):
        text = "# 当前任务逐页PPT脚本\n\n" + text[match.start() :].strip()
    return text if "## P01" in text else ""


def extract_script_section(script: str, heading: str, stop_headings: tuple[str, ...]) -> str:
    start = re.search(re.escape(heading) + r"\s*[：:]", script)
    if not start:
        return ""
    tail = script[start.end() :]
    stops = []
    for stop_heading in stop_headings:
        stop = re.search(r"\n\s*" + re.escape(stop_heading) + r"\s*[：:]", tail)
        if stop:
            stops.append(stop.start())
    return tail[: min(stops)].strip() if stops else tail.strip()


def validate_page_scripts(page_scripts: list[dict[str, object]], expected_pages: int | None = None) -> list[str]:
    errors: list[str] = []
    if expected_pages is not None and len(page_scripts) != expected_pages:
        errors.append(f"页数不一致：实际 {len(page_scripts)} 页，目标 {expected_pages} 页")
    if page_scripts:
        first_title = str(page_scripts[0]["title"])
        first_script = str(page_scripts[0]["script"])
        if "封面" not in first_title and "页面类型：cover" not in first_script and "页面类型：封面" not in first_script:
            errors.append("P01 必须是封面页")
    if len(page_scripts) >= 2:
        second_title = str(page_scripts[1]["title"])
        second_script = str(page_scripts[1]["script"])
        if "目录" not in second_title and "页面类型：agenda" not in second_script and "页面类型：目录" not in second_script:
            errors.append("P02 必须是目录页")
    titles = [str(page["title"]).strip() for page in page_scripts]
    duplicates = sorted({title for title in titles if titles.count(title) > 1})
    if duplicates:
        errors.append("存在重复页面标题：" + "、".join(duplicates[:5]))
    placeholder = re.compile(r"(专题深化\s*\d+|补充页|未命名|待定页面|页面标题)")
    bad_titles = [f"P{int(page['page_no']):02d}" for page in page_scripts if placeholder.search(str(page["title"]))]
    if bad_titles:
        errors.append("存在占位标题：" + "、".join(bad_titles[:5]))
    thin_pages = [
        f"P{int(page['page_no']):02d}"
        for page in page_scripts
        if "来源依据" not in str(page["script"])
        or "图示结构" not in str(page["script"])
        or "Page-specific source of truth" not in str(page["script"])
        or "页面设计 Brief" not in str(page["script"])
        or "审核备注" not in str(page["script"])
    ]
    if thin_pages:
        errors.append("缺少来源依据/图示结构/Page-specific source of truth/页面设计 Brief/审核备注：" + "、".join(thin_pages[:5]))
    required_truth_labels = ("页面目标", "版式要求", "图示结构", "必须出现的关键词", "上屏文字", "视觉注意", "事实与能力边界", "禁止事项")
    weak_truth_pages: list[str] = []
    for page in page_scripts:
        truth_body = extract_script_section(str(page["script"]), "Page-specific source of truth", ("页面设计 Brief", "讲稿", "审核备注"))
        truth_lines = [line for line in truth_body.splitlines() if line.strip().startswith("-")]
        missing = [label for label in required_truth_labels if label not in truth_body]
        if len(truth_body) < 260 or len(truth_lines) < 8 or missing:
            weak_truth_pages.append(f"P{int(page['page_no']):02d}")
    if weak_truth_pages:
        errors.append("Page-specific source of truth 颗粒度不足：" + "、".join(weak_truth_pages[:5]))
    return errors


def build_image_prompt(page_no: int, title: str, script: str, style_prompt: str) -> str:
    return f"""# P{page_no:02d} {title} 图片生产提示词

你是图片式 PPT 页面生成智能体。请严格根据本页脚本生成 16:9 企业汇报页面。

## 风格要求

{style_prompt}

## 本页脚本

{script}

## 执行要求

- 保留中文可读性，不要生成乱码。
- 主体图示必须按 Page-specific source of truth 的节点、层级、流程和边界绘制。
- 待确认、待补充、待对接内容必须以醒目的小标签标注。
- 不要新增脚本中没有的客户事实、数量、金额、比例、品牌型号、接口状态或上线状态。
"""


def write_page_workspace(job_dir: Path, status: JobStatus, pages: list[dict[str, object]], style_prompt: str, mode: str) -> None:
    page_index = []
    for item in pages:
        page_no = int(item["page_no"])
        title = str(item["title"])
        script = str(item["script"]).strip()
        script_path = f"work/01_requirements/pages/page-{page_no:02d}.md"
        prompt_path = f"work/02_image_ppt/prompts/slide-{page_no:02d}.md"
        result_path = f"work/02_image_ppt/results/page-{page_no:02d}.md"
        (job_dir / script_path).write_text(script + "\n", encoding="utf-8")
        (job_dir / prompt_path).write_text(build_image_prompt(page_no, title, script, style_prompt), encoding="utf-8")
        (job_dir / result_path).write_text(
            f"# P{page_no:02d} 脚本产物\n\n本页已完成页面脚本和图片生产提示词。当前插件第一生产路径不生成图片 PPT 或可编辑 PPTX。\n",
            encoding="utf-8",
        )
        page_index.append(
            {
                "page_id": f"p{page_no:02d}",
                "page_no": page_no,
                "title": title,
                "script_path": script_path,
                "prompt_path": prompt_path,
                "result_path": result_path,
                "script_state": mode,
                "prompt_state": "ready",
                "result_state": "not_started",
                "updated_at": now(),
            }
        )
    (job_dir / "work/01_requirements/page-index.json").write_text(json.dumps(page_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script_body = "# 当前任务逐页PPT脚本\n\n" + "\n\n".join(str(item["script"]).strip() for item in pages) + "\n"
    (job_dir / "work/01_requirements/ppt-script.md").write_text(script_body, encoding="utf-8")
    status.stage_artifacts["requirement_intake"] = sorted(
        set(status.stage_artifacts.get("requirement_intake", []) + ["work/01_requirements/ppt-script.md", "work/01_requirements/page-index.json"] + [item["script_path"] for item in page_index])
    )
    status.stage_artifacts["script_prompts"] = sorted(
        set(status.stage_artifacts.get("script_prompts", []) + [item["prompt_path"] for item in page_index])
    )
    status.status = "needs_human_review"
    status.error = None
    write_status(job_dir, status)


def run_model(job_dir: Path, provider: str, prompt: str) -> tuple[int, str, str, list[str]]:
    if provider == "codex":
        command = [
            os.environ.get("CODEX_BIN", "codex"),
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--cd",
            str(job_dir),
            "-",
        ]
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, timeout=WORKER_TIMEOUT_SECONDS, check=False)
        return result.returncode, result.stdout, result.stderr, command
    if provider == "hermes":
        command = [os.environ.get("HERMES_BIN", "hermes"), "--ignore-rules", "-z", prompt]
        if os.environ.get("HERMES_MODEL"):
            command.extend(["--model", os.environ["HERMES_MODEL"]])
        if os.environ.get("HERMES_PROVIDER"):
            command.extend(["--provider", os.environ["HERMES_PROVIDER"]])
        result = subprocess.run(command, capture_output=True, text=True, cwd=job_dir, timeout=WORKER_TIMEOUT_SECONDS, check=False)
        redacted = [command[0], "--ignore-rules", "-z", "<prompt>"]
        return result.returncode, result.stdout, result.stderr, redacted
    raise ValueError(f"Unsupported provider: {provider}")


def package_job(job_dir: Path) -> Path:
    output = job_dir / "output"
    output.mkdir(parents=True, exist_ok=True)
    package_path = output / "script-package.zip"
    include_roots = [
        "prompt.md",
        "status.json",
        "logs.txt",
        "work/01_requirements",
        "work/02_image_ppt/prompts",
        "work/02_image_ppt/style-prompt.md",
    ]
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in include_roots:
            path = job_dir / relative
            if not path.exists():
                continue
            if path.is_file():
                archive.write(path, relative)
            else:
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        archive.write(child, child.relative_to(job_dir).as_posix())
    return package_path


def command_init(args: argparse.Namespace) -> int:
    job_dir = job_root_from_args(args)
    create_job_dirs(job_dir)
    source_text = Path(args.source_text_file).read_text(encoding="utf-8") if args.source_text_file else args.source_text
    uploaded = copy_inputs(job_dir, expand_sources(args.source), source_text)
    status = JobStatus(
        job_id=job_dir.name,
        requester_name=args.requester.strip(),
        title=args.title.strip(),
        pages=args.pages,
        scenario=args.scenario,
        audience=args.audience,
        style=args.style,
        uploaded_files=uploaded,
    )
    style_prompt = read_style_prompt(args.style_prompt_file)
    write_initial_artifacts(job_dir, status, args.knowledge_base, style_prompt)
    write_status(job_dir, status)
    append_log(job_dir, "Job initialized.")
    print(job_dir)
    return 0


def command_import_script(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_root).expanduser().resolve()
    status = read_status(job_dir)
    script = Path(args.script).read_text(encoding="utf-8", errors="replace")
    if not script.lstrip().startswith("# 当前任务逐页PPT脚本"):
        script = "# 当前任务逐页PPT脚本\n\n" + script.strip() + "\n"
    pages = parse_ppt_script(script)
    expected = args.pages if args.pages is not None else status.pages
    errors = validate_page_scripts(pages, expected)
    if errors:
        status.status = "needs_human_review"
        status.error = "；".join(errors)
        write_status(job_dir, status)
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    style_prompt_path = job_dir / "work/02_image_ppt/style-prompt.md"
    style_prompt = style_prompt_path.read_text(encoding="utf-8", errors="replace") if style_prompt_path.exists() else read_style_prompt(None)
    write_page_workspace(job_dir, status, pages, style_prompt, "imported_script")
    package_path = package_job(job_dir)
    append_log(job_dir, f"Imported script and packaged {package_path.name}.")
    print(package_path)
    return 0


def command_run_model(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_root).expanduser().resolve()
    status = read_status(job_dir)
    prompt = (job_dir / "prompt.md").read_text(encoding="utf-8")
    status.status = "requirement_intake"
    write_status(job_dir, status)
    returncode, stdout, stderr, command = run_model(job_dir, args.provider, prompt)
    append_log(job_dir, f"Model command: {' '.join(command[:6])}")
    if stdout:
        (job_dir / "output/model-stdout.txt").write_text(stdout, encoding="utf-8")
    if stderr:
        (job_dir / "output/model-stderr.txt").write_text(stderr, encoding="utf-8")
    if returncode != 0:
        status.status = "failed"
        status.error = f"{args.provider} returned {returncode}"
        write_status(job_dir, status)
        print(status.error, file=sys.stderr)
        return returncode
    script = extract_model_script(stdout)
    script_path = job_dir / "work/01_requirements/ppt-script.md"
    if script:
        script_path.write_text(script.rstrip() + "\n", encoding="utf-8")
    elif script_path.exists():
        script = script_path.read_text(encoding="utf-8", errors="replace")
    else:
        status.status = "failed"
        status.error = "模型未返回可解析的 ppt-script.md"
        write_status(job_dir, status)
        print(status.error, file=sys.stderr)
        return 1
    temp_script = job_dir / "output/model-ppt-script.md"
    temp_script.write_text(script, encoding="utf-8")
    args.script = str(temp_script)
    args.pages = status.pages
    return command_import_script(args)


def command_validate(args: argparse.Namespace) -> int:
    job_dir = Path(args.job_root).expanduser().resolve()
    errors: list[str] = []
    for relative in (
        "prompt.md",
        "status.json",
        "logs.txt",
        "work/01_requirements/source-inventory.md",
        "work/01_requirements/knowledge-base-inventory.md",
        "work/01_requirements/facts.md",
        "work/01_requirements/open-questions.md",
        "work/01_requirements/generation-mode.md",
        "work/01_requirements/page-index.json",
        "work/02_image_ppt/style-prompt.md",
    ):
        if not (job_dir / relative).exists():
            errors.append(f"missing {relative}")
    status = read_status(job_dir)
    script_path = job_dir / "work/01_requirements/ppt-script.md"
    if args.require_pages:
        if not script_path.exists():
            errors.append("missing work/01_requirements/ppt-script.md")
        else:
            pages = parse_ppt_script(script_path.read_text(encoding="utf-8", errors="replace"))
            errors.extend(validate_page_scripts(pages, status.pages))
            for page in pages:
                no = int(page["page_no"])
                if not (job_dir / f"work/02_image_ppt/prompts/slide-{no:02d}.md").exists():
                    errors.append(f"missing prompt for P{no:02d}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {job_dir}")
    return 0


def command_package(args: argparse.Namespace) -> int:
    package_path = package_job(Path(args.job_root).expanduser().resolve())
    print(package_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable Solution Factory script-production workbench.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a server/local script-production job workspace.")
    init.add_argument("--output-root", default="outputs/solution-factory/server-workbench")
    init.add_argument("--job-id", default="")
    init.add_argument("--requester", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--pages", type=int, default=None)
    init.add_argument("--scenario", default="")
    init.add_argument("--audience", default="")
    init.add_argument("--style", default="解决方案风")
    init.add_argument("--style-prompt-file", default="")
    init.add_argument("--source", action="append", default=[])
    init.add_argument("--knowledge-base", action="append", default=[])
    init.add_argument("--source-text", default="")
    init.add_argument("--source-text-file", default="")
    init.set_defaults(func=command_init)

    imp = sub.add_parser("import-script", help="Import and validate an externally generated ppt-script.md.")
    imp.add_argument("job_root")
    imp.add_argument("--script", required=True)
    imp.add_argument("--pages", type=int, default=None)
    imp.set_defaults(func=command_import_script)

    run = sub.add_parser("run-model", help="Run a verified model adapter and write page workspaces.")
    run.add_argument("job_root")
    run.add_argument("--provider", choices=["codex", "hermes"], required=True)
    run.set_defaults(func=command_run_model)

    validate = sub.add_parser("validate", help="Validate a job workspace.")
    validate.add_argument("job_root")
    validate.add_argument("--require-pages", action="store_true")
    validate.set_defaults(func=command_validate)

    package = sub.add_parser("package", help="Create output/script-package.zip.")
    package.add_argument("job_root")
    package.set_defaults(func=command_package)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
