from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from .case_templates import SMART_LOGISTICS_SCRIPT_MD, build_requirement_reminders, load_smart_logistics_original_prompts
from .config import settings
from .codex_runner import codex_bridge_dir, codex_env
from .models import PipelineStatus
from .stage1_generator import generate_stage1_artifacts
from .storage import get_job_dir, read_status, update_status, write_logs, write_page_index, write_status


_worker_lock = asyncio.Lock()


async def run_job(job_id: str) -> None:
    if _worker_lock.locked():
        update_status(job_id, PipelineStatus.QUEUED)

    async with _worker_lock:
        job_dir = get_job_dir(job_id)
        update_status(job_id, PipelineStatus.RUNNING)
        if settings.worker_mode == "mock":
            await run_mock_pipeline(job_id, job_dir)
        else:
            await run_codex_pipeline(job_id, job_dir)


async def run_mock_pipeline(job_id: str, job_dir: Path) -> None:
    status = read_status(job_id)
    write_logs(job_dir, "Mock pipeline started.\n", append=True)

    update_status(job_id, PipelineStatus.REQUIREMENT_INTAKE)
    reminders = build_requirement_reminders(status)
    original_prompts = load_smart_logistics_original_prompts()
    (job_dir / "work" / "01_requirements" / "requirement-reminders.md").write_text(reminders, encoding="utf-8")
    (job_dir / "work" / "01_requirements" / "reference-smart-logistics-script.md").write_text(
        SMART_LOGISTICS_SCRIPT_MD,
        encoding="utf-8",
    )
    (job_dir / "work" / "01_requirements" / "reference-smart-logistics-original-prompts.md").write_text(
        original_prompts,
        encoding="utf-8",
    )
    pages = generate_stage1_artifacts(job_dir, status)
    write_page_index(job_dir, pages)

    update_status(job_id, PipelineStatus.IMAGE_PPT_GENERATION)
    (job_dir / "work" / "02_image_ppt" / "reference-smart-logistics-script.md").write_text(
        SMART_LOGISTICS_SCRIPT_MD,
        encoding="utf-8",
    )
    (job_dir / "work" / "02_image_ppt" / "reference-smart-logistics-original-prompts.md").write_text(
        original_prompts,
        encoding="utf-8",
    )
    (job_dir / "work" / "02_image_ppt" / "image-ppt-placeholder.md").write_text(
        "# 图片 PPT 阶段占位\n\n正式模式会在这里生成图片版 PPT、页面 PNG、prompt 和 handoff 包。\n",
        encoding="utf-8",
    )

    update_status(job_id, PipelineStatus.EDITABLE_REBUILD)
    (job_dir / "work" / "03_editable_rebuild" / "editable-rebuild-placeholder.md").write_text(
        "# 可编辑化阶段占位\n\n正式模式会在这里执行 ppt-image-rebuilder 严格门禁。\n",
        encoding="utf-8",
    )

    result = job_dir / "output" / "result.pptx"
    result.write_bytes(b"Mock PPTX placeholder. Switch PIPELINE_WORKER_MODE=codex for real generation.\n")
    (job_dir / "output" / "outline.md").write_text("# 大纲占位\n", encoding="utf-8")
    (job_dir / "output" / "qa-report.md").write_text("# QA 占位\n\nMock mode only.\n", encoding="utf-8")

    current = read_status(job_id)
    current.stage_artifacts = {
        "requirement_intake": [
            "work/01_requirements/01_requirements.md",
            "work/01_requirements/source-inventory.md",
            "work/01_requirements/facts.md",
            "work/01_requirements/open-questions.md",
            "work/01_requirements/requirement-reminders.md",
            "work/01_requirements/generation-mode.md",
            "work/01_requirements/page-index.json",
            *[page.script_path for page in pages],
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
        "image_ppt_generation": [
            *[page.prompt_path for page in pages],
            "work/02_image_ppt/reference-smart-logistics-script.md",
            "work/02_image_ppt/reference-smart-logistics-original-prompts.md",
            "work/02_image_ppt/image-ppt-placeholder.md",
        ],
        "editable_rebuild": ["work/03_editable_rebuild/editable-rebuild-placeholder.md"],
    }
    write_status(job_dir, current)
    update_status(job_id, PipelineStatus.DONE, output_file="result.pptx")
    write_logs(job_dir, "Mock pipeline finished.\n", append=True)


async def run_codex_pipeline(job_id: str, job_dir: Path) -> None:
    prompt = (job_dir / "prompt.md").read_text(encoding="utf-8")
    codex_cwd = codex_bridge_dir(job_dir)
    command = [
        settings.codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(codex_cwd),
        "-",
    ]
    write_logs(job_dir, f"Starting Codex command: {' '.join(command[:5])} <job_dir> -\n", append=True)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=codex_env(codex_cwd),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode("utf-8")),
            timeout=settings.worker_timeout_seconds,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        update_status(job_id, PipelineStatus.FAILED, error="Worker timeout")
        write_logs(job_dir, "Worker timeout.\n", append=True)
        return

    write_logs(job_dir, stdout.decode("utf-8", errors="replace"), append=True)
    write_logs(job_dir, stderr.decode("utf-8", errors="replace"), append=True)

    result = job_dir / "output" / "result.pptx"
    error = job_dir / "output" / "error.md"
    if result.exists():
        update_status(job_id, PipelineStatus.DONE, output_file="result.pptx")
    elif error.exists():
        update_status(job_id, PipelineStatus.NEEDS_HUMAN_REVIEW, error="Codex produced output/error.md")
    else:
        update_status(job_id, PipelineStatus.FAILED, error="result.pptx not found")
