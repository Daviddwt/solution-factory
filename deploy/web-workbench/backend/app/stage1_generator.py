from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

from .case_templates import build_page_prompt_from_script
from .models import DeckPage, JobStatus, utcish_now


@dataclass(slots=True)
class SourceText:
    filename: str
    stored_name: str
    size_bytes: int
    text: str
    status: str
    note: str


PAGE_BLUEPRINTS = [
    ("封面", "cover", "明确项目名称、汇报对象和本次材料性质，建立正式汇报入口。"),
    ("目录", "agenda", "列出本次汇报的章节结构，让受众先看清整体逻辑。"),
    ("项目背景与目标定位", "background", "讲清楚项目为什么要做、希望解决什么问题，以及汇报对象需要先形成的共识。"),
    ("现状痛点与需求边界", "requirement_analysis", "从材料中提炼现状问题、业务诉求、能力边界和不能编造的事实。"),
    ("总体方案架构", "architecture", "把业务目标拆成平台、数据、应用、集成和治理等层次。"),
    ("核心业务流程", "business_flow", "把关键业务路径画成从触发、处理、反馈到闭环的流程。"),
    ("数据与系统集成", "data_flow", "明确数据来源、接口、系统对接和待确认边界。"),
    ("AI能力与自动化协同", "ai_capability", "说明 AI、流程、工单、知识库或自动化在方案里的作用和边界。"),
    ("实施路径与里程碑", "implementation_roadmap", "拆分调研、设计、试点、上线、验收和持续优化。"),
    ("价值总结与待确认事项", "closing", "收束业务价值，同时把客户必须确认的事项前置。"),
]

MAX_BOOTSTRAP_PAGES = 80


def generate_stage1_artifacts(job_dir: Path, status: JobStatus) -> list[DeckPage]:
    sources = collect_source_texts(job_dir, status)
    source_inventory = build_source_inventory(sources)
    facts = extract_facts(status, sources)
    open_questions = build_open_questions(status, sources)
    pages, generation_mode = build_page_scripts(status, sources, facts)

    requirement_dir = job_dir / "work" / "01_requirements"
    image_dir = job_dir / "work" / "02_image_ppt"
    pages_dir = requirement_dir / "pages"
    prompts_dir = image_dir / "prompts"
    results_dir = image_dir / "results"
    pages_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    requirement_dir.joinpath("source-inventory.md").write_text(source_inventory, encoding="utf-8")
    requirement_dir.joinpath("facts.md").write_text(facts, encoding="utf-8")
    requirement_dir.joinpath("open-questions.md").write_text(open_questions, encoding="utf-8")
    requirement_dir.joinpath("01_requirements.md").write_text(
        build_requirement_summary(status, sources, facts, open_questions), encoding="utf-8"
    )
    requirement_dir.joinpath("generation-mode.md").write_text(
        build_generation_mode_note(generation_mode), encoding="utf-8"
    )
    requirement_dir.joinpath("ppt-script.md").write_text(
        "# 当前任务逐页PPT脚本\n\n" + "\n\n".join(page["script"] for page in pages) + "\n", encoding="utf-8"
    )

    deck_pages: list[DeckPage] = []
    now = utcish_now()
    for page in pages:
        page_no = int(page["page_no"])
        title = str(page["title"])
        script = str(page["script"])
        script_path = f"work/01_requirements/pages/page-{page_no:02d}.md"
        prompt_path = f"work/02_image_ppt/prompts/slide-{page_no:02d}.md"
        result_path = f"work/02_image_ppt/results/page-{page_no:02d}.md"
        job_dir.joinpath(script_path).write_text(script.rstrip() + "\n", encoding="utf-8")
        prompt = build_image_prompt(status, page_no, title, script)
        job_dir.joinpath(prompt_path).write_text(prompt, encoding="utf-8")
        job_dir.joinpath(result_path).write_text(
            f"# P{page_no:02d} 生成结果\n\n本页图片尚未生成。第二步会读取 `work/02_image_ppt/prompts/slide-{page_no:02d}.md`。\n",
            encoding="utf-8",
        )
        deck_pages.append(
            DeckPage(
                page_id=f"p{page_no:02d}",
                page_no=page_no,
                title=title,
                script_path=script_path,
                prompt_path=prompt_path,
                result_path=result_path,
                script_state="bootstrap_draft",
                prompt_state="bootstrap_prompt",
                result_state="not_started",
                updated_at=now,
            )
        )
    return deck_pages


def collect_source_texts(job_dir: Path, status: JobStatus) -> list[SourceText]:
    sources: list[SourceText] = []
    for item in status.uploaded_files:
        path = job_dir / "input" / item.stored_name
        text, extract_status, note = extract_text(path)
        sources.append(
            SourceText(
                filename=item.filename,
                stored_name=item.stored_name,
                size_bytes=item.size_bytes,
                text=clean_text(text),
                status=extract_status,
                note=note,
            )
        )
    return sources


def extract_text(path: Path) -> tuple[str, str, str]:
    suffix = path.suffix.lower()
    if not path.exists():
        return "", "missing", "文件不存在"
    if suffix in {".txt", ".md"}:
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
            for name in candidates[:80]:
                xml = archive.read(name)
                values = iter_xml_text(xml)
                if suffix == ".pptx" and values:
                    slide_no = office_slide_sort_key(name)
                    chunks.append(f"[PPT第{slide_no}页] " + " ".join(values))
                else:
                    chunks.extend(values)
            text = "\n".join(chunks)
    except Exception as exc:  # pragma: no cover - defensive for corrupted office files
        return "", "parse_failed", f"解析失败：{exc}"
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
        return [unescape(text)]
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


def build_source_inventory(sources: list[SourceText]) -> str:
    if not sources:
        return "# 资料清单\n\n- 无上传文件；本次只能依据任务表单信息生成需求草稿。\n"
    rows = ["# 资料清单", "", "| 文件 | 大小 | 抽取状态 | 说明 |", "|---|---:|---|---|"]
    for source in sources:
        rows.append(f"| {source.filename} | {source.size_bytes} bytes | {source.status} | {source.note} |")
    rows.append("")
    rows.append("## 可读资料摘要")
    for source in sources:
        excerpt = "\n".join(meaningful_lines(source.text, limit=6)) if source.text else "无可读文本。"
        rows.extend(["", f"### {source.filename}", "", excerpt])
    return "\n".join(rows).strip() + "\n"


def extract_facts(status: JobStatus, sources: list[SourceText]) -> str:
    lines = ["# 事实摘录", ""]
    lines.append("## 表单事实")
    lines.append(f"- PPT 标题：{status.title}")
    lines.append(f"- 提交人：{status.requester_name}")
    lines.append(f"- 建议页数：{status.pages or '未填写，系统按材料建议'}")
    lines.append(f"- 使用场景：{status.scenario or '未填写'}")
    if status.scenario_prompt:
        lines.append(f"- 使用场景提示词：{status.scenario_prompt}")
    lines.append(f"- 受众对象：{status.audience or '未填写'}")
    if status.audience_prompt:
        lines.append(f"- 受众对象提示词：{status.audience_prompt}")
    if status.user_instruction:
        lines.append(f"- 补充说明：{status.user_instruction}")
    lines.append("")
    lines.append("## 材料事实")
    source_lines = []
    for source in sources:
        for line in meaningful_lines(source.text, limit=12):
            source_lines.append(f"- [{source.filename}] {line}")
    if source_lines:
        lines.extend(source_lines[:48])
    else:
        lines.append("- 未从上传资料中抽取到可用文本事实。")
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

本次已基于任务表单和上传资料生成当前任务的事实摘录、待确认事项、逐页脚本和逐页图片生成提示词。

- 标题：{status.title}
- 可读资料数：{readable_count}
- 上传资料数：{len(sources)}
- 风格：{status.style}

## 事实摘录

{facts.strip()}

## 待确认事项

{open_questions.strip()}
"""


def build_page_scripts(status: JobStatus, sources: list[SourceText], facts_md: str) -> tuple[list[dict[str, object]], str]:
    requested_pages = status.pages or 8
    page_count = max(2, min(int(requested_pages), MAX_BOOTSTRAP_PAGES))
    fact_lines = [line[2:] for line in facts_md.splitlines() if line.startswith("- ")]
    source_basis = fact_lines[:20] or [f"PPT 标题：{status.title}", "未抽取到上传资料事实，需人工补充。"]

    pages: list[dict[str, object]] = []
    for index in range(page_count):
        blueprint = PAGE_BLUEPRINTS[index] if index < len(PAGE_BLUEPRINTS) else (
            derive_topic_title(index + 1, source_basis),
            "deep_dive",
            "围绕上传材料中的一个明确主题展开专题页，不能使用泛化占位标题。",
        )
        title, page_type, purpose = blueprint
        page_no = index + 1
        basis_slice = source_basis[index * 2 : index * 2 + 4] or source_basis[:4]
        script = render_page_script(page_no, title, page_type, purpose, status, basis_slice)
        pages.append({"page_no": page_no, "title": title, "script": script})
    return pages, "local_bootstrap"


def derive_topic_title(page_no: int, source_basis: list[str]) -> str:
    source = source_basis[(page_no - 1) % len(source_basis)] if source_basis else ""
    candidates = [
        "安消一体化场景拆解",
        "风险识别与闭环处置",
        "平台能力与业务落点",
        "数据接入与边界确认",
        "运营机制与责任分工",
        "阶段建设与交付保障",
    ]
    for keyword in ("安消", "消防", "用电", "安全", "告警", "巡检", "公寓", "宿舍", "物联", "平台", "工单", "数据"):
        if keyword in source:
            return f"{keyword}专题能力说明"
    return candidates[(page_no - 1) % len(candidates)]


def build_generation_mode_note(generation_mode: str) -> str:
    return f"""# 生成模式

- 当前逐页脚本生成模式：{generation_mode}
- AI 执行方式：Codex 任务执行
- 是否需要单独配置大模型 key：不需要

说明：

- `local_bootstrap` 表示当前由后端本地规则生成可审阅初稿，作为工作台启动和兜底能力。
- 正式智能生成不让前端用户配置模型 key；由 Codex 在受控任务环境中读取材料、生成脚本、深化提示词并写回任务目录。
- 当前第二步本地 SVG 只作为低保真结构预览；真实图片生成/深度视觉优化必须由 Codex 正式图片生成任务产出 PNG 后写回。
"""


def render_page_script(
    page_no: int,
    title: str,
    page_type: str,
    purpose: str,
    status: JobStatus,
    basis_lines: list[str],
) -> str:
    scenario = status.scenario or "待确认使用场景"
    audience = status.audience or "待确认受众"
    scenario_prompt = status.scenario_prompt or "未填写"
    audience_prompt = status.audience_prompt or "未填写"
    basis = "\n".join(f"- {line}" for line in basis_lines)
    return f"""## P{page_no:02d} {title}

- 核心观点：围绕“{status.title}”，{purpose}
- 页面类型：{page_type}
- 使用场景：{scenario}
- 场景表达口径：{scenario_prompt}
- 受众对象：{audience}
- 受众表达口径：{audience_prompt}

来源依据：

{basis}

图示结构：

- 顶部：页面标题与一句核心结论。
- 中部：用流程图、架构图、矩阵或对比结构表达本页主题。
- 底部：列出本页待确认事项或下一步动作。

页面设计 Brief：

- 页面目标：围绕“{status.title}”完成“{title}”这一页的第一版占位表达，后续必须交给 Codex 结合上传材料深化。
- 主体图示：{suggest_visual_type(page_type)}
- 画面模块：项目目标、关键问题、方案路径、待确认边界。
- 上屏文字：{title}；{purpose}；待客户确认；分阶段推进。
- 视觉布局：顶部放敢为云 Logo 位和页面标题，中部放主体图示，底部放待确认或下一步。
- 待确认表达：客户已有系统、接口状态、点位数量、金额比例和上线时间都必须标注待确认。
- 禁止画面：不得套用智慧后勤案例事实，不得编造客户系统名、金额、比例或已完成状态。

讲稿：

本页需要基于上述来源依据表达当前任务的真实需求，不得把参考案例中的客户事实直接套用到本项目。若材料没有明确说明具体系统、接口、金额、点位或比例，必须标为待确认。

审核备注：需求梳理完成后，由负责人确认本页事实边界，再进入图片PPT渲染。
"""


def suggest_visual_type(page_type: str) -> str:
    if page_type == "cover":
        return "封面视觉，突出项目名称、汇报场景、提交人和日期"
    if page_type == "agenda":
        return "目录列表或三段式章节导航"
    if "architecture" in page_type:
        return "分层架构图"
    if "flow" in page_type:
        return "闭环流程图"
    if "data" in page_type:
        return "数据流向图"
    if "roadmap" in page_type:
        return "阶段路线图"
    if "closing" in page_type:
        return "价值总结卡片组"
    return "问题到方案的结构化卡片图"


def build_image_prompt(status: JobStatus, page_no: int, title: str, script: str) -> str:
    style_prompt = status.custom_style_prompt or status.style_prompt
    return build_page_prompt_from_script(page_no, title, script, style_prompt)
