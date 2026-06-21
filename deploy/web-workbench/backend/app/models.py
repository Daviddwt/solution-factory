from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PipelineStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    REQUIREMENT_INTAKE = "requirement_intake"
    IMAGE_PPT_GENERATION = "image_ppt_generation"
    EDITABLE_REBUILD = "editable_rebuild"
    DONE = "done"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class JobCreate(BaseModel):
    workspace_id: str = "david"
    requester_name: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=120)
    pages: int | None = Field(default=None, ge=1, le=80)
    scenario: str = ""
    scenario_prompt: str = ""
    audience: str = ""
    audience_prompt: str = ""
    style: str = "解决方案风"
    style_prompt: str = ""
    custom_style_prompt: str = ""
    user_instruction: str = ""
    notify_target: str = ""


class UploadedFileInfo(BaseModel):
    filename: str
    stored_name: str
    size_bytes: int


class JobStatus(BaseModel):
    job_id: str
    workspace_id: str = "david"
    requester_name: str = "未登记"
    job_type: str = "ai_ppt_pipeline"
    status: PipelineStatus
    title: str
    pages: int | None = None
    scenario: str = ""
    scenario_prompt: str = ""
    audience: str = ""
    audience_prompt: str = ""
    style: str = "解决方案风"
    style_prompt: str = ""
    custom_style_prompt: str = ""
    user_instruction: str = ""
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    output_file: str | None = None
    notify_target: str = ""
    notify_sent_at: str | None = None
    notify_error: str | None = None
    uploaded_files: list[UploadedFileInfo] = Field(default_factory=list)
    stage_artifacts: dict[str, list[str]] = Field(default_factory=dict)

    @classmethod
    def new(cls, job_id: str, payload: JobCreate, uploaded_files: list[UploadedFileInfo]) -> "JobStatus":
        now = datetime.now().isoformat(timespec="seconds")
        return cls(
            job_id=job_id,
            workspace_id=safe_job_path_name(payload.workspace_id or "david"),
            requester_name=payload.requester_name or "Operator",
            status=PipelineStatus.CREATED,
            title=payload.title,
            pages=payload.pages,
            scenario=payload.scenario,
            scenario_prompt=payload.scenario_prompt,
            audience=payload.audience,
            audience_prompt=payload.audience_prompt,
            style=payload.style,
            style_prompt=payload.style_prompt,
            custom_style_prompt=payload.custom_style_prompt,
            user_instruction=payload.user_instruction,
            notify_target=payload.notify_target,
            created_at=now,
            updated_at=now,
            uploaded_files=uploaded_files,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        allowed_artifacts = {
            "requirement_intake",
            "script_prompts",
            "script_package",
            "script_markdown",
            "prompt_markdown",
            "ppt_script_reference",
            "original_prompt_reference",
        }
        data["stage_artifacts"] = {
            key: value for key, value in data.get("stage_artifacts", {}).items() if key in allowed_artifacts
        }
        return data


class JobSummary(BaseModel):
    job_id: str
    workspace_id: str
    requester_name: str
    status: PipelineStatus
    title: str
    created_at: str
    updated_at: str
    output_file: str | None = None


class DeckPage(BaseModel):
    page_id: str
    page_no: int
    title: str
    script_path: str
    prompt_path: str
    result_path: str
    script_state: str = "draft"
    prompt_state: str = "ready"
    result_state: str = "not_started"
    updated_at: str


class PageScriptUpdate(BaseModel):
    content: str = Field(min_length=1)


class IntakePromptUpdate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class KnowledgeBaseContentUpdate(BaseModel):
    content: str = Field(max_length=500_000)


def utcish_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_job_path_name(value: str) -> str:
    return Path(value).name.replace("/", "_").replace("\\", "_")
