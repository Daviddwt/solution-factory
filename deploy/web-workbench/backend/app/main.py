from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response

from .config import ensure_directories, settings
from .intake_presets import read_intake_presets, update_intake_prompt
from .knowledge_base import (
    delete_knowledge_base_item,
    generate_knowledge_base_digest,
    list_knowledge_base_items,
    mark_knowledge_base_digest_failed,
    mark_knowledge_base_digest_running,
    read_knowledge_base_digest,
    read_knowledge_base_content,
    safe_knowledge_base_path,
    write_knowledge_base_content,
)
from .models import IntakePromptUpdate, JobCreate, KnowledgeBaseContentUpdate, PageScriptUpdate, PipelineStatus
from .presets import STYLE_PRESETS, default_style_prompt
from .storage import (
    build_script_markdown,
    build_script_package,
    build_prompt_markdown,
    create_job,
    generate_codex_stage1_artifacts,
    generation_provider_label,
    list_jobs,
    read_deck_page_content,
    read_deck_pages,
    read_logs,
    read_status,
    regenerate_deck_page_prompt,
    safe_artifact_file,
    safe_output_file,
    update_status,
    update_deck_page_script,
)
from .worker import run_job


ensure_directories()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    provider_label = generation_provider_label()
    return {
        "app_name": settings.app_name,
        "worker_mode": settings.worker_mode,
        "ai_engine": {
            "owner": provider_label.lower(),
            "mode": settings.worker_mode,
            "requires_user_model_key": False,
            "note": f"当前通过 {provider_label} 生成 PPT 生产脚本和逐页图片生产提示词；图片生成服务未接入。",
        },
        "image_ppt_executor": {
            "connected": False,
            "mode": "not_connected",
            "reason": "第一版已收敛为脚本生产台，不提供图片生成、HTML 截图或本地渲染替代路径。",
            "built_in_imagegen": False,
        },
        "knowledge_base": {
            "connected": True,
            "items": len(list_knowledge_base_items()),
        },
    }


@app.get("/api/styles")
async def get_styles() -> dict:
    return {"styles": STYLE_PRESETS}


@app.post("/api/jobs")
async def create_pipeline_job(
    background_tasks: BackgroundTasks,
    requester_name: str = Form(...),
    title: str = Form(...),
    pages: str = Form(default=""),
    scenario: str = Form(default=""),
    scenario_prompt: str = Form(default=""),
    audience: str = Form(default=""),
    audience_prompt: str = Form(default=""),
    style: str = Form(default="解决方案风"),
    style_prompt: str = Form(default=""),
    custom_style_prompt: str = Form(default=""),
    user_instruction: str = Form(default=""),
    source_text: str = Form(default=""),
    notify_target: str = Form(default=""),
    auto_run: bool = Form(default=False),
    files: list[UploadFile] | None = File(default=None),
) -> dict:
    pages_value = int(pages) if str(pages).strip() else None
    payload = JobCreate(
        workspace_id="",
        requester_name=requester_name,
        title=title,
        pages=pages_value,
        scenario=scenario,
        scenario_prompt=scenario_prompt,
        audience=audience,
        audience_prompt=audience_prompt,
        style=style,
        style_prompt=style_prompt or default_style_prompt(style),
        custom_style_prompt=custom_style_prompt,
        user_instruction=user_instruction,
        notify_target=notify_target,
    )
    job = await create_job(payload, files or [], source_text=source_text)
    if auto_run:
        background_tasks.add_task(run_job, job.job_id)
    return job.to_safe_dict()


@app.get("/api/jobs")
async def get_jobs(workspace_id: str | None = None) -> dict:
    return {"jobs": [job.model_dump(mode="json") for job in list_jobs(workspace_id=workspace_id)]}


@app.get("/api/intake-presets")
async def get_intake_presets() -> dict:
    return read_intake_presets()


@app.get("/api/knowledge-base")
async def get_knowledge_base() -> dict:
    return {"items": list_knowledge_base_items()}


@app.get("/api/knowledge-base/digest")
async def get_knowledge_base_digest() -> dict:
    return {"digest": read_knowledge_base_digest()}


def run_knowledge_base_digest_background() -> None:
    try:
        generate_knowledge_base_digest()
    except Exception as exc:
        mark_knowledge_base_digest_failed(str(exc))


@app.post("/api/knowledge-base/digest")
async def post_knowledge_base_digest(background_tasks: BackgroundTasks) -> dict:
    current = read_knowledge_base_digest()
    if current.get("processing"):
        return {"accepted": True, "digest": current}
    mark_knowledge_base_digest_running()
    background_tasks.add_task(run_knowledge_base_digest_background)
    return {"accepted": True, "digest": read_knowledge_base_digest()}


@app.post("/api/knowledge-base/upload")
async def post_knowledge_base_upload(files: list[UploadFile] = File(...)) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        filename = upload.filename or ""
        try:
            target = safe_knowledge_base_path(filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if target.suffix.lower() not in settings.allowed_extensions:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {target.suffix}")

        size = 0
        with target.open("wb") as buffer:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    buffer.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"Uploaded file is too large. Maximum: {settings.max_upload_mb} MB")
                buffer.write(chunk)

    return {"items": list_knowledge_base_items()}


@app.get("/api/knowledge-base/{name}/content", response_class=PlainTextResponse)
async def get_knowledge_base_content(name: str) -> str:
    try:
        return read_knowledge_base_content(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge base file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/knowledge-base/{name}/content")
async def put_knowledge_base_content(name: str, payload: KnowledgeBaseContentUpdate) -> dict:
    try:
        item = write_knowledge_base_content(name, payload.content)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge base file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item, "items": list_knowledge_base_items()}


@app.delete("/api/knowledge-base/{name}")
async def delete_knowledge_base_file(name: str) -> dict:
    try:
        delete_knowledge_base_item(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Knowledge base file not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": list_knowledge_base_items()}


@app.put("/api/intake-presets/{kind}/{preset_id}")
async def put_intake_preset(kind: str, preset_id: str, payload: IntakePromptUpdate) -> dict:
    if kind not in {"scenario", "audience"}:
        raise HTTPException(status_code=400, detail="Invalid preset kind")
    return {"preset": update_intake_prompt(kind, preset_id, payload.prompt)}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    return read_status(job_id).to_safe_dict()


@app.get("/api/jobs/{job_id}/logs", response_class=PlainTextResponse)
async def get_job_logs(job_id: str) -> str:
    return read_logs(job_id)


@app.get("/api/jobs/{job_id}/artifact", response_class=PlainTextResponse)
async def get_job_artifact(job_id: str, path: str = "work/01_requirements/requirement-reminders.md") -> str:
    artifact = safe_artifact_file(job_id, path)
    return artifact.read_text(encoding="utf-8", errors="replace")


@app.get("/api/jobs/{job_id}/pages")
async def get_job_pages(job_id: str) -> dict:
    return {"pages": [page.model_dump(mode="json") for page in read_deck_pages(job_id)]}


def run_codex_stage1_background(job_id: str) -> None:
    provider_label = generation_provider_label()
    try:
        generate_codex_stage1_artifacts(job_id)
    except HTTPException:
        pass
    except Exception as exc:
        update_status(job_id, PipelineStatus.FAILED, error=f"{provider_label} 生成逐页脚本异常：{exc}")


@app.post("/api/jobs/{job_id}/codex-stage1")
async def post_job_codex_stage1(job_id: str, background_tasks: BackgroundTasks) -> dict:
    provider_label = generation_provider_label()
    status = read_status(job_id)
    if status.status == PipelineStatus.REQUIREMENT_INTAKE:
        return {
            "accepted": True,
            "status": status.status,
            "note": f"{provider_label} 正在生成逐页 PPT 生产脚本。页面会自动刷新状态，你也可以稍后回来查看结果。",
        }
    update_status(job_id, PipelineStatus.REQUIREMENT_INTAKE, error=None)
    background_tasks.add_task(run_codex_stage1_background, job_id)
    return {
        "accepted": True,
        "status": PipelineStatus.REQUIREMENT_INTAKE,
        "note": f"已提交给 {provider_label} 后台生成。页面会自动刷新，生成完成后可审阅并下载 Markdown 脚本。",
    }


@app.get("/api/jobs/{job_id}/pages/{page_id}/content", response_class=PlainTextResponse)
async def get_job_page_content(job_id: str, page_id: str, kind: str = "script") -> str:
    return read_deck_page_content(job_id, page_id, kind)


@app.put("/api/jobs/{job_id}/pages/{page_id}/script")
async def put_job_page_script(job_id: str, page_id: str, payload: PageScriptUpdate) -> dict:
    page = update_deck_page_script(job_id, page_id, payload.content)
    return {"page": page.model_dump(mode="json")}


@app.post("/api/jobs/{job_id}/pages/{page_id}/regenerate-prompt")
async def post_job_page_prompt(job_id: str, page_id: str) -> dict:
    page, prompt = regenerate_deck_page_prompt(job_id, page_id)
    return {"page": page.model_dump(mode="json"), "prompt": prompt}


@app.post("/api/jobs/{job_id}/image-ppt-package")
async def post_job_image_ppt_package(job_id: str) -> dict:
    raise HTTPException(status_code=501, detail="第一版只生成 PPT 生产脚本；图片版 PPT 打包服务未接入。")


@app.post("/api/jobs/{job_id}/script-package")
async def post_job_script_package(job_id: str) -> dict:
    return build_script_package(job_id)


@app.post("/api/jobs/{job_id}/script-markdown")
async def post_job_script_markdown(job_id: str) -> dict:
    return build_script_markdown(job_id)


@app.post("/api/jobs/{job_id}/prompt-markdown")
async def post_job_prompt_markdown(job_id: str) -> dict:
    return build_prompt_markdown(job_id)


@app.post("/api/jobs/{job_id}/image-ppt-generation/start")
async def post_job_image_ppt_generation_start(job_id: str, background_tasks: BackgroundTasks) -> dict:
    read_status(job_id)
    raise HTTPException(status_code=501, detail="第一版只生成 PPT 生产脚本；图片生成服务未接入。")


@app.get("/api/jobs/{job_id}/pages/{page_id}/image")
async def get_job_page_image(job_id: str, page_id: str) -> Response:
    read_status(job_id)
    raise HTTPException(status_code=501, detail="第一版不提供图片预览；请查看页面脚本和图片生产提示词。")


@app.post("/api/jobs/{job_id}/run")
async def run_pipeline_job(job_id: str, background_tasks: BackgroundTasks) -> dict:
    read_status(job_id)
    background_tasks.add_task(run_job, job_id)
    return {"job_id": job_id, "accepted": True}


@app.get("/api/jobs/{job_id}/download")
async def download_job_output(job_id: str, filename: str = "result.pptx") -> FileResponse:
    output = safe_output_file(job_id, filename)
    if output.name not in {"script-package.zip", "ppt-script.md", "image-production-prompts.md"}:
        raise HTTPException(status_code=400, detail="第一版只开放页面脚本、图片生产提示词和完整脚本包下载。")
    return FileResponse(output, filename=output.name)
