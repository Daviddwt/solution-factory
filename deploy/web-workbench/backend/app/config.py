from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = REPO_DIR / "storage"
JOBS_DIR = STORAGE_DIR / "jobs"
WORKSPACES_DIR = STORAGE_DIR / "workspaces"
PRESETS_DIR = STORAGE_DIR / "presets"
KNOWLEDGE_BASE_DIR = STORAGE_DIR / "knowledge_base"
PROMPT_TEMPLATE = REPO_DIR / "prompts" / "AI_PPT_PIPELINE_WORKER_PROMPT.md"


@dataclass(slots=True)
class Settings:
    app_name: str = "解决方案部 PPT 脚本生产台"
    worker_mode: str = os.getenv("PIPELINE_WORKER_MODE", "codex")
    worker_timeout_seconds: int = int(os.getenv("PIPELINE_WORKER_TIMEOUT_SECONDS", "1200"))
    codex_bin: str = os.getenv("CODEX_BIN", "codex")
    hermes_bin: str = os.getenv("HERMES_BIN", "hermes")
    hermes_model: str = os.getenv("HERMES_MODEL", "")
    hermes_provider: str = os.getenv("HERMES_PROVIDER", "")
    hermes_toolsets: str = os.getenv("HERMES_TOOLSETS", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:3000").rstrip("/")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(",")
        if origin.strip()
    )
    allowed_extensions: tuple[str, ...] = (
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
    )


settings = Settings()


def ensure_directories() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
