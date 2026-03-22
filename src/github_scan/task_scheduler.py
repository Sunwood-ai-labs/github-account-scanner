from __future__ import annotations

from pathlib import Path


def build_create_task_command(
    *,
    task_name: str,
    python_executable: Path,
    runner_script: Path,
    interval_minutes: int,
    start_time: str,
) -> list[str]:
    if interval_minutes < 1:
        raise ValueError("interval_minutes must be at least 1")

    task_command = f'"{python_executable}" "{runner_script}"'
    return [
        "schtasks",
        "/Create",
        "/SC",
        "MINUTE",
        "/MO",
        str(interval_minutes),
        "/ST",
        start_time,
        "/TN",
        task_name,
        "/TR",
        task_command,
        "/F",
    ]


def build_run_task_command(task_name: str) -> list[str]:
    return ["schtasks", "/Run", "/TN", task_name]
