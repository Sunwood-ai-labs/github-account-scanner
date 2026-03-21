from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from github_scan.discord_webhook import (
    DiscordNotificationError,
    build_discord_dry_run_text,
    build_discord_payload,
    load_report as load_discord_report,
    post_to_discord,
    post_via_discord_bot,
)
from github_scan.monitor import (
    GitHubApiError,
    GitHubClient,
    build_report_document,
    compare_snapshots,
    load_snapshot,
    save_snapshot,
    write_markdown_report,
    write_report_json,
)


def _default_state_file(account: str) -> Path:
    return Path("state") / f"{account.lower()}.json"


def _load_local_env_files() -> None:
    for path in (Path(".env"), Path(".env.local")):
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor a GitHub account for new repositories and releases.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="Fetch the latest account snapshot and compare it with saved state.")
    check_parser.add_argument("account", help="GitHub user or organization login.")
    check_parser.add_argument(
        "--state-file",
        type=Path,
        help="Where the last known snapshot is stored. Defaults to state/<account>.json.",
    )
    check_parser.add_argument("--json-report", type=Path, help="Optional JSON output path for the latest report.")
    check_parser.add_argument(
        "--markdown-report",
        type=Path,
        help="Optional Markdown output path for the latest report.",
    )
    check_parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
        help="GitHub token. Defaults to GITHUB_TOKEN or GH_TOKEN from the environment.",
    )
    check_parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout per request.")
    check_parser.add_argument(
        "--request-pause-seconds",
        type=float,
        default=0.0,
        help="Optional pause after each release request to reduce API pressure.",
    )

    discord_parser = subparsers.add_parser("notify-discord", help="Send a scan report to a Discord webhook.")
    discord_parser.add_argument(
        "--report-file",
        type=Path,
        required=True,
        help="JSON report created by the check command.",
    )
    discord_parser.add_argument(
        "--webhook-url",
        default=os.getenv("DISCORD_WEBHOOK_URL"),
        help="Discord webhook URL. Defaults to DISCORD_WEBHOOK_URL from the environment.",
    )
    discord_parser.add_argument(
        "--bot-token",
        default=os.getenv("DISCORD_BOT_TOKEN"),
        help="Discord bot token. Defaults to DISCORD_BOT_TOKEN from the environment.",
    )
    discord_parser.add_argument(
        "--channel-id",
        default=os.getenv("DISCORD_CHANNEL_ID"),
        help="Discord channel ID used as the parent channel for thread creation.",
    )
    discord_parser.add_argument(
        "--max-items",
        type=int,
        default=5,
        help="Maximum number of repositories or releases to include in the Discord message.",
    )
    discord_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the Discord message instead of sending it.",
    )
    return parser


def _print_summary(report: dict[str, object]) -> None:
    stats = report["statistics"]
    account = report["account"]
    assert isinstance(stats, dict)
    assert isinstance(account, dict)
    print(f"Checked {account['login']} ({account['type']}) at {report['checked_at']}")
    print(f"API requests: {stats['request_count']}")
    print(f"Token used: {'yes' if stats['token_used'] else 'no'}")

    if report["bootstrap"]:
        print("Created initial baseline snapshot.")
        return

    print(f"New repositories: {stats['new_repository_count']}")
    print(f"New releases: {stats['new_release_count']}")
    if not report["changed"]:
        print("No changes detected.")
        return

    new_repositories = report["new_repositories"]
    new_releases = report["new_releases"]
    assert isinstance(new_repositories, list)
    assert isinstance(new_releases, list)
    for repo in new_repositories:
        print(f"[repo] {repo['full_name']} ({repo['created_at']})")
    for item in new_releases:
        release = item["release"]
        repo = item["repository"]
        published = release["published_at"] or release["created_at"] or "unknown"
        print(f"[release] {repo['full_name']} {release['tag_name']} ({published})")


def run_check(args: argparse.Namespace) -> int:
    state_file = args.state_file or _default_state_file(args.account)
    previous = load_snapshot(state_file)
    client = GitHubClient(
        token=args.token,
        timeout=args.timeout_seconds,
        request_pause_seconds=args.request_pause_seconds,
    )
    current = client.fetch_snapshot(args.account)
    comparison = compare_snapshots(previous, current)
    report = build_report_document(
        comparison,
        request_count=client.request_count,
        token_used=bool(args.token),
        rate_limit=client.rate_limit,
    )

    save_snapshot(state_file, current)
    if args.json_report:
        write_report_json(args.json_report, report)
    if args.markdown_report:
        write_markdown_report(args.markdown_report, report)

    _print_summary(report)
    return 0


def run_notify_discord(args: argparse.Namespace) -> int:
    report = load_discord_report(args.report_file)
    payload = build_discord_payload(report, max_items=args.max_items)

    if args.dry_run:
        print(build_discord_dry_run_text(report, max_items=args.max_items))
        return 0

    if args.bot_token and args.channel_id:
        result = post_via_discord_bot(args.bot_token, args.channel_id, report, payload)
        print(f"Discord thread notification sent. thread_id={result['thread_id']}")
        return 0

    if args.webhook_url:
        post_to_discord(args.webhook_url, payload)
        print("Discord webhook notification sent.")
        return 0

    print(
        "DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID, or DISCORD_WEBHOOK_URL, must be set.",
        file=sys.stderr,
    )
    return 1


def main() -> int:
    _load_local_env_files()
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "check":
            return run_check(args)
        if args.command == "notify-discord":
            return run_notify_discord(args)
        parser.error(f"Unsupported command: {args.command}")
    except GitHubApiError as error:
        print(str(error), file=sys.stderr)
        return 1
    except DiscordNotificationError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
