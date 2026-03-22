from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
import traceback


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from github_scan.scheduler import (
    collect_report,
    load_env_files,
    send_report_to_discord,
    should_notify_with_filters,
)


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the GitHub account monitor once and notify Discord on changes.")
    parser.add_argument("--account", default="Sunwood-ai-labs", help="GitHub account to monitor.")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("state") / "sunwood-ai-labs.json",
        help="Snapshot file path.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=Path("state") / "last-report.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=Path("state") / "last-report.md",
        help="Markdown report output path.",
    )
    parser.add_argument("--max-items", type=int, default=5, help="Max items to include in Discord notifications.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout per request.")
    parser.add_argument(
        "--request-pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause between release requests.",
    )
    parser.add_argument(
        "--notify-on-bootstrap",
        action="store_true",
        help="Also send a Discord notification on the first baseline run.",
    )
    parser.add_argument(
        "--dry-run-notify",
        action="store_true",
        help="Render the Discord payload instead of sending it.",
    )
    parser.add_argument(
        "--notify-releases-only",
        action=argparse.BooleanOptionalAction,
        default=_env_flag("DISCORD_NOTIFY_RELEASES_ONLY", default=False),
        help="Only send Discord notifications when the report contains new releases.",
    )
    parser.add_argument(
        "--discord-profile",
        choices=("production", "test"),
        default=os.getenv("DISCORD_PROFILE", "production"),
        help="Discord delivery profile. Test mode does not inherit production mentions.",
    )
    return parser


def append_log(lines: list[str]) -> None:
    log_dir = REPO_ROOT / "logs" / "scheduled-monitor"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    with log_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def main() -> int:
    os.chdir(REPO_ROOT)
    load_env_files((REPO_ROOT / ".env", REPO_ROOT / ".env.local"))
    args = build_parser().parse_args()
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

    try:
        report = collect_report(
            account=args.account,
            state_file=args.state_file,
            json_report=args.json_report,
            markdown_report=args.markdown_report,
            timeout_seconds=args.timeout_seconds,
            request_pause_seconds=args.request_pause_seconds,
        )

        stats = report["statistics"]
        lines = [
            f"[{timestamp}] check account={report['account']['login']} bootstrap={report['bootstrap']} changed={report['changed']}",
            f"  repos={stats['new_repository_count']} releases={stats['new_release_count']} requests={stats['request_count']}",
        ]

        if should_notify_with_filters(
            report,
            notify_on_bootstrap=args.notify_on_bootstrap,
            release_only=args.notify_releases_only,
            release_count=int(stats["new_release_count"]),
        ):
            result = send_report_to_discord(
                report,
                profile=args.discord_profile,
                max_items=args.max_items,
                dry_run=args.dry_run_notify,
            )
            if result["mode"] == "bot":
                lines.append(f"  notify=bot thread_id={result['thread_id']}")
            elif result["mode"] == "webhook":
                lines.append("  notify=webhook")
            else:
                lines.append("  notify=dry-run")
        else:
            lines.append("  notify=skipped")
        lines.append(f"  notify_releases_only={args.notify_releases_only}")
        lines.append(f"  discord_profile={args.discord_profile}")

        append_log(lines)
        for line in lines:
            print(line)
        return 0
    except Exception as error:  # noqa: BLE001
        lines = [
            f"[{timestamp}] error={error}",
            traceback.format_exc().rstrip(),
        ]
        append_log(lines)
        for line in lines:
            print(line, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
