from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from github_scan.task_scheduler import build_create_task_command, build_run_task_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Register the local github-account-scanner Windows scheduled task.")
    parser.add_argument("--task-name", default="github-account-scanner-monitor", help="Scheduled task name.")
    parser.add_argument("--interval-minutes", type=int, default=15, help="How often to run the monitor.")
    parser.add_argument("--run-now", action="store_true", help="Trigger the task immediately after registration.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    python_executable = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    runner_script = REPO_ROOT / "scripts" / "run_scheduled_monitor.py"

    if not python_executable.exists():
        raise SystemExit(f"Missing Python interpreter for the task: {python_executable}")
    if not runner_script.exists():
        raise SystemExit(f"Missing scheduled runner script: {runner_script}")

    start_time = (datetime.now() + timedelta(minutes=1)).strftime("%H:%M")
    create_command = build_create_task_command(
        task_name=args.task_name,
        python_executable=python_executable,
        runner_script=runner_script,
        interval_minutes=args.interval_minutes,
        start_time=start_time,
    )
    subprocess.run(create_command, check=True)
    print(f"Registered scheduled task '{args.task_name}' every {args.interval_minutes} minutes starting at {start_time}.")

    if args.run_now:
        subprocess.run(build_run_task_command(args.task_name), check=True)
        print(f"Triggered scheduled task '{args.task_name}'.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
