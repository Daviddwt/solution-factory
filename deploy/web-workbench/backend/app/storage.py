from __future__ import annotations

import json
import hashlib
from html import escape
from io import BytesIO
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import HTTPException, UploadFile

from .case_templates import (
    SMART_LOGISTICS_SCRIPT_MD,
    build_requirement_reminders,
    load_smart_logistics_original_prompts,
    localize_prompt_terms,
)
from .config import JOBS_DIR, PROMPT_TEMPLATE, WORKSPACES_DIR, settings
from .codex_runner import run_codex_in_job
from .hermes_runner import run_hermes_oneshot, send_hermes_message, validate_hermes_target
from .knowledge_base import build_knowledge_base_inventory
from .models import DeckPage, JobCreate, JobStatus, JobSummary, PipelineStatus, UploadedFileInfo, safe_job_path_name, utcish_now
from .presets import default_style_prompt
from .stage1_generator import build_image_prompt, collect_source_texts, extract_facts
from .stage1_generator import build_open_questions, build_requirement_summary, build_source_inventory


BACKEND_DIR = Path(__file__).resolve().parents[1]
IMAGE_DECK_ASSEMBLER = BACKEND_DIR / "scripts" / "assemble_image_deck.mjs"
FORMAL_IMAGE_RENDERER = BACKEND_DIR / "scripts" / "render_formal_images.mjs"
CODEX_HTML_CAPTURE = BACKEND_DIR / "scripts" / "capture_html_slides.mjs"


def list_jobs(workspace_id: str | None = None) -> list[JobSummary]:
    jobs: list[JobSummary] = []
    roots = []
    if workspace_id:
        roots.append(WORKSPACES_DIR / safe_job_path_name(workspace_id) / "jobs")
    else:
        roots.extend(path / "jobs" for path in WORKSPACES_DIR.glob("*") if path.is_dir())
        roots.append(JOBS_DIR)

    status_paths = []
    for root in roots:
        status_paths.extend(root.glob("*/status.json"))

    for status_path in sorted(status_paths, reverse=True):
        status = read_status(status_path.parent.name, workspace_id=status_path.parents[2].name if "workspaces" in status_path.parts else None)
        jobs.append(
            JobSummary(
                job_id=status.job_id,
                workspace_id=status.workspace_id,
                requester_name=status.requester_name,
                status=status.status,
                title=status.title,
                created_at=status.created_at,
                updated_at=status.updated_at,
                output_file=status.output_file,
            )
        )
    return jobs


async def create_job(payload: JobCreate, files: list[UploadFile], source_text: str = "") -> JobStatus:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    payload.requester_name = payload.requester_name.strip()
    if not payload.requester_name:
        raise HTTPException(status_code=400, detail="提交人必填")
    payload.workspace_id = requester_workspace_id(payload.requester_name)
    if not payload.style_prompt:
        payload.style_prompt = default_style_prompt(payload.style)
    if payload.notify_target:
        try:
            payload.notify_target = validate_hermes_target(payload.notify_target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="企微回传目标无效") from exc
    job_dir = get_job_dir(job_id, workspace_id=payload.workspace_id, must_exist=False)
    create_job_dirs(job_dir)
    uploaded_files = await save_uploads(job_dir, files)
    if source_text.strip():
        uploaded_files.append(save_inline_source_text(job_dir, source_text))
    status = JobStatus.new(job_id, payload, uploaded_files)
    write_prompt(job_dir, status)
    write_initial_review_artifacts(job_dir, status)
    write_logs(job_dir, "Job created.\n")
    write_status(job_dir, status)
    return status


def requester_workspace_id(requester_name: str) -> str:
    digest = hashlib.sha1(requester_name.strip().encode("utf-8")).hexdigest()[:10]
    return f"person_{digest}"


def get_job_dir(job_id: str, workspace_id: str | None = None, must_exist: bool = True) -> Path:
    safe_id = safe_job_path_name(job_id)
    if workspace_id:
        job_dir = WORKSPACES_DIR / safe_job_path_name(workspace_id) / "jobs" / safe_id
    else:
        matches = list(WORKSPACES_DIR.glob(f"*/jobs/{safe_id}"))
        if matches:
            job_dir = matches[0]
        else:
            job_dir = JOBS_DIR / safe_id
    if must_exist and not job_dir.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return job_dir


def create_job_dirs(job_dir: Path) -> None:
    for relative in (
        "input",
        "work/01_requirements",
        "work/01_requirements/pages",
        "work/02_image_ppt",
        "work/02_image_ppt/prompts",
        "work/02_image_ppt/results",
        "work/03_editable_rebuild",
        "output",
    ):
        (job_dir / relative).mkdir(parents=True, exist_ok=True)


async def save_uploads(job_dir: Path, files: list[UploadFile]) -> list[UploadedFileInfo]:
    uploaded: list[UploadedFileInfo] = []
    for file in files:
        safe_name = safe_job_path_name(file.filename or "upload.bin")
        suffix = Path(safe_name).suffix.lower()
        if suffix not in settings.allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

        content = await file.read()
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(status_code=400, detail=f"File too large: {safe_name}")

        stored_name = f"{uuid.uuid4().hex[:10]}-{safe_name}"
        destination = job_dir / "input" / stored_name
        destination.write_bytes(content)
        uploaded.append(
            UploadedFileInfo(
                filename=safe_name,
                stored_name=stored_name,
                size_bytes=len(content),
            )
        )
    return uploaded


def save_inline_source_text(job_dir: Path, source_text: str) -> UploadedFileInfo:
    content = source_text.strip()
    stored_name = f"{uuid.uuid4().hex[:10]}-pasted-material.md"
    destination = job_dir / "input" / stored_name
    destination.write_text("# 粘贴文字资料\n\n" + content + "\n", encoding="utf-8")
    return UploadedFileInfo(
        filename="粘贴文字资料.md",
        stored_name=stored_name,
        size_bytes=len(destination.read_bytes()),
    )


def read_status(job_id: str, workspace_id: str | None = None) -> JobStatus:
    job_dir = get_job_dir(job_id, workspace_id=workspace_id)
    status_path = job_dir / "status.json"
    return JobStatus.model_validate_json(status_path.read_text(encoding="utf-8"))


def write_status(job_dir: Path, status: JobStatus) -> None:
    status.updated_at = utcish_now()
    (job_dir / "status.json").write_text(status.model_dump_json(indent=2), encoding="utf-8")


def update_status(job_id: str, status: PipelineStatus, error: str | None = None, output_file: str | None = None) -> JobStatus:
    job_dir = get_job_dir(job_id)
    current = read_status(job_id)
    current.status = status
    current.error = error
    if output_file is not None:
        current.output_file = output_file
    if status in {PipelineStatus.RUNNING, PipelineStatus.REQUIREMENT_INTAKE} and current.started_at is None:
        current.started_at = utcish_now()
    if status not in {PipelineStatus.DONE, PipelineStatus.FAILED, PipelineStatus.NEEDS_HUMAN_REVIEW}:
        current.finished_at = None
    if status in {PipelineStatus.DONE, PipelineStatus.FAILED, PipelineStatus.NEEDS_HUMAN_REVIEW}:
        current.finished_at = utcish_now()
    write_status(job_dir, current)
    return current


def write_prompt(job_dir: Path, status: JobStatus) -> None:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    worker_instructions = template.replace("{job_dir}", ".")
    prompt = f"""# PPT Job Request

## Job Metadata

- Job ID: {status.job_id}
- Workspace: {status.workspace_id}
- Requester: {status.requester_name}
- Job type: ai_ppt_pipeline
- Title: {status.title}
- Pages: {status.pages if status.pages is not None else "待 Codex 根据材料建议"}
- Scenario: {status.scenario or "未填写"}
- Scenario Prompt: {status.scenario_prompt or "未填写"}
- Audience: {status.audience or "未填写"}
- Audience Prompt: {status.audience_prompt or "未填写"}
- Style: {status.style}

## Style Prompt

{status.custom_style_prompt or status.style_prompt or default_style_prompt(status.style)}

## User Instruction

{status.user_instruction or "未填写"}

## Uploaded Files

{json.dumps([item.model_dump(mode="json") for item in status.uploaded_files], ensure_ascii=False, indent=2)}

---

{worker_instructions}
"""
    (job_dir / "prompt.md").write_text(prompt, encoding="utf-8")


def write_initial_review_artifacts(job_dir: Path, status: JobStatus) -> None:
    reminders = build_requirement_reminders(status)
    original_prompts = load_smart_logistics_original_prompts()
    sources = collect_source_texts(job_dir, status)
    source_inventory = build_source_inventory(sources)
    knowledge_inventory = build_knowledge_base_inventory()
    facts = extract_facts(status, sources)
    open_questions = build_open_questions(status, sources)
    requirement_dir = job_dir / "work" / "01_requirements"
    image_ppt_dir = job_dir / "work" / "02_image_ppt"
    (requirement_dir / "requirement-reminders.md").write_text(reminders, encoding="utf-8")
    (requirement_dir / "source-inventory.md").write_text(source_inventory, encoding="utf-8")
    (requirement_dir / "knowledge-base-inventory.md").write_text(knowledge_inventory, encoding="utf-8")
    (requirement_dir / "facts.md").write_text(facts, encoding="utf-8")
    (requirement_dir / "open-questions.md").write_text(open_questions, encoding="utf-8")
    (requirement_dir / "01_requirements.md").write_text(
        build_requirement_summary(status, sources, facts, open_questions),
        encoding="utf-8",
    )
    (requirement_dir / "generation-mode.md").write_text(
        "# 生成模式\n\n- 当前逐页脚本生成模式：empty_initial\n- 说明：新任务默认不生成占位页。请交给 Codex 生成可审阅逐页脚本和图片生产提示词后，再导出脚本包。\n",
        encoding="utf-8",
    )
    (requirement_dir / "reference-smart-logistics-script.md").write_text(SMART_LOGISTICS_SCRIPT_MD, encoding="utf-8")
    (requirement_dir / "reference-smart-logistics-original-prompts.md").write_text(original_prompts, encoding="utf-8")
    (image_ppt_dir / "reference-smart-logistics-script.md").write_text(SMART_LOGISTICS_SCRIPT_MD, encoding="utf-8")
    (image_ppt_dir / "reference-smart-logistics-original-prompts.md").write_text(original_prompts, encoding="utf-8")
    write_page_index(job_dir, [])
    status.stage_artifacts = {
        "requirement_intake": [
            "work/01_requirements/01_requirements.md",
            "work/01_requirements/requirement-reminders.md",
            "work/01_requirements/source-inventory.md",
            "work/01_requirements/knowledge-base-inventory.md",
            "work/01_requirements/facts.md",
            "work/01_requirements/open-questions.md",
            "work/01_requirements/generation-mode.md",
            "work/01_requirements/page-index.json",
            "work/01_requirements/reference-smart-logistics-script.md",
            "work/01_requirements/reference-smart-logistics-original-prompts.md",
        ],
        "ppt_script_reference": [
            "work/01_requirements/reference-smart-logistics-script.md",
            "work/02_image_ppt/reference-smart-logistics-script.md",
        ],
        "original_prompt_reference": [
            "work/01_requirements/reference-smart-logistics-original-prompts.md",
            "work/02_image_ppt/reference-smart-logistics-original-prompts.md",
        ],
        "script_prompts": [
            "work/02_image_ppt/reference-smart-logistics-script.md",
            "work/02_image_ppt/reference-smart-logistics-original-prompts.md",
        ],
    }


def page_index_path(job_dir: Path) -> Path:
    return job_dir / "work" / "01_requirements" / "page-index.json"


def write_page_index(job_dir: Path, pages: list[DeckPage]) -> None:
    page_index_path(job_dir).write_text(
        json.dumps([page.model_dump(mode="json") for page in pages], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_deck_pages(job_id: str) -> list[DeckPage]:
    job_dir = get_job_dir(job_id)
    index_path = page_index_path(job_dir)
    if not index_path.exists():
        write_page_index(job_dir, [])
        return []
    pages = [DeckPage.model_validate(item) for item in json.loads(index_path.read_text(encoding="utf-8"))]
    return pages


def write_combined_ppt_script(job_dir: Path, pages: list[DeckPage]) -> None:
    chunks = ["# 当前任务逐页PPT脚本", ""]
    for page in pages:
        path = job_dir / page.script_path
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace").strip())
            chunks.append("")
    (job_dir / "work" / "01_requirements" / "ppt-script.md").write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")


def generation_provider_label() -> str:
    if settings.worker_mode == "hermes":
        return "Hermes"
    if settings.worker_mode == "mock":
        return "Mock"
    return "Codex"


def generation_mode_name() -> str:
    if settings.worker_mode == "hermes":
        return "hermes_stage1"
    if settings.worker_mode == "mock":
        return "mock"
    return "codex_stage1"


def generate_codex_stage1_artifacts(job_id: str) -> tuple[list[DeckPage], str]:
    job_dir = get_job_dir(job_id)
    status = read_status(job_id)
    update_status(job_id, PipelineStatus.REQUIREMENT_INTAKE)
    (job_dir / "work" / "01_requirements" / "knowledge-base-inventory.md").write_text(
        build_knowledge_base_inventory(),
        encoding="utf-8",
    )

    provider = generation_provider_label()
    mode = generation_mode_name()
    target_count = max(2, min(int(status.pages or 8), MAX_SAFE_PAGES))
    write_initial_review_artifacts(job_dir, status)
    prompt = build_codex_stage1_prompt(status)
    write_logs(job_dir, f"{provider} Stage 1 started.\n", append=True)
    try:
        if settings.worker_mode == "hermes":
            returncode, stdout, stderr, command = run_hermes_stage1(job_dir, status, target_count)
        else:
            returncode, stdout, stderr, command = run_codex_in_job(job_dir, prompt)
    except subprocess.TimeoutExpired as exc:
        update_status(job_id, PipelineStatus.FAILED, error=f"{provider} 生成逐页脚本超时")
        write_logs(job_dir, f"{provider} Stage 1 timeout: {exc}\n", append=True)
        raise HTTPException(status_code=504, detail=f"{provider} 生成逐页脚本超时，请稍后重试。") from exc

    log_command = " ".join(command[:5])
    write_logs(job_dir, f"{provider} Stage 1 command: {log_command} <job_dir>\n", append=True)
    if stdout:
        write_logs(job_dir, stdout, append=True)
    if stderr:
        write_logs(job_dir, stderr, append=True)
    if returncode != 0:
        update_status(job_id, PipelineStatus.FAILED, error=f"{provider} 生成逐页脚本失败")
        raise HTTPException(status_code=500, detail=f"{provider} 生成逐页脚本失败，请查看日志。")

    script_path = job_dir / "work" / "01_requirements" / "ppt-script.md"
    if settings.worker_mode == "hermes":
        script = extract_model_ppt_script(stdout)
        if not script:
            update_status(job_id, PipelineStatus.FAILED, error="Hermes 未返回可解析的 ppt-script.md")
            raise HTTPException(status_code=500, detail="Hermes 没有返回可解析的逐页 PPT 脚本。")
        script_path.write_text(script.rstrip() + "\n", encoding="utf-8")
        write_stage1_generation_notes(job_dir, provider, mode, stdout, stderr)
    elif not script_path.exists():
        update_status(job_id, PipelineStatus.FAILED, error="Codex 未写回 ppt-script.md")
        raise HTTPException(status_code=500, detail="Codex 没有写回逐页 PPT 脚本。")

    script = script_path.read_text(encoding="utf-8", errors="replace")
    page_scripts = parse_codex_ppt_script(script)
    if len(page_scripts) != target_count:
        update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW, error=f"{provider} 返回 {len(page_scripts)} 页，目标 {target_count} 页")
        raise HTTPException(status_code=409, detail=f"{provider} 返回 {len(page_scripts)} 页脚本，和目标 {target_count} 页不一致，请重试或调整页数。")
    quality_errors = validate_codex_page_scripts(page_scripts)
    if quality_errors:
        message = "；".join(quality_errors)
        update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW, error=f"{provider} 脚本质量未通过：{message}")
        raise HTTPException(status_code=409, detail=f"{provider} 脚本质量未通过：{message}。请重试生成或补充资料。")

    pages = write_codex_page_workspace(job_dir, status, page_scripts, provider_label=provider, generation_mode=mode)
    current = read_status(job_id)
    current.status = PipelineStatus.NEEDS_HUMAN_REVIEW
    current.error = None
    artifacts = [
        "work/01_requirements/01_requirements.md",
        "work/01_requirements/source-inventory.md",
        "work/01_requirements/knowledge-base-inventory.md",
        "work/01_requirements/facts.md",
        "work/01_requirements/open-questions.md",
        "work/01_requirements/generation-mode.md",
        "work/01_requirements/codex-generation.md",
        f"work/01_requirements/{mode}-generation.md",
        "work/01_requirements/ppt-script.md",
        "work/01_requirements/page-index.json",
        *[page.script_path for page in pages],
    ]
    current.stage_artifacts["requirement_intake"] = sorted(set(artifacts))
    current.stage_artifacts["script_prompts"] = sorted(
        {
            "work/02_image_ppt/reference-smart-logistics-script.md",
            "work/02_image_ppt/reference-smart-logistics-original-prompts.md",
            *[page.prompt_path for page in pages],
        }
    )
    write_status(job_dir, current)
    write_logs(job_dir, f"{provider} Stage 1 finished with {len(pages)} pages.\n", append=True)
    notify_job_ready(job_dir, current, pages)
    return pages, script


MAX_SAFE_PAGES = 80
HERMES_BATCH_SIZE = 2
HERMES_BATCH_MAX_ATTEMPTS = 2


def read_job_text(job_dir: Path, relative_path: str, limit: int) -> str:
    path = job_dir / relative_path
    if not path.exists() or not path.is_file():
        return f"{relative_path} 未找到。"
    return trim_for_codex_prompt(path.read_text(encoding="utf-8", errors="replace"), limit)


def run_hermes_stage1(job_dir: Path, status: JobStatus, page_count: int) -> tuple[int, str, str, list[str]]:
    if page_count <= HERMES_BATCH_SIZE + 3:
        prompt = build_hermes_stage1_prompt(job_dir, status, 1, page_count, page_count)
        return run_hermes_oneshot(job_dir, prompt)

    combined_pages: list[str] = []
    stderr_parts: list[str] = []
    commands: list[str] = []
    for start in range(1, page_count + 1, HERMES_BATCH_SIZE):
        end = min(page_count, start + HERMES_BATCH_SIZE - 1)
        last_stdout = ""
        last_command: list[str] = []
        for attempt in range(1, HERMES_BATCH_MAX_ATTEMPTS + 1):
            prompt = build_hermes_stage1_prompt(job_dir, status, start, end, page_count)
            if attempt > 1:
                prompt += build_hermes_batch_retry_note(start, end)
            returncode, stdout, stderr, command = run_hermes_oneshot(job_dir, prompt)
            last_stdout = stdout
            last_command = command
            commands.append(" ".join(command))
            attempt_label = f"P{start:02d}-P{end:02d} attempt {attempt}"
            if stderr:
                stderr_parts.append(f"[{attempt_label} stderr]\n{stderr.strip()}")
            write_logs(job_dir, f"Hermes Stage 1 batch {attempt_label} returned {returncode}.\n", append=True)
            if returncode != 0:
                return returncode, "\n\n".join(combined_pages + [stdout]), "\n\n".join(stderr_parts), command

            batch_script = extract_model_ppt_script(stdout, required_first_page=start)
            if not batch_script:
                message = f"[P{start:02d}-P{end:02d}] Hermes 未返回可解析页段。"
                if attempt < HERMES_BATCH_MAX_ATTEMPTS:
                    write_logs(job_dir, message + " 准备重试当前页段。\n", append=True)
                    continue
                stderr_parts.append(message)
                return 2, "\n\n".join(combined_pages + [stdout]), "\n\n".join(stderr_parts), command

            batch_pages = parse_codex_ppt_script(batch_script)
            expected_numbers = list(range(start, end + 1))
            actual_numbers = [int(page["page_no"]) for page in batch_pages]
            if actual_numbers != expected_numbers:
                message = f"[P{start:02d}-P{end:02d}] 页码不匹配，期望 {expected_numbers}，实际 {actual_numbers}。"
                if attempt < HERMES_BATCH_MAX_ATTEMPTS:
                    write_logs(job_dir, message + " 准备重试当前页段。\n", append=True)
                    continue
                stderr_parts.append(message)
                return 2, "\n\n".join(combined_pages + [batch_script]), "\n\n".join(stderr_parts), command

            break
        else:
            return 2, "\n\n".join(combined_pages + [last_stdout]), "\n\n".join(stderr_parts), last_command

        combined_pages.extend(str(page["script"]) for page in batch_pages)

    script = "# 当前任务逐页PPT脚本\n\n" + "\n\n".join(combined_pages).strip() + "\n"
    stderr_parts.append("[Hermes batched commands]\n" + "\n".join(commands))
    return 0, script, "\n\n".join(stderr_parts), [settings.hermes_bin, "-z", "<batched prompts>"]


def build_hermes_batch_retry_note(start_page: int, end_page: int) -> str:
    return f"""

## 重试修正要求

上一次模型输出没有通过后端校验。现在只重写当前页段：

- 必须从 `## P{start_page:02d}` 开始。
- 必须连续输出到 `## P{end_page:02d}`。
- 不得输出其他页码，不得复述上一页段内容。
- 不得在页段前后追加“已生成完毕”“如需落盘”“输出文件路径”等解释性文字。
- 如果没有足够客户材料，也要在对应页内写“待客户确认/待补充”，不能换成其他页码。
"""


def build_hermes_stage1_prompt(job_dir: Path, status: JobStatus, start_page: int, end_page: int, page_count: int) -> str:
    range_label = f"P{start_page:02d}-P{end_page:02d}"
    page_rule = (
        "P01 必须是封面页，P02 必须是目录页。"
        if start_page == 1
        else "当前页段不是封面或目录，不要输出 P01/P02，也不要补写总目录。"
    )
    return f"""你是解决方案部 PPT 脚本生产台的 Hermes 模型执行者。

你现在只负责生成可审阅的逐页 PPT 生产脚本。不要生成图片、不要生成 PPTX、不要声称图片生成或可编辑 PPT 已接入。

请根据下面给出的任务上下文，直接输出当前页段的 Markdown 内容。不要输出解释、不要使用代码块围栏、不要输出 JSON。

总页数是 {page_count} 页。当前只生成 {range_label}，必须包含 {end_page - start_page + 1} 页，不能少页，不能多页。{page_rule}

## 任务信息

- 任务标题：{status.title}
- 提交人：{status.requester_name}
- 使用场景：{status.scenario or "未填写"}
- 场景提示词：{status.scenario_prompt or "未填写"}
- 受众对象：{status.audience or "未填写"}
- 受众提示词：{status.audience_prompt or "未填写"}
- 风格：{status.style}
- 用户补充说明：{status.user_instruction or "未填写"}
- 关键要求：如果上传资料中说明 Word 是主依据、PPT 只是素材参考，必须以 Word 为主；引用 PPT 素材时尽量标注 PPT 第几页。无法确认页码时写“PPT素材页码待人工确认”，不要编造页码。

## 来源清单

{read_job_text(job_dir, "work/01_requirements/source-inventory.md", 14000)}

## 公司知识库清单

{read_job_text(job_dir, "work/01_requirements/knowledge-base-inventory.md", 9000)}

## 已抽取事实

{read_job_text(job_dir, "work/01_requirements/facts.md", 18000)}

## 待确认问题

{read_job_text(job_dir, "work/01_requirements/open-questions.md", 8000)}

## 智慧后勤脚本结构参考

{read_job_text(job_dir, "work/01_requirements/reference-smart-logistics-script.md", 7000)}

## 输出硬性要求

- 所有用户可见内容必须是中文。
- 不要编造客户名称、设备数量、金额、比例、接口状态、上线时间、品牌型号或已完成状态。
- 材料没有明确依据的内容写成“待确认”或“待补充”，不要写成确定事实。
- 严禁使用“专题深化 9”“补充页”“未命名页面”“待定页面”等占位标题。
- 每页必须有明确的事实来源、页面结论、图示结构和进入图片 PPT 前的审阅边界。
- 每页必须包含“来源依据”“图示结构”“Page-specific source of truth”“页面设计 Brief”“讲稿”“审核备注”。
- “Page-specific source of truth”必须细到能指导后续图片生产：页面目标、版式要求、图示结构、模块节点、必须出现的关键词、上屏文字、讲稿要点、视觉注意、事实与能力边界和禁止事项都要写清楚。
- 页与页之间必须有清晰分工，不能用同一段场景提示词或受众提示词重复填充多页。
- “来源依据”必须优先引用上传文件或粘贴资料中的事实；不能只把“场景提示词/受众提示词/风格提示词”当成来源依据。
- 公司知识库只作为能力口径和表达方式依据；客户现场情况、数量、点位、金额、接口状态、上线计划必须来自上传材料或标注待确认。
- 本页段只输出 {range_label}，页码必须从 P{start_page:02d} 连续到 P{end_page:02d}。不要输出其他页。

## 严格输出格式

# 当前任务逐页PPT脚本

## P{start_page:02d} 页面标题

- 核心观点：一句话说明本页要让受众形成什么判断。
- 页面类型：cover / agenda / background / requirement_analysis / architecture / business_flow / data_flow / ai_capability / implementation_roadmap / value_summary / deep_dive 等中文可读类型。
- 使用场景：{status.scenario or "待确认"}
- 场景表达口径：结合场景说明这页应该怎么讲。
- 受众对象：{status.audience or "待确认"}
- 受众表达口径：结合受众说明讲价值、讲业务还是讲技术。

来源依据：

- 区分“客户材料事实”和“公司知识库口径”；没有客户材料依据就写“待补充/待客户确认”。

图示结构：

- 说明本页适合使用的图示结构，必须可被图片 PPT 阶段直接理解。

Page-specific source of truth：

- 页面目标：明确这一页要让客户形成的判断，不得写泛泛目标。
- 版式要求：明确使用几栏、矩阵、分层、泳道、时间轴、中心辐射、看板、封面或目录等版式；说明标题区、主体区、侧栏和底部提示如何组织。
- 图示结构：逐项列出主体图中的节点、层级、流程步骤、表格列名或卡片内容；必须能直接指导图片生成。
- 必须出现的关键词：列出 5 到 10 个必须上屏或作为图示标签出现的中文关键词。
- 上屏文字：列出建议放在画面上的短句，控制在可读范围内。
- 讲稿要点：用 2 到 4 条说明这页怎么讲，避免图片只剩空泛模块。
- 视觉注意：说明强调色、风险/待确认标注、图标、线条、表格或卡片的使用要求。
- 事实与能力边界：列出哪些是材料已有事实，哪些必须标注“待客户确认/待补充/待对接”。
- 禁止事项：列出本页不得出现的编造数字、客户系统名、已完成状态、外部案例事实或不适合客户领导的技术细节。

页面设计 Brief：

- 用 5 到 8 条中文摘要复述上面的当前页设计真值，方便人工快速审核；不能替代 Page-specific source of truth。

讲稿：

用 1 到 3 段中文说明本页讲述逻辑。不要写空话，不要堆术语。

审核备注：列出本页进入图片 PPT 前必须确认的边界。
"""


def extract_model_ppt_script(stdout: str, *, required_first_page: int = 1) -> str:
    text = stdout.strip()
    fenced = re.search(r"```(?:markdown|md)?\s*(# 当前任务逐页PPT脚本.*?)(?:\n```|$)", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("# 当前任务逐页PPT脚本")
    if start >= 0:
        text = text[start:].strip()
    elif match := re.search(r"^##\s*P\d{2}\s+", text, flags=re.MULTILINE):
        text = text[match.start() :].strip()
    if f"## P{required_first_page:02d}" not in text:
        return ""
    return text


def write_stage1_generation_notes(job_dir: Path, provider: str, mode: str, stdout: str, stderr: str) -> None:
    requirement_dir = job_dir / "work" / "01_requirements"
    note = f"""# {provider} 逐页脚本生成记录

- provider: {provider}
- generation_mode: {mode}
- 说明：本次由后端调用 {provider} 非交互模型入口生成 `ppt-script.md`，再由后端解析、校验并写入逐页脚本和图片生产提示词。
- 能力边界：当前只生成脚本和提示词，不生成图片 PPT，不生成 PPTX，不生成可编辑 PPT。
- stderr: {trim_for_codex_prompt(stderr.strip() or "无", 2000)}
"""
    (requirement_dir / "codex-generation.md").write_text(note, encoding="utf-8")
    (requirement_dir / f"{mode}-generation.md").write_text(note, encoding="utf-8")
    (requirement_dir / "generation-mode.md").write_text(
        f"# 生成模式\n\n- 当前逐页脚本生成模式：{mode}\n- provider：{provider}\n- 说明：脚本由 {provider} 生成，后端负责解析、校验、拆分和导出。\n",
        encoding="utf-8",
    )


def notify_job_ready(job_dir: Path, status: JobStatus, pages: list[DeckPage]) -> None:
    if not status.notify_target:
        return
    script_path = job_dir / "work" / "01_requirements" / "ppt-script.md"
    script_preview = ""
    if script_path.exists():
        script_preview = build_script_preview(script_path.read_text(encoding="utf-8", errors="replace"))
    job_url = f"{settings.public_base_url}/jobs/{status.job_id}"
    download_url = f"{settings.public_base_url}/api/jobs/{status.job_id}/download?filename=script-package.zip"
    message = f"""PPT 脚本已生成，等待审阅

任务：{status.title}
提交人：{status.requester_name}
页数：{len(pages)}
状态：待人工审阅

审阅入口：
{job_url}

脚本包下载：
{download_url}

脚本摘要：
{script_preview or "已生成逐页脚本和图片生产提示词，请打开审阅入口查看。"}

边界：当前只生成 PPT 生产脚本和逐页图片生产提示词，不生成图片 PPT、不生成 PPTX、不生成可编辑 PPT。
"""
    try:
        returncode, stdout, stderr, command = send_hermes_message(status.notify_target, message)
    except Exception as exc:
        status.notify_error = str(exc)[:600]
        write_status(job_dir, status)
        write_logs(job_dir, f"Hermes notify exception: {exc}\n", append=True)
        return
    write_logs(job_dir, f"Hermes notify command: {' '.join(command)}\n", append=True)
    if stdout:
        write_logs(job_dir, stdout, append=True)
    if stderr:
        write_logs(job_dir, stderr, append=True)
    if returncode == 0:
        status.notify_sent_at = utcish_now()
        status.notify_error = None
    else:
        status.notify_error = (stderr or stdout or "Hermes send failed").strip()[:600]
    write_status(job_dir, status)


def build_script_preview(script: str) -> str:
    lines: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## P") or stripped.startswith("- 核心观点"):
            lines.append(stripped)
        if len(lines) >= 8:
            break
    preview = "\n".join(lines)
    return trim_for_codex_prompt(preview, 1800)


def build_codex_stage1_prompt(status: JobStatus) -> str:
    page_count = max(2, min(int(status.pages or 8), MAX_SAFE_PAGES))
    return f"""你是解决方案部 PPT 脚本生产台的 Codex 执行者。请只在当前任务目录内读写文件。

目标：根据 `prompt.md`、`input/` 上传材料、已有 `work/01_requirements/source-inventory.md`、`knowledge-base-inventory.md`、`facts.md`、`open-questions.md`，生成可审阅的逐页 PPT 生产脚本和逐页图片生产提示词。

当前产品只生成脚本和提示词，不生成图片 PPT，不生成 PPTX，不生成可编辑 PPT。

必须先读取并参考：
- `work/01_requirements/knowledge-base-inventory.md`：公司知识库基线。它可用于公司能力、标准口径、禁用表述和通用架构，但不能替代客户材料事实。
- `work/01_requirements/reference-smart-logistics-original-prompts.md`：这是“智慧后勤”项目的原始复杂图片 PPT 提示词样例，重点学习它的逐页颗粒度、Page-specific source of truth、页面目标、版式要求、图示结构、关键词、讲稿和视觉注意。
- `work/01_requirements/reference-smart-logistics-script.md`：这是逐页脚本样例，只能参考结构和审核口径，不得套用客户事实。

硬性要求：
- 必须生成 {page_count} 页，不能少页，不能多页；用户填写的页数就是总页数，封面和目录包含在总页数内。
- P01 必须是封面页，标题为项目/方案名称，不做普通内容页。
- P02 必须是目录页，列出后续正文页的章节结构；如果总页数只有 2 页，P02 写成“目录与汇报范围”。
- P03 及以后才进入正文内容。
- 所有用户可见内容必须是中文。
- 不要编造客户名称、设备数量、金额、比例、接口状态、上线时间、品牌型号或已完成状态。
- 材料没有明确依据的内容写成“待确认”或“待补充”，不要写成确定事实。
- 严禁使用“专题深化 9”“补充页”“未命名页面”“待定页面”等占位标题；每页标题必须能看出业务主题。
- 每页必须有明确的事实来源、页面结论、图示结构和进入图片 PPT 前的审阅边界。
- 每页必须包含“Page-specific source of truth”和“页面设计 Brief”。其中“Page-specific source of truth”是图片生成模型真正执行的当前页设计说明书，颗粒度必须对齐智慧后勤原始提示词：页面目标、版式要求、图示结构、模块节点、必须出现的关键词、上屏文字、讲稿要点、视觉注意、能力/事实边界和禁止事项都要写清楚。
- 如果材料不足以支撑某页，要把页面改成“待确认事项/资料补充清单/实施边界”类页面，而不是泛化编造。
- 页与页之间必须有清晰分工，不能用同一段场景提示词或受众提示词重复填充多页。
- “来源依据”必须优先引用上传文件或粘贴资料中的事实；不能只把“场景提示词/受众提示词/风格提示词”当成来源依据。
- “公司知识库”可以作为能力口径和表达方式依据，但客户现场情况、客户已有系统、数量、点位、金额、接口状态、上线计划等必须来自上传材料或标注待确认。
- 使用场景：{status.scenario or "未填写"}。
- 场景提示词：{status.scenario_prompt or "未填写"}。
- 受众对象：{status.audience or "未填写"}。
- 受众提示词：{status.audience_prompt or "未填写"}。
- 风格：{status.style}。

请写回这些文件：
1. `work/01_requirements/01_requirements.md`
2. `work/01_requirements/facts.md`
3. `work/01_requirements/open-questions.md`
4. `work/01_requirements/generation-mode.md`
5. `work/01_requirements/codex-generation.md`
6. `work/01_requirements/ppt-script.md`

不要创建 `codex_specs/`、`codex_tasks/`、`codex_reviews/` 或其他与本任务产物无关的目录；本次只写上述指定文件。

`ppt-script.md` 必须严格使用下面格式，每页一个二级标题，页码连续：

# 当前任务逐页PPT脚本

## P01 页面标题

- 核心观点：一句话说明本页要让受众形成什么判断。
- 页面类型：cover / agenda / background / requirement_analysis / architecture / business_flow / data_flow / ai_capability / implementation_roadmap / value_summary / deep_dive 等中文可读类型。
- 使用场景：{status.scenario or "待确认"}
- 场景表达口径：结合场景说明这页应该怎么讲。
- 受众对象：{status.audience or "待确认"}
- 受众表达口径：结合受众说明讲价值、讲业务还是讲技术。

来源依据：

- 区分“客户材料事实”和“公司知识库口径”；没有客户材料依据就写“待补充/待客户确认”。

图示结构：

- 说明本页适合使用的图示结构，必须可被图片 PPT 阶段直接理解。

Page-specific source of truth：

- 页面目标：明确这一页要让客户形成的判断，不得写泛泛目标。
- 版式要求：明确使用几栏、矩阵、分层、泳道、时间轴、中心辐射、看板、封面或目录等版式；说明标题区、主体区、侧栏和底部提示如何组织。
- 图示结构：逐项列出主体图中的节点、层级、流程步骤、表格列名或卡片内容；必须能直接指导图片生成。
- 必须出现的关键词：列出 5 到 10 个必须上屏或作为图示标签出现的中文关键词。
- 上屏文字：列出建议放在画面上的短句，控制在可读范围内。
- 讲稿要点：用 2 到 4 条说明这页怎么讲，避免图片只剩空泛模块。
- 视觉注意：说明强调色、风险/待确认标注、图标、线条、表格或卡片的使用要求。
- 事实与能力边界：列出哪些是材料已有事实，哪些必须标注“待客户确认/待补充/待对接”。
- 禁止事项：列出本页不得出现的编造数字、客户系统名、已完成状态、外部案例事实或不适合客户领导的技术细节。

页面设计 Brief：

- 用 5 到 8 条中文摘要复述上面的当前页设计真值，方便人工快速审核；不能替代 Page-specific source of truth。

讲稿：

用 1 到 3 段中文说明本页讲述逻辑。不要写空话，不要堆术语。

审核备注：列出本页进入图片 PPT 前必须确认的边界。

质量自检要求：
- 在 `codex-generation.md` 中写明本次是否通过脚本质量自检。
- 自检至少覆盖：页数是否准确、P01 是否封面、P02 是否目录、是否存在占位页名、是否存在多页重复表达、每页是否有来源依据、是否有待确认边界。
- 自检必须覆盖：每页是否包含足够详细的 Page-specific source of truth；如果某页只写“痛点矩阵/流程图/架构图”而没有节点、关键词、版式和视觉注意，视为未通过。
- 如果存在无法避免的资料不足，必须在 `open-questions.md` 和对应页面审核备注中说明。

最后，请在 `generation-mode.md` 写明：当前逐页脚本生成模式为 `codex_stage1`。
"""


def parse_codex_ppt_script(script: str) -> list[dict[str, object]]:
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


def validate_codex_page_scripts(page_scripts: list[dict[str, object]]) -> list[str]:
    errors: list[str] = []
    if len(page_scripts) >= 1:
        first = str(page_scripts[0]["title"])
        first_script = str(page_scripts[0]["script"])
        if "封面" not in first and "页面类型：cover" not in first_script and "页面类型：封面" not in first_script:
            errors.append("P01 必须是封面页")
    if len(page_scripts) >= 2:
        second = str(page_scripts[1]["title"])
        second_script = str(page_scripts[1]["script"])
        if "目录" not in second and "页面类型：agenda" not in second_script and "页面类型：目录" not in second_script:
            errors.append("P02 必须是目录页")

    titles = [str(page["title"]).strip() for page in page_scripts]
    duplicate_titles = sorted({title for title in titles if titles.count(title) > 1})
    if duplicate_titles:
        errors.append("存在重复页面标题：" + "、".join(duplicate_titles[:3]))

    placeholder_pattern = re.compile(r"(专题深化\s*\d+|补充页|未命名|待定页面|页面标题)")
    placeholder_titles = [f"P{int(page['page_no']):02d}" for page in page_scripts if placeholder_pattern.search(str(page["title"]))]
    if placeholder_titles:
        errors.append("存在占位标题：" + "、".join(placeholder_titles[:5]))

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

    weak_truth_pages = []
    required_truth_labels = ("页面目标", "版式要求", "图示结构", "必须出现的关键词", "上屏文字", "视觉注意", "事实与能力边界", "禁止事项")
    for page in page_scripts:
        script = str(page["script"])
        truth_body = extract_script_section(script, "Page-specific source of truth", ("页面设计 Brief", "讲稿", "审核备注"))
        missing_labels = [label for label in required_truth_labels if label not in truth_body]
        truth_lines = [line for line in truth_body.splitlines() if line.strip().startswith("-")]
        if len(truth_body) < 320 or len(truth_lines) < 8 or missing_labels:
            weak_truth_pages.append(f"P{int(page['page_no']):02d}")
    if weak_truth_pages:
        errors.append("Page-specific source of truth 颗粒度不足：" + "、".join(weak_truth_pages[:5]))

    generic_phrase = "本页需要基于上述来源依据表达当前任务的真实需求"
    generic_pages = [f"P{int(page['page_no']):02d}" for page in page_scripts if generic_phrase in str(page["script"])]
    if generic_pages:
        errors.append("存在本地占位稿通用讲稿：" + "、".join(generic_pages[:5]))

    weak_source_pages = []
    for page in page_scripts:
        script = str(page["script"])
        source_match = re.search(r"来源依据：(?P<body>.*?)(?:\n\n图示结构：|\n\n页面设计 Brief：)", script, flags=re.DOTALL)
        source_body = source_match.group("body") if source_match else ""
        if source_body and all(token in source_body for token in ("使用场景", "场景提示词")):
            weak_source_pages.append(f"P{int(page['page_no']):02d}")
    if weak_source_pages:
        errors.append("来源依据过度依赖场景/受众提示词：" + "、".join(weak_source_pages[:5]))
    return errors


def extract_script_section(script: str, heading: str, stop_headings: tuple[str, ...]) -> str:
    start_pattern = re.escape(heading) + r"\s*[：:]"
    start = re.search(start_pattern, script)
    if not start:
        return ""
    tail = script[start.end() :]
    stop_positions = []
    for stop_heading in stop_headings:
        stop = re.search(r"\n\s*" + re.escape(stop_heading) + r"\s*[：:]", tail)
        if stop:
            stop_positions.append(stop.start())
    if stop_positions:
        tail = tail[: min(stop_positions)]
    return tail.strip()


def write_codex_page_workspace(
    job_dir: Path,
    status: JobStatus,
    page_scripts: list[dict[str, object]],
    *,
    provider_label: str = "Codex",
    generation_mode: str = "codex_stage1",
) -> list[DeckPage]:
    pages_dir = job_dir / "work" / "01_requirements" / "pages"
    prompts_dir = job_dir / "work" / "02_image_ppt" / "prompts"
    results_dir = job_dir / "work" / "02_image_ppt" / "results"
    pages_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    valid_numbers = {int(item["page_no"]) for item in page_scripts}
    remove_stale_page_files(job_dir, valid_numbers)
    clear_stage2_generated_outputs(job_dir)

    pages: list[DeckPage] = []
    now = utcish_now()
    for item in page_scripts:
        page_no = int(item["page_no"])
        title = str(item["title"])
        script = str(item["script"]).strip()
        script_path = f"work/01_requirements/pages/page-{page_no:02d}.md"
        prompt_path = f"work/02_image_ppt/prompts/slide-{page_no:02d}.md"
        result_path = f"work/02_image_ppt/results/page-{page_no:02d}.md"
        (job_dir / script_path).write_text(script + "\n", encoding="utf-8")
        (job_dir / prompt_path).write_text(build_image_prompt(status, page_no, title, script), encoding="utf-8")
        (job_dir / result_path).write_text(
            f"# P{page_no:02d} 脚本产物\n\n本页已由 {provider_label} 完成页面脚本和图片生产提示词。第一版不生成图片，请审阅脚本后导出脚本包。\n",
            encoding="utf-8",
        )
        pages.append(
            DeckPage(
                page_id=f"p{page_no:02d}",
                page_no=page_no,
                title=title,
                script_path=script_path,
                prompt_path=prompt_path,
                result_path=result_path,
                script_state="hermes_draft" if generation_mode == "hermes_stage1" else "codex_draft",
                prompt_state="ready",
                result_state="not_started",
                updated_at=now,
            )
        )

    write_page_index(job_dir, pages)
    write_combined_ppt_script(job_dir, pages)
    return pages


def remove_stale_page_files(job_dir: Path, valid_numbers: set[int]) -> None:
    patterns = [
        "work/01_requirements/pages/page-*.md",
        "work/02_image_ppt/prompts/slide-*.md",
        "work/02_image_ppt/results/page-*.md",
        "work/02_image_ppt/results/slide-*.svg",
        "work/02_image_ppt/assets/slide-*.png",
    ]
    for pattern in patterns:
        for path in job_dir.glob(pattern):
            match = re.search(r"(?:page|slide)-(\d{2})\.", path.name)
            if not match:
                continue
            page_no = int(match.group(1))
            if page_no not in valid_numbers:
                path.unlink(missing_ok=True)


def clear_stage2_generated_outputs(job_dir: Path) -> None:
    """A new Stage 1 script invalidates all downstream visual outputs."""
    patterns = [
        "work/02_image_ppt/results/slide-*.svg",
        "work/02_image_ppt/assets/slide-*.png",
        "work/02_image_ppt/output/image-draft.pptx",
        "work/02_image_ppt/qa/contact-sheet.png",
        "work/02_image_ppt/manifest.json",
        "work/02_image_ppt/formal-image-manifest.json",
        "work/02_image_ppt/source-prompts.md",
        "output/image-draft.pptx",
        "output/image-ppt-package.zip",
    ]
    for pattern in patterns:
        for path in job_dir.glob(pattern):
            path.unlink(missing_ok=True)


def find_deck_page(job_id: str, page_id: str) -> tuple[Path, list[DeckPage], DeckPage]:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    safe_page_id = safe_job_path_name(page_id)
    for page in pages:
        if page.page_id == safe_page_id:
            return job_dir, pages, page
    raise HTTPException(status_code=404, detail="Page not found")


def read_deck_page_content(job_id: str, page_id: str, kind: str) -> str:
    job_dir, _, page = find_deck_page(job_id, page_id)
    if kind == "script":
        path = page.script_path
    elif kind == "prompt":
        path = page.prompt_path
    elif kind == "result":
        path = page.result_path
    else:
        raise HTTPException(status_code=400, detail="Invalid page content kind")
    return safe_artifact_file(job_id, path).read_text(encoding="utf-8", errors="replace")


def deck_page_image_path(page: DeckPage) -> str:
    return f"work/02_image_ppt/results/slide-{page.page_no:02d}.svg"


def formal_deck_page_image_path(page: DeckPage) -> str:
    return f"work/02_image_ppt/assets/slide-{page.page_no:02d}.png"


def formal_image_manifest_path() -> str:
    return "work/02_image_ppt/formal-image-manifest.json"


def read_formal_image_manifest(job_dir: Path) -> dict:
    manifest_path = job_dir / formal_image_manifest_path()
    if not manifest_path.exists():
        raise HTTPException(
            status_code=409,
            detail="当前只有低保真结构预览，正式图片尚未生成，不能打包图片版 PPTX。请先完成正式图片生成后再打包。",
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=409, detail="正式图片生成清单损坏，请重新生成正式图片。") from exc
    generation_mode = str(manifest.get("generation_mode") or "")
    if generation_mode not in {
        "built_in_imagegen",
        "codex_built_in_imagegen",
        "codex_builtin_image_generation",
        "codex_builtin_image_generation_imported",
        "codex_formal_png_renderer",
        "codex_visual_html_render",
    }:
        raise HTTPException(status_code=409, detail="正式图片生成清单来源不正确，不能打包图片版 PPTX。")
    return manifest


async def import_codex_stage2_image_assets(job_id: str, files: list[UploadFile]) -> tuple[list[DeckPage], int, str]:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能导入图片版 PPT")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        raise HTTPException(status_code=409, detail=f"{names} 提示词待重生成，不能导入正式图片")

    extracted: dict[int, bytes] = {}
    for upload in files:
        raw_name = safe_job_path_name(upload.filename or "upload.bin")
        content = await upload.read()
        suffix = Path(raw_name).suffix.lower()
        if suffix == ".zip":
            try:
                with ZipFile(BytesIO(content)) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        member_name = Path(member.filename).name
                        if Path(member_name).suffix.lower() != ".png":
                            continue
                        page_no = parse_slide_asset_number(member_name)
                        if page_no is not None:
                            extracted[page_no] = archive.read(member)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="ZIP 文件无法读取，请确认里面包含 slide-01.png 这类图片。") from exc
        elif suffix == ".png":
            page_no = parse_slide_asset_number(raw_name)
            if page_no is not None:
                extracted[page_no] = content
        else:
            raise HTTPException(status_code=400, detail="正式图片导入只支持 PNG 或包含 PNG 的 ZIP。")

    expected = {page.page_no for page in pages}
    missing = sorted(expected - set(extracted))
    extra = sorted(set(extracted) - expected)
    if missing:
        names = "、".join(f"P{no:02d}" for no in missing[:8])
        more = "等" if len(missing) > 8 else ""
        raise HTTPException(status_code=409, detail=f"缺少 {names}{more} 的正式图片。请一次导入完整 slide-01.png 到 slide-{len(pages):02d}.png。")
    if extra:
        names = "、".join(f"P{no:02d}" for no in extra[:8])
        raise HTTPException(status_code=409, detail=f"导入包里包含当前任务没有的页码：{names}。")

    image_dir = job_dir / "work" / "02_image_ppt"
    assets_dir = image_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    now = utcish_now()
    manifest_slides = []
    for page in pages:
        content = extracted[page.page_no]
        if not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail=f"P{page.page_no:02d} 不是有效 PNG 文件。")
        asset_relative = formal_deck_page_image_path(page)
        (job_dir / asset_relative).write_bytes(content)
        page.result_state = "generated"
        page.updated_at = now
        (job_dir / page.result_path).write_text(
            build_formal_image_result_note(page, asset_relative, "codex_builtin_image_generation_imported"),
            encoding="utf-8",
        )
        manifest_slides.append(
            {
                "slide_no": page.page_no,
                "page_id": f"P{page.page_no:02d}",
                "title": page.title,
                "image_path": f"assets/slide-{page.page_no:02d}.png",
                "generation_mode": "codex_builtin_image_generation_imported",
            }
        )

    manifest = {
        "stage": "image_ppt_generation",
        "generation_mode": "codex_builtin_image_generation_imported",
        "slide_count": len(pages),
        "slides": manifest_slides,
        "generated_at": now,
        "imported_at": now,
        "note": "这些图片由 Codex 正式图片流程生成后导入；不是本地 deterministic renderer 产物。",
    }
    (image_dir / "formal-image-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_page_index(job_dir, pages)

    current_status = read_status(job_id)
    artifacts = [
        formal_image_manifest_path(),
        *[formal_deck_page_image_path(page) for page in pages],
    ]
    current_status.stage_artifacts["image_ppt_generation"] = sorted(
        set(current_status.stage_artifacts.get("image_ppt_generation", []) + artifacts)
    )
    current_status.output_file = None
    write_status(job_dir, current_status)
    update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW)
    write_logs(job_dir, f"Imported Codex Stage 2 formal images: {len(pages)} pages.\n", append=True)
    return read_deck_pages(job_id), len(pages), "正式图片已导入，可继续打包图片版 PPTX 和交接包。"


def parse_slide_asset_number(filename: str) -> int | None:
    stem = Path(filename).stem.lower()
    patterns = (
        r"(?:slide|page|p)[-_ ]*0*(\d{1,3})$",
        r"^0*(\d{1,3})$",
    )
    for pattern in patterns:
        match = re.search(pattern, stem)
        if match:
            return int(match.group(1))
    return None


def read_deck_page_image(job_id: str, page_id: str) -> Path:
    job_dir, _, page = find_deck_page(job_id, page_id)
    formal_image = job_dir / formal_deck_page_image_path(page)
    if page.result_state == "generated" and formal_image.exists():
        return safe_artifact_file(job_id, formal_deck_page_image_path(page))
    image = job_dir / deck_page_image_path(page)
    if not image.exists():
        raise HTTPException(status_code=404, detail="Structure preview not found")
    return safe_artifact_file(job_id, deck_page_image_path(page))


def render_formal_deck_images(job_id: str) -> tuple[list[DeckPage], int, str]:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能生成正式图片")

    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        raise HTTPException(status_code=409, detail=f"{names} 提示词待重生成，不能生成正式图片")

    if not FORMAL_IMAGE_RENDERER.exists():
        raise HTTPException(status_code=500, detail="正式图片渲染脚本不存在")

    image_dir = job_dir / "work" / "02_image_ppt"
    (image_dir / "assets").mkdir(parents=True, exist_ok=True)
    write_logs(job_dir, f"Formal image generation started for {len(pages)} pages.\n", append=True)
    update_status(job_id, PipelineStatus.IMAGE_PPT_GENERATION)
    result = subprocess.run(
        ["node", str(FORMAL_IMAGE_RENDERER), "--job-dir", str(job_dir)],
        capture_output=True,
        text=True,
        timeout=360,
        check=False,
    )
    if result.stdout:
        write_logs(job_dir, result.stdout, append=True)
    if result.stderr:
        write_logs(job_dir, result.stderr, append=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "正式图片生成失败").strip()
        update_status(job_id, PipelineStatus.FAILED, error=detail[-500:])
        raise HTTPException(status_code=500, detail=detail[-800:])

    manifest = read_formal_image_manifest(job_dir)
    generated_count = int(manifest.get("slide_count") or 0)
    if generated_count != len(pages):
        raise HTTPException(status_code=500, detail="正式图片生成数量与当前页面数不一致")

    now = utcish_now()
    for page in pages:
        formal_image = job_dir / formal_deck_page_image_path(page)
        if not formal_image.exists():
            raise HTTPException(status_code=500, detail=f"P{page.page_no:02d} 正式图片缺失")
        page.result_state = "generated"
        page.updated_at = now
        (job_dir / page.result_path).write_text(
            build_formal_image_result_note(page, formal_deck_page_image_path(page), manifest.get("generation_mode")),
            encoding="utf-8",
        )
    write_page_index(job_dir, pages)

    current_status = read_status(job_id)
    artifacts = [
        formal_image_manifest_path(),
        *[formal_deck_page_image_path(page) for page in pages],
    ]
    current_status.stage_artifacts["image_ppt_generation"] = sorted(
        set(current_status.stage_artifacts.get("image_ppt_generation", []) + artifacts)
    )
    current_status.output_file = None
    write_status(job_dir, current_status)
    update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW)
    write_logs(job_dir, f"Formal image generation finished: {generated_count} pages.\n", append=True)
    return read_deck_pages(job_id), generated_count, "正式图片已生成，可继续打包图片版 PPTX 和交接包。"


def render_deck_page_image(job_id: str, page_id: str) -> tuple[DeckPage, str]:
    job_dir, pages, page = find_deck_page(job_id, page_id)
    if page.prompt_state == "needs_regeneration":
        raise HTTPException(status_code=409, detail="请先重生成本页提示词，再生成结构预览")

    image_path = deck_page_image_path(page)
    prompt = build_codex_image_prompt(job_dir, read_status(job_id), [page])
    write_logs(job_dir, f"Codex Stage 2 started for P{page.page_no:02d}.\n", append=True)
    update_status(job_id, PipelineStatus.IMAGE_PPT_GENERATION)
    try:
        returncode, stdout, stderr, command = run_codex_in_job(job_dir, prompt)
    except subprocess.TimeoutExpired as exc:
        update_status(job_id, PipelineStatus.FAILED, error=f"Codex 生成 P{page.page_no:02d} 结构预览超时")
        write_logs(job_dir, f"Codex Stage 2 timeout: {exc}\n", append=True)
        raise HTTPException(status_code=504, detail="Codex 生成本页结构预览超时，请稍后重试。") from exc

    write_logs(job_dir, f"Codex Stage 2 command: {' '.join(command[:5])} <job_dir> -\n", append=True)
    if stdout:
        write_logs(job_dir, stdout, append=True)
    if stderr:
        write_logs(job_dir, stderr, append=True)
    if returncode != 0:
        update_status(job_id, PipelineStatus.FAILED, error=f"Codex 生成 P{page.page_no:02d} 结构预览失败")
        raise HTTPException(status_code=500, detail="Codex 生成本页结构预览失败，请查看日志。")
    write_codex_svg_bundle(job_dir, [page], stdout)
    normalize_svg_artifact(job_dir / image_path)

    result = build_image_result_note(page, image_path)
    (job_dir / page.result_path).write_text(result, encoding="utf-8")
    page.result_state = "structure_preview"
    page.updated_at = utcish_now()
    write_page_index(job_dir, pages)
    write_logs(job_dir, f"Codex P{page.page_no:02d} structure preview generated.\n", append=True)
    return page, result


def render_all_deck_page_images(job_id: str) -> tuple[list[DeckPage], int]:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        raise HTTPException(status_code=409, detail=f"{names} 提示词待重生成，不能批量生成结构预览")

    if not pages:
        return [], 0

    prompt = build_codex_image_prompt(job_dir, read_status(job_id), pages)
    write_logs(job_dir, f"Codex Stage 2 batch started for {len(pages)} pages.\n", append=True)
    update_status(job_id, PipelineStatus.IMAGE_PPT_GENERATION)
    try:
        returncode, stdout, stderr, command = run_codex_in_job(job_dir, prompt)
    except subprocess.TimeoutExpired as exc:
        update_status(job_id, PipelineStatus.FAILED, error="Codex 批量生成结构预览超时")
        write_logs(job_dir, f"Codex Stage 2 batch timeout: {exc}\n", append=True)
        raise HTTPException(status_code=504, detail="Codex 批量生成结构预览超时，请稍后重试。") from exc

    write_logs(job_dir, f"Codex Stage 2 batch command: {' '.join(command[:5])} <job_dir> -\n", append=True)
    if stdout:
        write_logs(job_dir, stdout, append=True)
    if stderr:
        write_logs(job_dir, stderr, append=True)
    if returncode != 0:
        update_status(job_id, PipelineStatus.FAILED, error="Codex 批量生成结构预览失败")
        raise HTTPException(status_code=500, detail="Codex 批量生成结构预览失败，请查看日志。")
    write_codex_svg_bundle(job_dir, pages, stdout)

    now = utcish_now()
    generated = 0
    for page in pages:
        normalize_svg_artifact(job_dir / deck_page_image_path(page))
        result = build_image_result_note(page, deck_page_image_path(page))
        (job_dir / page.result_path).write_text(result, encoding="utf-8")
        page.result_state = "structure_preview"
        page.updated_at = now
        generated += 1
    write_page_index(job_dir, pages)
    write_logs(job_dir, f"Codex Stage 2 batch generated {generated} structure previews.\n", append=True)
    return read_deck_pages(job_id), generated


def build_codex_image_prompt(job_dir: Path, status: JobStatus, pages: list[DeckPage]) -> str:
    page_blocks: list[str] = []
    for page in pages:
        script = (job_dir / page.script_path).read_text(encoding="utf-8", errors="replace")
        prompt = (job_dir / page.prompt_path).read_text(encoding="utf-8", errors="replace")
        page_blocks.append(
            f"""## P{page.page_no:02d} {page.title}

输出文件：`{deck_page_image_path(page)}`
说明文件：`work/02_image_ppt/results/page-{page.page_no:02d}.md`

### 页面脚本

{trim_for_codex_prompt(script, 9000)}

### 图片生成提示词

{trim_for_codex_prompt(prompt, 9000)}
"""
        )
    page_content = "\n\n".join(page_blocks)
    return f"""你是解决方案部 AI PPT 生产线第二步的 Codex 低保真结构预览生成者。请只在当前任务目录内读写文件。

任务：根据下面已经给出的每页页面脚本和图片生成提示词，生成用于审阅版式方向的 16:9 SVG 结构预览。

重要边界：
- SVG 结构预览不是正式图片 PPT，不得被当成可汇报图片终稿。
- 正式图片 PPT 必须由内置图像生成能力生成 PNG 图片后再打包。
- 你只负责生成低保真结构预览，帮助检查页面逻辑、布局方向和文字边界。

重要执行限制：
- 不要运行 `pwd`、`ls`、`cat`、`sed`、`python`、`node` 或任何 shell/终端命令。
- 不要再读取文件；本提示词已经包含生成所需内容。
- 不要直接写文件；只输出后端可解析的 JSON，由后端负责写入任务目录。

项目：{status.title}
使用场景：{status.scenario or "待确认"}
受众对象：{status.audience or "待确认"}
风格：{status.style}

页面内容：

{page_content}

每个输出 SVG 必须满足：
- 不要创建 `codex_specs/`、`codex_tasks/`、`codex_reviews/` 或其他与本任务产物无关的目录。
- 画布固定 `width="1600"`、`height="900"`、`viewBox="0 0 1600 900"`。
- 所有页面可见文字必须是中文；不要出现 English UI 文案、Lorem ipsum 或代码注释。
- 不能把长段落塞进一个文本框；标题、核心观点、节点、标签必须分层，避免文字越界。
- 每页左上角必须保留敢为云 Logo 位：当前没有上传真实素材时，用“敢为云”三个中文作为文字 Logo 占位；Logo 高度与页面主标题字体高度大致一致，后续可替换为真实 Logo 素材。
- P01 必须按封面页处理，突出项目名称、汇报场景、提交人/团队和日期，不要画成普通流程页。
- P02 必须按目录页处理，用清晰章节列表或步骤条展示后续页面结构，不要画成普通内容页。
- 采用企业级解决方案汇报风格：深蓝标题栏、浅蓝灰背景、白色内容卡片、流程/架构/矩阵为主。
- 不要使用外部图片、远程链接、客户 Logo、金额、百分比或材料没有依据的客户系统名。
- 如果材料不足，请在图中使用“待确认”“待补充”“待对接”等表达。
- SVG 字符串内不要写 Markdown 代码围栏，只写合法 SVG。

最终回答必须只输出一个 JSON 对象，不要输出解释、Markdown 或代码围栏。JSON 结构如下：

{{
  "slides": [
    {{
      "page_no": 1,
      "svg": "<svg ...>...</svg>",
      "note": "本页由 Codex 生成，可审阅但不是可编辑 PPT。"
    }}
  ]
}}
"""


def trim_for_codex_prompt(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n\n[内容已截断，按以上信息生成，不要补造缺失事实。]"


def write_codex_svg_bundle(job_dir: Path, pages: list[DeckPage], stdout: str) -> None:
    payload = parse_codex_json_payload(stdout)
    slides = payload.get("slides")
    if not isinstance(slides, list):
        raise HTTPException(status_code=500, detail="Codex 未返回可解析的结构预览 JSON。")

    by_no = {page.page_no: page for page in pages}
    written: set[int] = set()
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        try:
            page_no = int(slide.get("page_no"))
        except (TypeError, ValueError):
            continue
        page = by_no.get(page_no)
        svg = str(slide.get("svg") or "").strip()
        note = str(slide.get("note") or "本页由 Codex 生成，可审阅但不是可编辑 PPT。").strip()
        if not page or "<svg" not in svg or "</svg>" not in svg:
            continue
        image_path = job_dir / deck_page_image_path(page)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_text(svg + "\n", encoding="utf-8")
        (job_dir / page.result_path).write_text(
            f"# P{page.page_no:02d} 结构预览结果\n\n状态：Codex 低保真结构预览已生成。\n\n说明：{note}\n\n边界：这不是正式图片 PPT，只能用于检查页面逻辑和布局方向。\n",
            encoding="utf-8",
        )
        written.add(page_no)

    missing = [f"P{page.page_no:02d}" for page in pages if page.page_no not in written and not (job_dir / deck_page_image_path(page)).exists()]
    if missing:
        raise HTTPException(status_code=500, detail=f"Codex 未返回这些页面的 SVG：{'、'.join(missing)}")


def parse_codex_json_payload(stdout: str) -> dict:
    text = stdout.strip()
    if "```" in text:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise HTTPException(status_code=500, detail="Codex 输出中没有 JSON 对象。")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Codex 结构预览 JSON 解析失败。") from exc


def normalize_svg_artifact(path: Path) -> None:
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"{path.name} 未生成，请重试。")
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if "<svg" not in raw or "</svg>" not in raw:
        raise HTTPException(status_code=500, detail=f"{path.name} 不是有效 SVG。")
    start = raw.find("<svg")
    end = raw.rfind("</svg>") + len("</svg>")
    svg = raw[start:end].strip()
    if not re.search(r"\bwidth\s*=\s*['\"]1600['\"]", svg):
        svg = re.sub(r"\swidth\s*=\s*['\"][^'\"]+['\"]", "", svg, count=1)
        svg = re.sub(r"<svg\b", '<svg width="1600"', svg, count=1)
    if not re.search(r"\bheight\s*=\s*['\"]900['\"]", svg):
        svg = re.sub(r"\sheight\s*=\s*['\"][^'\"]+['\"]", "", svg, count=1)
        svg = re.sub(r"<svg\b", '<svg height="900"', svg, count=1)
    if not re.search(r"\bviewBox\s*=", svg):
        svg = re.sub(r"<svg\b", '<svg viewBox="0 0 1600 900"', svg, count=1)
    path.write_text(svg + "\n", encoding="utf-8")


def build_image_ppt_package(job_id: str) -> dict:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能生成图片 PPT 交付包")

    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        raise HTTPException(status_code=409, detail=f"{names} 提示词待重生成，不能生成图片 PPT 交付包")

    image_dir = job_dir / "work" / "02_image_ppt"
    assets_dir = image_dir / "assets"
    output_dir = image_dir / "output"
    qa_dir = image_dir / "qa"
    handoff_dir = image_dir / "handoff-to-ppt-image-rebuilder"
    for directory in (assets_dir, output_dir, qa_dir, handoff_dir):
        directory.mkdir(parents=True, exist_ok=True)

    formal_manifest = read_formal_image_manifest(job_dir)
    if int(formal_manifest.get("slide_count") or 0) != len(pages):
        raise HTTPException(status_code=409, detail="正式图片页数与当前脚本页数不一致，请重新生成正式图片。")
    generation_mode = str(formal_manifest.get("generation_mode") or "")
    if "renderer" in generation_mode:
        raise HTTPException(
            status_code=409,
            detail="检测到的是历史本地渲染结果，不是 Codex 正式图片生成结果，不能打包为图片版 PPT。",
        )

    source_prompt_path = image_dir / "source-prompts.md"
    source_prompt_path.write_text(build_source_prompts_bundle(job_dir, pages), encoding="utf-8")

    formal_slides = {
        int(slide.get("slide_no")): slide
        for slide in formal_manifest.get("slides", [])
        if isinstance(slide, dict) and str(slide.get("slide_no", "")).isdigit()
    }
    slides = []
    for page in pages:
        formal_slide = formal_slides.get(page.page_no, {})
        asset_path = assets_dir / f"slide-{page.page_no:02d}.png"
        if not asset_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"P{page.page_no:02d} 正式图片尚未生成，当前结构预览不能打包为图片版 PPTX。",
            )
        slides.append(
            {
                "slide_no": page.page_no,
                "page_id": f"P{page.page_no:02d}",
                "page_key": page.page_id,
                "title": page.title,
                "prompt_path": f"prompts/slide-{page.page_no:02d}.md",
                "script_path": f"../01_requirements/pages/page-{page.page_no:02d}.md",
                "image_path": f"assets/slide-{page.page_no:02d}.png",
                "generation_mode": formal_slide.get("generation_mode", formal_manifest.get("generation_mode")),
            }
        )

    status = read_status(job_id)
    manifest = {
        "project_id": job_id,
        "title": status.title,
        "requester_name": status.requester_name,
        "stage": "image_ppt_generation",
        "draft_type": "正式图片版 PPT",
        "editability": "图片版草稿，不是可编辑 PPT；第三步需要继续做可编辑重建。",
        "generation_mode": formal_manifest.get("generation_mode"),
        "formal_image_manifest": formal_image_manifest_path(),
        "source_prompt": "source-prompts.md",
        "output_pptx": "output/image-draft.pptx",
        "slide_count": len(slides),
        "slides": slides,
        "generated_at": utcish_now(),
    }
    (image_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    run_image_deck_assembler(image_dir)

    image_pptx = image_dir / "output" / "image-draft.pptx"
    if not image_pptx.exists():
        raise HTTPException(status_code=500, detail="图片版 PPTX 未生成，请检查后端组装脚本")
    final_output = job_dir / "output" / "image-draft.pptx"
    shutil.copyfile(image_pptx, final_output)

    safe_manifest = json.loads((image_dir / "manifest.json").read_text(encoding="utf-8"))
    write_image_ppt_handoff(image_dir, status.title, safe_manifest)
    package_zip = write_image_ppt_zip(image_dir, job_dir)

    current_status = read_status(job_id)
    image_artifacts = [
        "work/02_image_ppt/manifest.json",
        "work/02_image_ppt/formal-image-manifest.json",
        "work/02_image_ppt/source-prompts.md",
        "work/02_image_ppt/qa/contact-sheet.png",
        "work/02_image_ppt/output/image-draft.pptx",
        "work/02_image_ppt/handoff-to-ppt-image-rebuilder/README.md",
        "work/02_image_ppt/handoff-to-ppt-image-rebuilder/handoff-prompt.md",
        "output/image-draft.pptx",
        "output/image-ppt-package.zip",
    ]
    current_status.stage_artifacts["image_ppt_generation"] = sorted(
        set(current_status.stage_artifacts.get("image_ppt_generation", []) + image_artifacts)
    )
    write_status(job_dir, current_status)
    update_status(job_id, PipelineStatus.DONE, output_file="image-draft.pptx")
    write_logs(job_dir, "Codex image PPT package generated.\n", append=True)

    return {
        "package_state": "ready",
        "slide_count": len(slides),
        "output_file": final_output.name,
        "package_file": package_zip.name,
        "artifacts": image_artifacts,
        "note": "已生成正式图片版 PPT 包。它用于汇报前审阅和进入后续可编辑重建任务，不等同于最终可编辑 PPT。",
    }


def build_script_package(job_id: str) -> dict:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能导出脚本包。请先生成生产脚本。")

    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / "script-package.zip"
    include_paths = [
        "prompt.md",
        "work/01_requirements/01_requirements.md",
        "work/01_requirements/source-inventory.md",
        "work/01_requirements/knowledge-base-inventory.md",
        "work/01_requirements/facts.md",
        "work/01_requirements/open-questions.md",
        "work/01_requirements/generation-mode.md",
        "work/01_requirements/codex-generation.md",
        "work/01_requirements/ppt-script.md",
        "work/01_requirements/page-index.json",
    ]
    include_paths.extend(page.script_path for page in pages)
    include_paths.extend(page.prompt_path for page in pages)
    include_paths.extend(page.result_path for page in pages)

    manifest = {
        "job_id": job_id,
        "title": read_status(job_id).title,
        "requester_name": read_status(job_id).requester_name,
        "package_type": "ppt_script_production_package",
        "slide_count": len(pages),
        "generated_at": utcish_now(),
        "contains": [
            "requirement summary",
            "company knowledge-base inventory",
            "facts and open questions",
            "page-level PPT scripts",
            "page-level image-production prompts",
        ],
        "non_goals": [
            "no generated slide images",
            "no image-only PPTX",
            "no editable PPTX",
        ],
    }

    with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for relative in include_paths:
            path = job_dir / relative
            if path.exists() and path.is_file():
                archive.write(path, relative)

    current_status = read_status(job_id)
    current_status.output_file = package_path.name
    current_status.stage_artifacts["script_package"] = ["output/script-package.zip"]
    write_status(job_dir, current_status)
    write_logs(job_dir, "Script package generated: output/script-package.zip\n", append=True)

    return {
        "package_state": "ready",
        "slide_count": len(pages),
        "output_file": package_path.name,
        "package_file": package_path.name,
        "artifacts": ["output/script-package.zip"],
        "note": "已生成 PPT 生产脚本包，可下载交给后续图片 PPT 制作流程使用。",
    }


def build_script_markdown(job_id: str) -> dict:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能下载 Markdown。请先生成生产脚本。")

    script_path = job_dir / "work" / "01_requirements" / "ppt-script.md"
    if not script_path.exists():
        write_combined_ppt_script(job_dir, pages)
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Markdown 脚本文档不存在，请重新生成脚本。")

    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "ppt-script.md"
    markdown_path.write_text(script_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

    current_status = read_status(job_id)
    current_status.output_file = markdown_path.name
    current_status.stage_artifacts["script_markdown"] = ["output/ppt-script.md"]
    write_status(job_dir, current_status)
    write_logs(job_dir, "Markdown script generated: output/ppt-script.md\n", append=True)

    return {
        "package_state": "ready",
        "slide_count": len(pages),
        "output_file": markdown_path.name,
        "package_file": markdown_path.name,
        "artifacts": ["output/ppt-script.md"],
        "note": "已生成页面脚本 Markdown，用于人工审阅每页讲什么、依据和边界是否正确。",
    }


def build_prompt_markdown(job_id: str) -> dict:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能下载图片生产提示词。请先生成生产脚本。")

    chunks = [
        "# 当前任务逐页图片生产提示词",
        "",
        "用途：给后续图片 PPT 制作工具或模型使用，说明每一页如何排版、画什么结构、放哪些上屏文字，以及哪些内容不能出现。",
        "",
    ]
    for page in pages:
        prompt_path = job_dir / page.prompt_path
        if not prompt_path.exists():
            raise HTTPException(status_code=404, detail=f"P{page.page_no:02d} 图片生产提示词不存在，请重新生成脚本。")
        chunks.append(prompt_path.read_text(encoding="utf-8", errors="replace").strip())
        chunks.append("")

    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "image-production-prompts.md"
    markdown_path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")

    current_status = read_status(job_id)
    current_status.output_file = markdown_path.name
    current_status.stage_artifacts["prompt_markdown"] = ["output/image-production-prompts.md"]
    write_status(job_dir, current_status)
    write_logs(job_dir, "Image production prompts Markdown generated: output/image-production-prompts.md\n", append=True)

    return {
        "package_state": "ready",
        "slide_count": len(pages),
        "output_file": markdown_path.name,
        "package_file": markdown_path.name,
        "artifacts": ["output/image-production-prompts.md"],
        "note": "已生成图片生产提示词 Markdown，用于后续图片 PPT 制作工具或模型。",
    }


def prepare_codex_stage2_image_ppt_request(job_id: str) -> dict:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        raise HTTPException(status_code=409, detail="当前任务还没有逐页脚本，不能生成图片版 PPT")

    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        raise HTTPException(status_code=409, detail=f"{names} 提示词待重生成，不能提交图片版 PPT 生产")

    image_dir = job_dir / "work" / "02_image_ppt"
    assets_dir = image_dir / "assets"
    output_dir = image_dir / "output"
    qa_dir = image_dir / "qa"
    for directory in (image_dir, assets_dir, output_dir, qa_dir):
        directory.mkdir(parents=True, exist_ok=True)

    source_prompt_path = image_dir / "source-prompts.md"
    request_path = image_dir / "codex-stage2-operator-request.md"
    request_state_path = image_dir / "codex-stage2-request.json"
    source_prompt_path.write_text(build_source_prompts_bundle(job_dir, pages), encoding="utf-8")

    slide_lines = "\n".join(
        f"- P{page.page_no:02d} `{page.page_id}`：{page.title} -> `work/02_image_ppt/assets/slide-{page.page_no:02d}.png`"
        for page in pages
    )
    request = f"""# Codex Stage 2 图片版 PPT 生产任务

任务 ID：`{job_id}`
任务标题：{read_status(job_id).title}
页数：{len(pages)}
提交人：{read_status(job_id).requester_name}

## 生产目标

请由当前 Codex 会话执行第二步 `制作图片 PPT`，使用内置图片生成能力逐页生成 16:9 PNG 图片，并回写到本任务目录。

必须注意：
- 不要调用本地 deterministic renderer 作为正式交付。
- 不要使用旧的本地 SVG 结构预览作为正式交付。
- 不要把图片版 PPT 称为可编辑 PPT。
- 每页必须以 `work/01_requirements/pages/page-*.md` 和 `work/02_image_ppt/prompts/slide-*.md` 为语义真值。
- 若某页提示词质量不足，先停止并报告，不要用占位稿补齐。

## 输入

- 源提示词包：`work/02_image_ppt/source-prompts.md`
- 逐页脚本：`work/01_requirements/pages/page-*.md`
- 逐页图片提示词：`work/02_image_ppt/prompts/slide-*.md`

## 需要生成的图片

{slide_lines}

## 回写要求

1. 逐页生成 PNG，保存到 `work/02_image_ppt/assets/slide-XX.png`。
2. 写入 `work/02_image_ppt/formal-image-manifest.json`，字段至少包括：
   - `stage`: `image_ppt_generation`
   - `generation_mode`: `codex_builtin_image_generation`
   - `slide_count`
   - `slides`: 每页 `slide_no/title/image_path/generation_mode`
3. 每页更新 `work/02_image_ppt/results/page-XX.md`，说明正式图片已生成。
4. 图片全部生成后，调用后端打包接口或等价组装流程生成：
   - `output/image-draft.pptx`
   - `output/image-ppt-package.zip`
5. 如生成失败，写明失败页码和原因，不允许回写假结果。

## 当前状态

本文件只代表浏览器用户已提交第二步生产请求；真正图片生成由 Codex 会话执行。
"""
    request_path.write_text(request, encoding="utf-8")

    state = {
        "state": "needs_codex_operator",
        "job_id": job_id,
        "title": read_status(job_id).title,
        "slide_count": len(pages),
        "requested_at": utcish_now(),
        "source_prompt": "work/02_image_ppt/source-prompts.md",
        "operator_request": "work/02_image_ppt/codex-stage2-operator-request.md",
        "next_step": "Codex must generate slide PNGs with built-in image generation, then package the image PPT.",
    }
    request_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    current_status = read_status(job_id)
    current_status.stage_artifacts["image_ppt_generation"] = sorted(
        set(
            current_status.stage_artifacts.get("image_ppt_generation", [])
            + [
                "work/02_image_ppt/source-prompts.md",
                "work/02_image_ppt/codex-stage2-operator-request.md",
                "work/02_image_ppt/codex-stage2-request.json",
            ]
        )
    )
    current_status.output_file = None
    write_status(job_dir, current_status)
    update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW)
    write_logs(job_dir, "Codex Stage 2 image PPT request prepared; waiting for Codex operator generation.\n", append=True)

    return {
        "state": "needs_codex_operator",
        "slide_count": len(pages),
        "request_file": "work/02_image_ppt/codex-stage2-operator-request.md",
        "source_prompt": "work/02_image_ppt/source-prompts.md",
        "note": "已提交第二步图片版 PPT 生产请求。当前不会使用本地兜底；需要 Codex 会话读取任务包并生成图片后回写。",
    }


def run_codex_visual_image_ppt(job_id: str) -> None:
    job_dir = get_job_dir(job_id)
    pages = read_deck_pages(job_id)
    if not pages:
        update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW, error="当前任务还没有逐页脚本，不能生成图片版 PPT")
        write_logs(job_dir, "Codex visual image PPT blocked: no page scripts.\n", append=True)
        return

    stale_pages = [page for page in pages if page.prompt_state == "needs_regeneration"]
    if stale_pages:
        names = "、".join(f"P{page.page_no:02d}" for page in stale_pages)
        update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW, error=f"{names} 提示词待重生成")
        write_logs(job_dir, f"Codex visual image PPT blocked: stale prompts {names}.\n", append=True)
        return

    image_dir = job_dir / "work" / "02_image_ppt"
    html_dir = image_dir / "codex-html"
    (html_dir / "slides").mkdir(parents=True, exist_ok=True)
    (image_dir / "assets").mkdir(parents=True, exist_ok=True)
    (image_dir / "source-prompts.md").write_text(build_source_prompts_bundle(job_dir, pages), encoding="utf-8")

    current_status = read_status(job_id)
    current_status.stage_artifacts["image_ppt_generation"] = ["work/02_image_ppt/source-prompts.md"]
    current_status.output_file = None
    write_status(job_dir, current_status)
    update_status(job_id, PipelineStatus.IMAGE_PPT_GENERATION)
    write_logs(job_dir, f"Codex visual image PPT started for {len(pages)} pages.\n", append=True)
    prompt = build_codex_visual_html_prompt(job_dir, read_status(job_id), pages)
    try:
        returncode, stdout, stderr, command = run_codex_in_job(job_dir, prompt, timeout=settings.worker_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        update_status(job_id, PipelineStatus.FAILED, error="Codex 视觉页生成超时")
        write_logs(job_dir, f"Codex visual HTML timeout: {exc}\n", append=True)
        return

    write_logs(job_dir, f"Codex visual HTML command: {' '.join(command[:5])} <job_dir> -\n", append=True)
    if stdout:
        write_logs(job_dir, stdout, append=True)
    if stderr:
        write_logs(job_dir, stderr, append=True)
    if returncode != 0:
        update_status(job_id, PipelineStatus.FAILED, error="Codex 视觉页生成失败")
        write_logs(job_dir, "Codex visual HTML failed.\n", append=True)
        return

    try:
        validate_codex_html_manifest(job_dir, pages)
        capture_codex_html_slides(job_dir)
        mark_formal_pages_generated(job_id, job_dir, pages)
        package = build_image_ppt_package(job_id)
    except Exception as exc:
        detail = str(exc)
        update_status(job_id, PipelineStatus.FAILED, error=detail[-500:])
        write_logs(job_dir, f"Codex visual image PPT failed: {detail}\n", append=True)
        return

    write_logs(job_dir, f"Codex visual image PPT finished: {package.get('slide_count')} pages.\n", append=True)


def build_codex_visual_html_prompt(job_dir: Path, status: JobStatus, pages: list[DeckPage]) -> str:
    page_blocks: list[str] = []
    for page in pages:
        script = (job_dir / page.script_path).read_text(encoding="utf-8", errors="replace")
        prompt = (job_dir / page.prompt_path).read_text(encoding="utf-8", errors="replace")
        page_blocks.append(
            f"""## P{page.page_no:02d} {page.title}

输出 HTML：`work/02_image_ppt/codex-html/slides/slide-{page.page_no:02d}.html`

### 页面脚本

{trim_for_codex_prompt(script, 11000)}

### 图片生成提示词

{trim_for_codex_prompt(prompt, 11000)}
"""
        )

    return f"""你是解决方案部 AI PPT 生产线第二步的 Codex 视觉执行器。你的任务不是生成占位稿，也不是调用本地固定模板，而是根据已经审核的逐页脚本和提示词，写出可被浏览器截图成正式图片版 PPT 的高保真 HTML 页面。

项目：{status.title}
提交人：{status.requester_name}
使用场景：{status.scenario or "待确认"}
受众对象：{status.audience or "待确认"}
风格：{status.style}
总页数：{len(pages)}

硬性输出：
1. 为每页写一个独立 HTML 文件，路径必须严格等于每页块中给出的 `输出 HTML`。
2. 写入 `work/02_image_ppt/codex-html/manifest.json`，结构如下：
{{
  "stage": "image_ppt_generation",
  "generation_mode": "codex_visual_html_render",
  "slide_count": {len(pages)},
  "slides": [
    {{"slide_no": 1, "title": "页面标题", "html_path": "work/02_image_ppt/codex-html/slides/slide-01.html"}}
  ]
}}
3. 不要写 PNG、PPTX、ZIP；后端会截图和打包。

视觉要求：
- 每个 HTML 页面固定 1600x900 画布，页面不能滚动，不能出现浏览器默认边距。
- 必须是可用于客户汇报的中文企业级解决方案页，不是线框稿、占位稿、代码示例或普通网页。
- 所有可见文字必须是简体中文；不要出现英文 UI、Lorem ipsum、代码注释或无意义短语。
- P01 必须是封面，P02 必须是目录，后续页按脚本的图示结构制作。
- 左上角保留“敢为云”文字 Logo 位，高度和标题字体大致相符。
- 主体要有真实信息层级：标题、核心观点、图示结构、关键节点、待确认边界、页码。
- 不要把长讲稿塞到页面上；只使用脚本中的上屏文字、关键词、节点和短句。
- 风格继承智慧后勤方案的企业级解决方案汇报感：深蓝标题栏、浅蓝灰背景、白色内容区、流程/架构/矩阵/看板、细线连接、克制强调色。
- 禁止使用外部图片、远程字体、在线图标库、客户 Logo、金额、百分比、无来源系统名、个人信息。
- 如果材料不足，请用“待确认”“待补充”“待对接”标注，不要编造。

工程要求：
- HTML/CSS/少量内联 SVG 均可，但每页必须自包含，不引用外部资源。
- 使用 CSS grid/flex/svg 保证截图时文字不越界、不重叠、不被裁切。
- 文件路径只能在 `work/02_image_ppt/codex-html/` 内；不要创建其他目录。
- 不要修改页面脚本、提示词、状态文件、日志或输出目录。

页面内容：

{chr(10).join(page_blocks)}

完成后只用一句中文说明已写入 HTML 和 manifest。"""


def validate_codex_html_manifest(job_dir: Path, pages: list[DeckPage]) -> None:
    manifest_path = job_dir / "work" / "02_image_ppt" / "codex-html" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("Codex 未写入 codex-html/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    slides = manifest.get("slides")
    if not isinstance(slides, list) or len(slides) != len(pages):
        raise RuntimeError("Codex HTML manifest 页数与当前脚本页数不一致")
    expected = {page.page_no: page for page in pages}
    for slide in slides:
        page_no = int(slide.get("slide_no") or 0)
        if page_no not in expected:
            raise RuntimeError(f"Codex HTML manifest 包含未知页码：{page_no}")
        html_path = str(slide.get("html_path") or "")
        expected_path = f"work/02_image_ppt/codex-html/slides/slide-{page_no:02d}.html"
        if html_path != expected_path:
            raise RuntimeError(f"P{page_no:02d} HTML 路径不正确：{html_path}")
        full_path = job_dir / html_path
        if not full_path.exists():
            raise RuntimeError(f"P{page_no:02d} HTML 文件缺失")
        raw = full_path.read_text(encoding="utf-8", errors="replace")
        if "<html" not in raw.lower() or "</html>" not in raw.lower():
            raise RuntimeError(f"P{page_no:02d} HTML 不是完整页面")


def capture_codex_html_slides(job_dir: Path) -> None:
    if not CODEX_HTML_CAPTURE.exists():
        raise RuntimeError("HTML 截图脚本不存在")
    result = subprocess.run(
        ["node", str(CODEX_HTML_CAPTURE), "--job-dir", str(job_dir)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.stdout:
        write_logs(job_dir, result.stdout, append=True)
    if result.stderr:
        write_logs(job_dir, result.stderr, append=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "HTML 截图失败").strip()
        raise RuntimeError(detail[-800:])


def mark_formal_pages_generated(job_id: str, job_dir: Path, pages: list[DeckPage]) -> None:
    manifest = read_formal_image_manifest(job_dir)
    if int(manifest.get("slide_count") or 0) != len(pages):
        raise RuntimeError("截图生成页数与当前脚本页数不一致")
    now = utcish_now()
    for page in pages:
        formal_image = job_dir / formal_deck_page_image_path(page)
        if not formal_image.exists():
            raise RuntimeError(f"P{page.page_no:02d} 正式图片缺失")
        page.result_state = "generated"
        page.updated_at = now
        (job_dir / page.result_path).write_text(
            build_formal_image_result_note(page, formal_deck_page_image_path(page), manifest.get("generation_mode")),
            encoding="utf-8",
        )
    write_page_index(job_dir, pages)
    current_status = read_status(job_id)
    artifacts = [
        formal_image_manifest_path(),
        "work/02_image_ppt/codex-html/manifest.json",
        *[formal_deck_page_image_path(page) for page in pages],
    ]
    current_status.stage_artifacts["image_ppt_generation"] = sorted(
        set(current_status.stage_artifacts.get("image_ppt_generation", []) + artifacts)
    )
    current_status.output_file = None
    write_status(job_dir, current_status)


def run_image_deck_assembler(image_dir: Path) -> None:
    if not IMAGE_DECK_ASSEMBLER.exists():
        raise HTTPException(status_code=500, detail="图片 PPT 组装脚本不存在")
    result = subprocess.run(
        ["node", str(IMAGE_DECK_ASSEMBLER), "--workspace", str(image_dir)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "图片 PPT 组装失败").strip()
        raise HTTPException(status_code=500, detail=detail[-800:])


def build_source_prompts_bundle(job_dir: Path, pages: list[DeckPage]) -> str:
    chunks = [
        "# 图片 PPT 生成源提示词包",
        "",
        "用途：作为第二步图片版 PPT 草稿和第三步可编辑重建的语义依据。",
        "说明：每页以页面脚本和图片生成提示词共同作为审阅依据；图片只作为视觉草稿参考。",
        "",
    ]
    for page in pages:
        script = (job_dir / page.script_path).read_text(encoding="utf-8", errors="replace").strip()
        prompt = (job_dir / page.prompt_path).read_text(encoding="utf-8", errors="replace").strip()
        chunks.extend(
            [
                f"## P{page.page_no:02d} {page.title}",
                "",
                "### 页面脚本",
                script,
                "",
                "### 图片生成提示词",
                prompt,
                "",
            ]
        )
    return "\n".join(chunks).rstrip() + "\n"


def write_image_ppt_handoff(image_dir: Path, title: str, manifest: dict) -> None:
    handoff_dir = image_dir / "handoff-to-ppt-image-rebuilder"
    slides = manifest.get("slides", [])
    slide_lines = "\n".join(f"- P{slide.get('slide_no', index + 1):02d}：{slide.get('title', '未命名页面')}" for index, slide in enumerate(slides))
    readme = f"""# 图片 PPT 转可编辑 PPT 交接说明

本包对应任务：{title}

## 当前阶段结论

已完成第二步“制作图片 PPT”的 MVP 交付包：图片版 PPTX、逐页图片、逐页提示词、联系表和交接提示。当前 PPTX 是图片版草稿，不是可编辑 PPT。第三步需要继续把标题、卡片、流程、表格、图标和连接线重建为可编辑 PowerPoint 对象。

## 包内内容

- 图片版 PPTX：`output/image-draft.pptx`
- 页面图片：`assets/slide-*.png`
- 每页提示词：`prompts/slide-*.md`
- 源提示词包：`source-prompts.md`
- 联系表：`qa/contact-sheet.png`
- 清单：`manifest.json`

## 页面清单

{slide_lines}

## 进入第三步时的边界

- 不改变页数、页序和主题。
- 不新增外部材料、真实金额、真实百分比、客户系统名、Logo 或个人信息。
- 待确认、需集成、需定制开发、信息不清的内容不能改写成已完成。
- 图片中文字可能有局部误差，第三步必须以页面脚本和提示词作为语义真值。
"""
    prompt = f"""# 给第三步“图片 PPT 转化”的提示

请读取本目录的 `manifest.json`、`source-prompts.md`、`prompts/slide-*.md`、`assets/slide-*.png` 和 `output/image-draft.pptx`，把图片版 PPT 草稿重建为可编辑 PPTX。

重建要求：

1. 保持 {len(slides)} 页，不增删页、不改页序。
2. 以页面脚本和每页提示词作为文字与语义真值，图片只作为版式参考。
3. 标题、段落、表格、架构层、流程节点、状态标签、线条、箭头和图标尽量用 PowerPoint 原生对象。
4. 对复杂背景或装饰图可以局部保留图片，但不能把主体内容整页截图化。
5. 输出可编辑 PPTX 后，需要做页面预览和可编辑性 QA。
"""
    (handoff_dir / "README.md").write_text(readme, encoding="utf-8")
    (handoff_dir / "handoff-prompt.md").write_text(prompt, encoding="utf-8")


def write_image_ppt_zip(image_dir: Path, job_dir: Path) -> Path:
    package_path = job_dir / "output" / "image-ppt-package.zip"
    members = [
        "manifest.json",
        "source-prompts.md",
        "qa/contact-sheet.png",
        "output/image-draft.pptx",
        "handoff-to-ppt-image-rebuilder/README.md",
        "handoff-to-ppt-image-rebuilder/handoff-prompt.md",
    ]
    members.extend(sorted(path.relative_to(image_dir).as_posix() for path in (image_dir / "assets").glob("slide-*.png")))
    members.extend(sorted(path.relative_to(image_dir).as_posix() for path in (image_dir / "prompts").glob("slide-*.md")))
    with ZipFile(package_path, "w", compression=ZIP_DEFLATED) as archive:
        for member in members:
            source = image_dir / member
            if source.exists() and source.is_file():
                archive.write(source, member)
    return package_path


def build_image_result_note(page: DeckPage, image_path: str) -> str:
    return f"""# P{page.page_no:02d} 结构预览结果

状态：Codex 低保真结构预览已生成，可在页面右侧直接预览。

说明：
- 本预览只用于检查页面逻辑、信息层级和版式方向。
- 当前 SVG 不是正式图片 PPT，不能进入图片版 PPTX 打包。
- 正式图片版 PPT 必须由后续正式图片生成能力产出 PNG 后，再写入交付包。

审阅建议：
- 先检查标题、核心观点、主体图示和待确认事项是否正确。
- 如果内容不对，请回到“页面脚本”修改并重新生成提示词。
- 如果视觉方向不对，请调整风格提示词后重新生成本页提示词和结构预览。

记录：Codex 结构预览已写入 `{image_path}`。正式图片未生成前，不能打包图片版 PPTX。
"""


def build_formal_image_result_note(page: DeckPage, image_path: str, generation_mode: str | None = None) -> str:
    if generation_mode == "codex_visual_html_render":
        return f"""# P{page.page_no:02d} Codex HTML 截图预览结果

状态：已生成 HTML 截图版页面，可在页面右侧预览，并可下载为图片版 PPTX 讨论稿。

说明：
- 本页由 Codex 写出 16:9 HTML 视觉页，再由本地 Chrome 截图为 PNG。
- 这不是 Codex Desktop image2.0 或内置图像模型直接生成的结果。
- 当前 PPTX 是 HTML 截图版讨论稿，不是最终可编辑 PPT，也不应按 image2.0 质量判断。
- 第三步转可编辑时，需要以页面脚本和图片生成提示词作为语义真值，以本 PNG 作为视觉参考。

审阅建议：
- 检查页面标题、核心观点、主体图示、待确认事项和页码是否正确。
- 如内容不对，请回到“页面脚本”修改并重新生成提示词与 HTML 截图版 PPT。
- 如追求智慧后勤同等级视觉质量，需要接入真正的原图片 PPT / image2.0 生成流程。

记录：HTML 截图图片已写入 `{image_path}`，可进入图片版 PPT 打包。
"""

    return f"""# P{page.page_no:02d} 图像模型结果

状态：图片页已生成，可在页面右侧预览，并可进入图片版 PPTX 打包。

说明：
- 本页已写入 PNG 资产，不再使用低保真 SVG 结构预览作为交付内容。
- 当前 PPTX 仍会是图片版 PPT，不是最终可编辑 PPT。
- 第三步转可编辑时，需要以页面脚本和图片生成提示词作为语义真值，以本 PNG 作为视觉参考。

审阅建议：
- 检查页面标题、核心观点、主体图示、待确认事项和页码是否正确。
- 如内容不对，请回到“页面脚本”修改并重新生成提示词与图片。
- 如只是视觉方向不满意，可先修改风格/边界提示词后重新生成图片。

记录：图片已写入 `{image_path}`，可进入图片版 PPT 打包。
"""


def build_image_draft_svg(page: DeckPage, script: str, prompt: str) -> str:
    brief = parse_page_brief(page, script)
    page_type = brief["page_type"]
    if "架构" in page_type or "数据" in page_type:
        body = svg_architecture_body(brief)
    elif "流程" in page_type:
        body = svg_flow_body(brief)
    elif "需求" in page_type or "风险" in page_type:
        body = svg_analysis_body(brief)
    elif "矩阵" in page_type or "指标" in page_type or "客服" in brief["title"]:
        body = svg_matrix_body(brief)
    elif "实施" in page_type:
        body = svg_roadmap_body(brief)
    elif "总结" in page_type:
        body = svg_closing_body(brief)
    else:
        body = svg_overview_body(brief)
    return svg_report_shell(page, brief, body)


def parse_page_brief(page: DeckPage, script: str) -> dict[str, object]:
    title = page.title
    core = "围绕当前任务形成清晰、可审阅的方案表达。"
    page_type = "汇报页"
    requirements: list[str] = []
    capabilities: list[str] = []
    talk_lines: list[str] = []
    in_talk = False
    for raw in script.splitlines():
        line = localize_prompt_terms(raw.strip().strip("- "))
        if line.startswith("## P"):
            title = line.split(" ", 2)[-1].strip() or title
        elif line.startswith("核心观点："):
            core = line.split("：", 1)[1].strip()
        elif line.startswith("页面类型："):
            page_type = line.split("：", 1)[1].strip()
        elif line.startswith("关联需求："):
            requirements = split_brief_items(line.split("：", 1)[1])
        elif line.startswith("关联能力："):
            capabilities = split_brief_items(line.split("：", 1)[1])
        elif line.startswith("讲稿"):
            in_talk = True
        elif line.startswith("审核备注"):
            in_talk = False
        elif in_talk and line:
            talk_lines.append(line)
    talk = " ".join(talk_lines) or core
    requirements = expand_requirement_items(requirements, title, page_type, talk)
    capabilities = expand_capability_items(capabilities, title, page_type, talk)
    return {
        "page_no": page.page_no,
        "title": title,
        "core": core,
        "page_type": page_type,
        "requirements": requirements[:5],
        "capabilities": capabilities[:6],
        "talk": talk,
    }


def split_brief_items(text: str) -> list[str]:
    items = re.split(r"[,，、;；]+", text)
    return [item.strip() for item in items if item.strip()]


def expand_requirement_items(items: list[str], title: str, page_type: str, talk: str) -> list[str]:
    localized = [localize_prompt_terms(item) for item in items if item.strip()]
    if len(localized) >= 3 or not ("需求" in page_type or "风险" in page_type):
        return localized or ["业务目标", "能力边界", "实施路径"]

    text = title + talk
    if "一站式" in text or "差旅" in text:
        derived = ["统一员工服务入口", "自动拆解多类后勤诉求", "资源确认与异常复核"]
    elif "资源" in text or "台账" in text:
        derived = ["资源入库与台账治理", "使用维修调剂报废闭环", "闲置资源盘活与跨基地协同"]
    elif "安全" in text or "巡检" in text:
        derived = ["责任区风险感知", "巡检整改闭环", "异常预警与工单联动"]
    else:
        derived = ["当前痛点识别", "目标状态拆解", "待确认边界显性化"]
    return merge_unique(localized, derived)[:5]


def expand_capability_items(items: list[str], title: str, page_type: str, talk: str) -> list[str]:
    localized = [localize_prompt_terms(item) for item in items if item.strip()]
    text = title + page_type + talk
    defaults = ["数据治理能力", "流程编排能力", "智能协同能力", "可视化分析能力"]
    if "安全" in text or "巡检" in text:
        defaults = ["物联感知能力", "视频识别能力", "安全工单能力", "闭环追踪能力"]
    elif "客服" in text:
        defaults = ["知识库能力", "智能问答能力", "工单转派能力", "服务评价能力"]
    elif "资源" in text:
        defaults = ["资源台账能力", "生命周期管理能力", "可视化分析能力", "问数决策能力"]
    elif "流程" in page_type or "入口" in text:
        defaults = ["自然语言理解能力", "流程编排能力", "接口集成能力", "人工复核能力"]
    return merge_unique(localized, defaults)[:6]


def merge_unique(primary: list[str], fallback: list[str]) -> list[str]:
    merged: list[str] = []
    for item in primary + fallback:
        label = item.strip()
        if label and label not in merged:
            merged.append(label)
    return merged


def svg_report_shell(page: DeckPage, brief: dict[str, object], body: str) -> str:
    title = escape(str(brief["title"]))
    core_lines = svg_text_lines(str(brief["core"]), 112, 180, 58, 24, "#17324d", 30, 2, weight=700)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
  <defs>
    <filter id="softShadow" x="-10%" y="-10%" width="120%" height="130%">
      <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#15324f" flood-opacity="0.10"/>
    </filter>
  </defs>
  <rect width="1600" height="900" fill="#f4f8fb"/>
  <rect x="0" y="0" width="1600" height="92" fill="#153f73"/>
  <rect x="0" y="92" width="1600" height="8" fill="#2c7fb8"/>
  <rect x="60" y="24" width="112" height="42" rx="8" fill="#ffffff" opacity="0.96"/>
  <text x="78" y="53" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="800">敢为云</text>
  <text x="204" y="58" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="37" font-weight="700">P{page.page_no:02d} {title}</text>
  <text x="1288" y="56" fill="#b9d7f5" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">图片版PPT汇报草稿</text>
  <rect x="76" y="124" width="1448" height="96" rx="18" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <rect x="92" y="142" width="8" height="60" rx="4" fill="#2c7fb8"/>
  <text x="112" y="153" fill="#2c7fb8" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17" font-weight="700">核心观点</text>
  {core_lines}
  {body}
  <text x="82" y="846" fill="#7890a2" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="16">说明：本页由页面脚本生成，用于图片版PPT初稿审阅；涉及接口、数量、金额、上线状态等必须以资料确认为准。</text>
  <text x="1456" y="846" fill="#7890a2" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">P{page.page_no:02d}</text>
</svg>
"""


def svg_overview_body(brief: dict[str, object]) -> str:
    requirements = list(brief["requirements"])
    capabilities = list(brief["capabilities"])
    talk = str(brief["talk"])
    cards = "".join(
        svg_small_card(112 + index * 288, 276, 250, 130, f"0{index + 1}", item, "#eef6ff")
        for index, item in enumerate(requirements[:5])
    )
    pillars = "".join(
        svg_pillar(180 + index * 330, 510, 260, 168, item, ["数据沉淀", "流程闭环", "智能协同", "安全边界", "持续优化"][index % 5])
        for index, item in enumerate(capabilities[:4])
    )
    return f"""
  <text x="96" y="265" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="700">方案定位与需求主线</text>
  {cards}
  <rect x="96" y="452" width="1408" height="284" rx="20" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="494" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="24" font-weight="700">能力支撑</text>
  {pillars}
  <rect x="128" y="706" width="1344" height="46" rx="10" fill="#eaf3f5"/>
  {svg_text_lines(talk, 154, 735, 86, 17, "#36556f", 19, 1)}
"""


def svg_architecture_body(brief: dict[str, object]) -> str:
    caps = list(brief["capabilities"])
    reqs = list(brief["requirements"])
    modules = (caps + ["数据治理", "流程编排", "可视化分析", "智能问答"])[:6]
    upstream = reqs[:4] or ["业务系统", "数据接口", "物联设备", "服务入口"]
    module_cards = "".join(
        svg_module_box(228 + (index % 3) * 342, 392 + (index // 3) * 96, 280, 66, item)
        for index, item in enumerate(modules)
    )
    upstream_cards = "".join(
        svg_tag(210 + index * 300, 650, item, "#eef6ff", "#256bd8")
        for index, item in enumerate(upstream[:4])
    )
    return f"""
  <rect x="96" y="252" width="1408" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="300" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">总体架构：入口、平台、数据与场景闭环</text>
  <rect x="164" y="338" width="1272" height="70" rx="16" fill="#153f73"/>
  <text x="690" y="382" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="26" font-weight="700">智慧后勤综合管理平台</text>
  <text x="154" y="448" fill="#7890a2" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">平台能力层</text>
  {module_cards}
  <line x1="800" y1="408" x2="800" y2="624" stroke="#8eb8d7" stroke-width="4" stroke-dasharray="10 10"/>
  <text x="154" y="690" fill="#7890a2" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">接入与场景层</text>
  {upstream_cards}
"""


def svg_flow_body(brief: dict[str, object]) -> str:
    steps = flow_steps_for(str(brief["title"]), str(brief["talk"]))
    nodes = "".join(svg_flow_node(112 + index * 238, 392, 188, 116, index + 1, step) for index, step in enumerate(steps[:6]))
    arrows = "".join(
        f'<path d="M {300 + index * 238} 450 L {338 + index * 238} 450" stroke="#2c7fb8" stroke-width="5" marker-end="url(#arrow)"/>'
        for index in range(min(len(steps), 6) - 1)
    )
    return f"""
  <defs>
    <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
      <path d="M 0 0 L 12 6 L 0 12 z" fill="#2c7fb8"/>
    </marker>
  </defs>
  <rect x="96" y="252" width="1408" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="305" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">业务闭环路径</text>
  <rect x="128" y="332" width="1344" height="50" rx="12" fill="#eaf3f5"/>
  {svg_text_lines(str(brief["talk"]), 154, 364, 78, 17, "#36556f", 18, 1)}
  {arrows}
  {nodes}
  <rect x="128" y="608" width="1344" height="78" rx="14" fill="#f7fbf8" stroke="#c8decf"/>
  <text x="154" y="640" fill="#2f855a" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="21" font-weight="700">闭环控制</text>
  <text x="154" y="672" fill="#36556f" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="19">自动处理与人工复核并行，接口不足时以流程自动化或定制开发兜底。</text>
"""


def svg_analysis_body(brief: dict[str, object]) -> str:
    reqs = list(brief["requirements"])[:4]
    caps = list(brief["capabilities"])[:4]
    left = "".join(svg_list_row(148, 336 + index * 70, item, "#eaf3f5", "#256bd8") for index, item in enumerate(reqs))
    right = "".join(svg_list_row(930, 336 + index * 70, item, "#edf6f1", "#2f855a") for index, item in enumerate(caps))
    return f"""
  <rect x="96" y="252" width="620" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <rect x="884" y="252" width="620" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <rect x="742" y="430" width="116" height="70" rx="35" fill="#153f73"/>
  <text x="776" y="474" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="30" font-weight="700">转化</text>
  <text x="136" y="305" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">需求与边界</text>
  <text x="924" y="305" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">方案能力落点</text>
  {left}
  {right}
  <rect x="136" y="656" width="1328" height="56" rx="12" fill="#fff8ea" stroke="#ead5a4"/>
  <text x="164" y="691" fill="#8a5c12" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">待确认事项保持显性，不把接口、数量、金额或系统状态写成既定事实。</text>
"""


def svg_matrix_body(brief: dict[str, object]) -> str:
    caps = list(brief["capabilities"])[:5]
    while len(caps) < 5:
        caps.append(["知识沉淀", "智能问答", "服务工单", "数据分析", "运营优化"][len(caps)])
    rows = "".join(svg_table_row(150, 342 + index * 62, cap, index) for index, cap in enumerate(caps))
    return f"""
  <rect x="96" y="252" width="1408" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="304" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">能力矩阵与汇报价值</text>
  <rect x="138" y="322" width="1324" height="54" rx="10" fill="#153f73"/>
  <text x="176" y="356" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">能力项</text>
  <text x="530" y="356" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">服务对象</text>
  <text x="860" y="356" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">表达重点</text>
  <text x="1220" y="356" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">边界</text>
  {rows}
  <rect x="138" y="674" width="1324" height="48" rx="10" fill="#eaf3f5"/>
  <text x="168" y="705" fill="#36556f" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">原则：讲价值、讲路径、讲边界，不编造无来源数字。</text>
"""


def svg_roadmap_body(brief: dict[str, object]) -> str:
    phases = ["需求调研", "高阶设计", "试点建设", "联调验收", "持续运营"]
    phase_cards = "".join(svg_timeline_phase(150 + index * 268, 406, phase, index) for index, phase in enumerate(phases))
    return f"""
  <rect x="96" y="252" width="1408" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="305" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">实施路径与审核闸口</text>
  <line x1="230" y1="466" x2="1370" y2="466" stroke="#2c7fb8" stroke-width="8" stroke-linecap="round"/>
  {phase_cards}
  <rect x="128" y="630" width="1344" height="72" rx="14" fill="#fff8ea" stroke="#ead5a4"/>
  <text x="158" y="662" fill="#8a5c12" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="20" font-weight="700">审核闸口</text>
  <text x="158" y="692" fill="#36556f" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18">每阶段输出可审阅文档和确认清单，未确认边界不进入确定性承诺。</text>
"""


def svg_closing_body(brief: dict[str, object]) -> str:
    pillars = ["统一数据资产", "智能感知场景", "流程闭环运营", "长期架构演进"]
    cards = "".join(svg_value_card(134 + index * 350, 330, pillar, index) for index, pillar in enumerate(pillars))
    return f"""
  <rect x="96" y="252" width="1408" height="504" rx="22" fill="#ffffff" stroke="#d5e2ec" filter="url(#softShadow)"/>
  <text x="128" y="305" fill="#153f73" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="25" font-weight="700">合作价值总结</text>
  {cards}
  <rect x="142" y="610" width="1316" height="84" rx="16" fill="#153f73"/>
  <text x="178" y="646" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="23" font-weight="700">汇报收束</text>
  {svg_text_lines(str(brief["talk"]), 178, 678, 72, 18, "#d7e9f7", 20, 1)}
"""


def svg_text_lines(
    text: str,
    x: int,
    y: int,
    max_chars: int,
    size: int,
    color: str,
    line_height: int,
    max_lines: int,
    weight: int = 400,
) -> str:
    lines = wrap_text(localize_prompt_terms(text), max_chars)[:max_lines]
    if len(wrap_text(localize_prompt_terms(text), max_chars)) > max_lines and lines:
        lines[-1] = lines[-1].rstrip("…") + "…"
    return "".join(
        f'<text x="{x}" y="{y + index * line_height}" fill="{color}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="{size}" font-weight="{weight}">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def svg_small_card(x: int, y: int, width: int, height: int, no: str, title: str, fill: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="16" fill="{fill}" stroke="#c9d9e8"/>
  <circle cx="{x + 38}" cy="{y + 40}" r="22" fill="#256bd8"/>
  <text x="{x + 25}" y="{y + 48}" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" font-weight="700">{no}</text>
  {svg_text_lines(title, x + 72, y + 38, 10, 18, "#17324d", 24, 3, weight=700)}
"""


def svg_pillar(x: int, y: int, width: int, height: int, title: str, subtitle: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="18" fill="#f8fbff" stroke="#d5e2ec"/>
  <rect x="{x}" y="{y}" width="{width}" height="12" rx="6" fill="#2c7fb8"/>
  {svg_text_lines(title, x + 24, y + 56, 12, 20, "#153f73", 26, 2, weight=700)}
  <text x="{x + 24}" y="{y + 124}" fill="#5f7485" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17">{escape(subtitle)}</text>
"""


def svg_module_box(x: int, y: int, width: int, height: int, title: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="14" fill="#eef6ff" stroke="#b8d0e6"/>
  {svg_text_lines(title, x + 22, y + 40, 12, 19, "#153f73", 23, 1, weight=700)}
"""


def svg_tag(x: int, y: int, text: str, fill: str, color: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="240" height="54" rx="27" fill="{fill}" stroke="#c9d9e8"/>
  {svg_text_lines(text, x + 26, y + 34, 10, 18, color, 20, 1, weight=700)}
"""


def flow_steps_for(title: str, talk: str) -> list[str]:
    text = title + talk
    if "差旅" in text or "后勤保障" in text:
        return ["员工入口", "AI理解", "任务拆解", "资源确认", "人工复核", "结果反馈"]
    if "安全" in text or "巡检" in text:
        return ["风险感知", "规则判断", "工单派发", "现场整改", "复核闭环", "数据沉淀"]
    return ["需求触发", "数据读取", "流程编排", "任务执行", "异常复核", "闭环反馈"]


def svg_flow_node(x: int, y: int, width: int, height: int, no: int, text: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="{width}" height="{height}" rx="18" fill="#f8fbff" stroke="#b8d0e6"/>
  <circle cx="{x + 34}" cy="{y + 34}" r="22" fill="#2c7fb8"/>
  <text x="{x + 27}" y="{y + 42}" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="18" font-weight="700">{no}</text>
  {svg_text_lines(text, x + 24, y + 84, 8, 20, "#153f73", 24, 2, weight=700)}
"""


def svg_list_row(x: int, y: int, text: str, fill: str, accent: str) -> str:
    return f"""
  <rect x="{x}" y="{y}" width="500" height="52" rx="12" fill="{fill}" stroke="#d5e2ec"/>
  <rect x="{x}" y="{y}" width="8" height="52" rx="4" fill="{accent}"/>
  {svg_text_lines(text, x + 28, y + 34, 22, 18, "#17324d", 20, 1, weight=700)}
"""


def svg_table_row(x: int, y: int, cap: str, index: int) -> str:
    fill = "#f8fbff" if index % 2 == 0 else "#eef6ff"
    return f"""
  <rect x="{x - 12}" y="{y}" width="1324" height="54" fill="{fill}" stroke="#ffffff"/>
  {svg_text_lines(cap, x + 20, y + 34, 16, 18, "#153f73", 20, 1, weight=700)}
  <text x="{x + 380}" y="{y + 34}" fill="#36556f" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17">业务/管理/服务对象</text>
  <text x="{x + 710}" y="{y + 34}" fill="#36556f" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17">价值、路径、风险边界</text>
  <text x="{x + 1070}" y="{y + 34}" fill="#8a5c12" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17">待确认</text>
"""


def svg_timeline_phase(x: int, y: int, title: str, index: int) -> str:
    return f"""
  <circle cx="{x + 70}" cy="{y + 60}" r="34" fill="#153f73"/>
  <text x="{x + 56}" y="{y + 70}" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="22" font-weight="700">{index + 1}</text>
  <rect x="{x}" y="{y + 108}" width="160" height="88" rx="14" fill="#eef6ff" stroke="#b8d0e6"/>
  {svg_text_lines(title, x + 26, y + 160, 6, 20, "#153f73", 22, 2, weight=700)}
"""


def svg_value_card(x: int, y: int, title: str, index: int) -> str:
    colors = ["#eef6ff", "#edf6f1", "#fff8ea", "#f5f7fb"]
    accents = ["#256bd8", "#2f855a", "#b7791f", "#153f73"]
    return f"""
  <rect x="{x}" y="{y}" width="300" height="214" rx="20" fill="{colors[index % len(colors)]}" stroke="#d5e2ec"/>
  <circle cx="{x + 52}" cy="{y + 54}" r="28" fill="{accents[index % len(accents)]}"/>
  <text x="{x + 43}" y="{y + 64}" fill="#ffffff" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="22" font-weight="700">{index + 1}</text>
  {svg_text_lines(title, x + 36, y + 118, 10, 23, "#153f73", 28, 2, weight=700)}
  <text x="{x + 36}" y="{y + 178}" fill="#5f7485" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="17">支撑长期演进</text>
"""


def extract_text_lines(text: str, max_lines: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-#0123456789. 、")
        if not line or line.startswith("用途：") or line.startswith("Asset type"):
            continue
        line = localize_prompt_terms(line)
        if not has_chinese(line):
            continue
        if len(line) > 54:
            line = line[:53] + "…"
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines or ["当前页内容等待进一步审阅。"]


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def wrap_text(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_chars:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def svg_wrapped_list(lines: list[str], x: int, y: int, color: str, size: int, max_chars: int, max_rows: int) -> str:
    rows: list[str] = []
    for line in lines:
        wrapped = wrap_text(line, max_chars)
        if wrapped:
            wrapped[0] = "• " + wrapped[0]
        rows.extend(wrapped)
        if len(rows) >= max_rows:
            break
    if len(rows) > max_rows:
        rows = rows[:max_rows]
    if rows and len(rows) == max_rows:
        rows[-1] = rows[-1].rstrip("…") + "…"
    return "".join(
        f'<text x="{x}" y="{y + index * (size + 10)}" fill="{color}" font-family="PingFang SC, Microsoft YaHei, sans-serif" font-size="{size}">{escape(row)}</text>'
        for index, row in enumerate(rows[:max_rows])
    )


def update_deck_page_script(job_id: str, page_id: str, content: str) -> DeckPage:
    job_dir, pages, page = find_deck_page(job_id, page_id)
    (job_dir / page.script_path).write_text(content.rstrip() + "\n", encoding="utf-8")
    page.script_state = "edited"
    page.prompt_state = "needs_regeneration"
    page.result_state = "stale"
    page.updated_at = utcish_now()
    write_page_index(job_dir, pages)
    write_logs(job_dir, f"P{page.page_no:02d} script edited. Prompt needs regeneration.\n", append=True)
    return page


def regenerate_deck_page_prompt(job_id: str, page_id: str) -> tuple[DeckPage, str]:
    job_dir, pages, page = find_deck_page(job_id, page_id)
    status = read_status(job_id)
    script = (job_dir / page.script_path).read_text(encoding="utf-8", errors="replace")
    truth_errors = validate_page_specific_truth(script)
    if truth_errors:
        page.prompt_state = "needs_regeneration"
        page.result_state = "stale"
        page.updated_at = utcish_now()
        write_page_index(job_dir, pages)
        raise HTTPException(status_code=409, detail="当前页缺少可执行的 Page-specific source of truth：" + "；".join(truth_errors))
    prompt = build_image_prompt(status, page.page_no, page.title, script)
    (job_dir / page.prompt_path).write_text(prompt, encoding="utf-8")
    page.prompt_state = "ready"
    page.result_state = "prompt_ready"
    page.updated_at = utcish_now()
    write_page_index(job_dir, pages)
    write_logs(job_dir, f"P{page.page_no:02d} prompt regenerated from edited script.\n", append=True)
    return page, prompt


def validate_page_specific_truth(script: str) -> list[str]:
    truth_body = extract_script_section(script, "Page-specific source of truth", ("页面设计 Brief", "讲稿", "审核备注"))
    if not truth_body:
        return ["请补写当前页设计真值"]
    required_truth_labels = ("页面目标", "版式要求", "图示结构", "必须出现的关键词", "上屏文字", "视觉注意", "事实与能力边界", "禁止事项")
    missing_labels = [label for label in required_truth_labels if label not in truth_body]
    truth_lines = [line for line in truth_body.splitlines() if line.strip().startswith("-")]
    errors: list[str] = []
    if missing_labels:
        errors.append("缺少字段：" + "、".join(missing_labels))
    if len(truth_body) < 320 or len(truth_lines) < 8:
        errors.append("内容过薄，请补充版式、节点、关键词、边界和视觉注意")
    return errors


def write_logs(job_dir: Path, text: str, append: bool = False) -> None:
    mode = "a" if append else "w"
    with (job_dir / "logs.txt").open(mode, encoding="utf-8") as handle:
        handle.write(text)


def read_logs(job_id: str) -> str:
    job_dir = get_job_dir(job_id)
    logs_path = job_dir / "logs.txt"
    return logs_path.read_text(encoding="utf-8") if logs_path.exists() else ""


def safe_output_file(job_id: str, filename: str) -> Path:
    job_dir = get_job_dir(job_id)
    safe_name = safe_job_path_name(filename)
    output_path = job_dir / "output" / safe_name
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    return output_path


def safe_artifact_file(job_id: str, relative_path: str) -> Path:
    job_dir = get_job_dir(job_id)
    safe_relative = Path(relative_path)
    if safe_relative.is_absolute() or ".." in safe_relative.parts:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    target = job_dir / safe_relative
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    resolved_job_dir = job_dir.resolve()
    if resolved_job_dir not in target.resolve().parents:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    return target
