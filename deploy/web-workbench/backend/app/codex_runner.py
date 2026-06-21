from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import settings


CODEX_BRIDGE_ROOT = Path("/tmp/ai-ppt-codex-jobs")


def codex_bridge_dir(job_dir: Path) -> Path:
    """Use an ASCII-only symlink path so Codex is not started under a Chinese cwd."""
    CODEX_BRIDGE_ROOT.mkdir(parents=True, exist_ok=True)
    bridge = CODEX_BRIDGE_ROOT / job_dir.name
    if bridge.is_symlink() or bridge.exists():
        if bridge.resolve() == job_dir.resolve():
            return bridge
        if bridge.is_dir() and not bridge.is_symlink():
            raise RuntimeError(f"Codex bridge path is an existing directory: {bridge}")
        bridge.unlink()
    bridge.symlink_to(job_dir.resolve(), target_is_directory=True)
    return bridge


def codex_env(cwd: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    drop_keys = {
        "_",
        "OLDPWD",
        "PWD",
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "VIRTUAL_ENV_PROMPT",
    }
    for key, value in os.environ.items():
        if key in drop_keys:
            continue
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            continue
        if "/Documents/解决方案部" in value or "/backend/.venv" in value or "uvicorn" in value:
            continue
        env[key] = value
    safe_path_parts = [
        str(Path.home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        "/Applications/Codex.app/Contents/Resources",
    ]
    env["PATH"] = ":".join(safe_path_parts)
    env["PWD"] = str(cwd)
    return env


def run_codex_in_job(job_dir: Path, prompt: str, *, timeout: int | None = None) -> tuple[int, str, str, list[str]]:
    """Run Codex inside one job directory with a fixed argument list."""
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
    result = subprocess.run(
        command,
        input=prompt,
        capture_output=True,
        text=True,
        env=codex_env(codex_cwd),
        timeout=timeout or settings.worker_timeout_seconds,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr, command
