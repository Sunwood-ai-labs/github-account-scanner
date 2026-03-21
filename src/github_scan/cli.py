from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "check":
            return run_check(args)
        parser.error(f"Unsupported command: {args.command}")
    except GitHubApiError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
