from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .config import settings


HERMES_BRIDGE_ROOT = Path("/tmp/ai-ppt-hermes-jobs")


def hermes_bridge_dir(job_dir: Path) -> Path:
    """Use an ASCII-only symlink path so Hermes is not started under a Chinese cwd."""
    HERMES_BRIDGE_ROOT.mkdir(parents=True, exist_ok=True)
    bridge = HERMES_BRIDGE_ROOT / job_dir.name
    if bridge.is_symlink() or bridge.exists():
        if bridge.resolve() == job_dir.resolve():
            return bridge
        if bridge.is_dir() and not bridge.is_symlink():
            raise RuntimeError(f"Hermes bridge path is an existing directory: {bridge}")
        bridge.unlink()
    bridge.symlink_to(job_dir.resolve(), target_is_directory=True)
    return bridge


def hermes_env(cwd: Path) -> dict[str, str]:
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
        "/home/ganwei/.local/bin",
        "/home/ganwei/.hermes/hermes-agent/venv/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    existing_path = env.get("PATH", "")
    if existing_path:
        safe_path_parts.append(existing_path)
    env["PATH"] = ":".join(dict.fromkeys(part for part in safe_path_parts if part))
    env["PWD"] = str(cwd)
    return env


def run_hermes_oneshot(job_dir: Path, prompt: str, *, timeout: int | None = None) -> tuple[int, str, str, list[str]]:
    """Run Hermes in one-shot mode with a fixed argument list."""
    hermes_cwd = hermes_bridge_dir(job_dir)
    command = [settings.hermes_bin, "--ignore-rules", "-z", prompt]
    if settings.hermes_model:
        command.extend(["--model", settings.hermes_model])
    if settings.hermes_provider:
        command.extend(["--provider", settings.hermes_provider])
    if settings.hermes_toolsets.strip():
        command.extend(["--toolsets", settings.hermes_toolsets.strip()])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=hermes_cwd,
        env=hermes_env(hermes_cwd),
        timeout=timeout or settings.worker_timeout_seconds,
        check=False,
    )
    redacted_command = [settings.hermes_bin, "--ignore-rules", "-z", "<prompt>"]
    if settings.hermes_toolsets.strip():
        redacted_command.extend(["--toolsets", settings.hermes_toolsets.strip()])
    if settings.hermes_model:
        redacted_command.extend(["--model", settings.hermes_model])
    if settings.hermes_provider:
        redacted_command.extend(["--provider", settings.hermes_provider])
    return result.returncode, result.stdout, result.stderr, redacted_command


def validate_hermes_target(target: str) -> str:
    value = target.strip()
    if not value:
        return ""
    if not re.fullmatch(r"wecom:[A-Za-z0-9_-]{8,80}(?::[A-Za-z0-9_-]{8,80})?", value):
        raise ValueError("Unsupported Hermes notification target")
    return value


def send_hermes_message(target: str, message: str, *, timeout: int = 60) -> tuple[int, str, str, list[str]]:
    safe_target = validate_hermes_target(target)
    if not safe_target:
        return 0, "", "", []
    command = [settings.hermes_bin, "send", "--to", safe_target, message]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=hermes_env(Path.cwd()),
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr, [settings.hermes_bin, "send", "--to", safe_target, "<message>"]
