from __future__ import annotations

from collections.abc import Mapping
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


def _clean_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate or None


def resolve_discord_delivery_config(
    *,
    profile: str = "production",
    webhook_url: str | None = None,
    bot_token: str | None = None,
    channel_id: str | None = None,
    mention_user_id: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    source = environ if environ is not None else os.environ
    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"production", "test"}:
        raise DiscordNotificationError(
            "Discord profile must be either 'production' or 'test'."
        )

    def env(name: str) -> str | None:
        return _clean_optional_value(source.get(name))

    explicit_webhook = _clean_optional_value(webhook_url)
    explicit_bot_token = _clean_optional_value(bot_token)
    explicit_channel_id = _clean_optional_value(channel_id)
    explicit_mention_user_id = _clean_optional_value(mention_user_id)

    if normalized_profile == "production":
        resolved = {
            "profile": normalized_profile,
            "webhook_url": explicit_webhook or env("DISCORD_PRODUCTION_WEBHOOK_URL") or env("DISCORD_WEBHOOK_URL"),
            "bot_token": explicit_bot_token or env("DISCORD_PRODUCTION_BOT_TOKEN") or env("DISCORD_BOT_TOKEN"),
            "channel_id": explicit_channel_id or env("DISCORD_PRODUCTION_CHANNEL_ID") or env("DISCORD_CHANNEL_ID"),
            "mention_user_id": (
                explicit_mention_user_id
                if mention_user_id is not None
                else env("DISCORD_PRODUCTION_MENTION_USER_ID") or env("DISCORD_EXPLAINER_USER_ID")
            ),
        }
    else:
        resolved = {
            "profile": normalized_profile,
            "webhook_url": explicit_webhook
            or env("DISCORD_TEST_WEBHOOK_URL")
            or env("DISCORD_PRODUCTION_WEBHOOK_URL")
            or env("DISCORD_WEBHOOK_URL"),
            "bot_token": explicit_bot_token
            or env("DISCORD_TEST_BOT_TOKEN")
            or env("DISCORD_PRODUCTION_BOT_TOKEN")
            or env("DISCORD_BOT_TOKEN"),
            "channel_id": explicit_channel_id
            or env("DISCORD_TEST_CHANNEL_ID")
            or env("DISCORD_PRODUCTION_CHANNEL_ID")
            or env("DISCORD_CHANNEL_ID"),
            # Test notifications never inherit production mentions unless explicitly set.
            "mention_user_id": (
                explicit_mention_user_id
                if mention_user_id is not None
                else env("DISCORD_TEST_MENTION_USER_ID")
            ),
        }

    return resolved


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
    release_count = int(report.get("statistics", {}).get("new_release_count", 0))
    return should_notify_with_filters(
        report,
        notify_on_bootstrap=notify_on_bootstrap,
        release_only=False,
        release_count=release_count,
    )


def should_notify_with_filters(
    report: dict[str, Any],
    *,
    notify_on_bootstrap: bool = False,
    release_only: bool = False,
    release_count: int | None = None,
) -> bool:
    if report.get("changed"):
        if not release_only:
            return True
        if release_count is not None:
            return release_count > 0
        stats = report.get("statistics", {})
        if isinstance(stats, dict):
            return int(stats.get("new_release_count", 0)) > 0
        new_releases = report.get("new_releases", [])
        return isinstance(new_releases, list) and bool(new_releases)
    if notify_on_bootstrap and report.get("bootstrap"):
        return True
    return False


def send_report_to_discord(
    report: dict[str, Any],
    *,
    profile: str = "production",
    max_items: int = 5,
    dry_run: bool = False,
    webhook_url: str | None = None,
    bot_token: str | None = None,
    channel_id: str | None = None,
    mention_user_id: str | None = None,
) -> dict[str, Any]:
    payload = build_discord_payload(report, max_items=max_items)
    config = resolve_discord_delivery_config(
        profile=profile,
        webhook_url=webhook_url,
        bot_token=bot_token,
        channel_id=channel_id,
        mention_user_id=mention_user_id,
    )

    if dry_run:
        return {
            "mode": "dry-run",
            "profile": config["profile"],
            "preview": build_discord_dry_run_text(report, max_items=max_items),
        }

    if config["bot_token"] and config["channel_id"]:
        result = post_via_discord_bot(
            config["bot_token"],
            config["channel_id"],
            report,
            payload,
            mention_user_id=config["mention_user_id"],
        )
        result["mode"] = "bot"
        result["profile"] = config["profile"]
        return result

    if config["webhook_url"]:
        post_to_discord(config["webhook_url"], payload)
        return {"mode": "webhook", "profile": config["profile"]}

    raise DiscordNotificationError(
        "DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID, or DISCORD_WEBHOOK_URL, must be set."
    )
