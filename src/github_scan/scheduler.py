from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from github_scan.discord_webhook import (
    DiscordNotificationError,
    build_discord_dry_run_text,
    build_discord_payload,
    post_to_discord,
    post_via_discord_bot,
)
from github_scan.monitor import (
    GitHubClient,
    build_report_document,
    compare_snapshots,
    load_snapshot,
    save_snapshot,
    write_markdown_report,
    write_report_json,
)


def load_env_files(paths: tuple[Path, ...], *, environ: dict[str, str] | None = None) -> None:
    target = environ if environ is not None else os.environ
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in target:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            target[key] = value


def collect_report(
    *,
    account: str,
    state_file: Path,
    json_report: Path,
    markdown_report: Path,
    token: str | None = None,
    timeout_seconds: float = 30.0,
    request_pause_seconds: float = 0.0,
) -> dict[str, Any]:
    previous = load_snapshot(state_file)
    client = GitHubClient(
        token=token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
        timeout=timeout_seconds,
        request_pause_seconds=request_pause_seconds,
    )
    current = client.fetch_snapshot(account)
    comparison = compare_snapshots(previous, current)
    report = build_report_document(
        comparison,
        request_count=client.request_count,
        token_used=bool(client.token),
        rate_limit=client.rate_limit,
    )

    save_snapshot(state_file, current)
    write_report_json(json_report, report)
    write_markdown_report(markdown_report, report)
    return report


def should_notify(report: dict[str, Any], *, notify_on_bootstrap: bool = False) -> bool:
    if report.get("changed"):
        return True
    if notify_on_bootstrap and report.get("bootstrap"):
        return True
    return False


def send_report_to_discord(
    report: dict[str, Any],
    *,
    max_items: int = 5,
    dry_run: bool = False,
    webhook_url: str | None = None,
    bot_token: str | None = None,
    channel_id: str | None = None,
    mention_user_id: str | None = None,
) -> dict[str, Any]:
    payload = build_discord_payload(report, max_items=max_items)

    if dry_run:
        return {
            "mode": "dry-run",
            "preview": build_discord_dry_run_text(report, max_items=max_items),
        }

    resolved_bot_token = bot_token or os.getenv("DISCORD_BOT_TOKEN")
    resolved_channel_id = channel_id or os.getenv("DISCORD_CHANNEL_ID")
    resolved_webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    resolved_mention_user_id = mention_user_id or os.getenv("DISCORD_EXPLAINER_USER_ID")

    if resolved_bot_token and resolved_channel_id:
        result = post_via_discord_bot(
            resolved_bot_token,
            resolved_channel_id,
            report,
            payload,
            mention_user_id=resolved_mention_user_id,
        )
        result["mode"] = "bot"
        return result

    if resolved_webhook_url:
        post_to_discord(resolved_webhook_url, payload)
        return {"mode": "webhook"}

    raise DiscordNotificationError(
        "DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID, or DISCORD_WEBHOOK_URL, must be set."
    )
