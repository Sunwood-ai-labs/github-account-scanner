from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DiscordNotificationError(RuntimeError):
    """Raised when a Discord webhook notification fails."""


_DISCORD_CHANNEL_URL_RE = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?discord\.com/channels/\d+/(\d+)(?:/\d+)?/?$"
)


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_discord_channel_id(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise DiscordNotificationError("Discord channel target is empty.")
    if candidate.isdigit():
        return candidate

    match = _DISCORD_CHANNEL_URL_RE.match(candidate)
    if match:
        return match.group(1)

    raise DiscordNotificationError(
        "Discord channel target must be a channel ID or a Discord channel URL."
    )


def _parse_checked_at(checked_at: str) -> datetime:
    if checked_at.endswith("Z"):
        checked_at = checked_at[:-1] + "+00:00"
    return datetime.fromisoformat(checked_at)


def _checked_at_jst(report: dict[str, Any]) -> str:
    dt = _parse_checked_at(report["checked_at"]).astimezone(JST)
    return dt.strftime("%Y-%m-%d %H:%M JST")


def _discord_color(report: dict[str, Any]) -> int:
    if report["bootstrap"]:
        return 0x3498DB
    if report["changed"]:
        return 0x2ECC71
    return 0x95A5A6


def _safe_count(label: str, items: list[dict[str, Any]], max_items: int) -> str:
    if len(items) <= max_items:
        return ""
    return f"\n他 {len(items) - max_items} 件"


def _repo_lines(report: dict[str, Any], *, max_items: int) -> str | None:
    repositories = report.get("new_repositories", [])
    if not repositories:
        return None

    lines = []
    for repo in repositories[:max_items]:
        created_at = repo.get("created_at") or "unknown"
        lines.append(f"- [`{repo['full_name']}`]({repo['html_url']})")
        lines.append(f"  作成日時: `{created_at}`")
    return "".join(line + "\n" for line in lines).rstrip() + _safe_count("repository", repositories, max_items)


def _release_lines(report: dict[str, Any], *, max_items: int) -> str | None:
    releases = report.get("new_releases", [])
    if not releases:
        return None

    lines = []
    for item in releases[:max_items]:
        repo = item["repository"]
        release = item["release"]
        release_name = release["name"] or release["tag_name"]
        published_at = release["published_at"] or release["created_at"] or "unknown"
        lines.append(f"- [`{repo['full_name']}`]({repo['html_url']})")
        lines.append(f"  リリース: [`{release_name}`]({release['html_url']})")
        lines.append(f"  タグ: `{release['tag_name']}` / 公開日時: `{published_at}`")
    return "".join(line + "\n" for line in lines).rstrip() + _safe_count("release", releases, max_items)


def build_discord_payload(report: dict[str, Any], *, max_items: int = 5) -> dict[str, Any]:
    account = report["account"]
    stats = report["statistics"]

    if report["bootstrap"]:
        description = "初回ベースラインを作成しました。次回以降の実行から新規 repository / release を通知します。"
    elif report["changed"]:
        description = "新しい更新を検知しました。"
    else:
        description = "変更はありませんでした。"

    fields: list[dict[str, Any]] = [
        {
            "name": "監視対象",
            "value": f"`{account['login']}` ({account['type']})",
            "inline": True,
        },
        {
            "name": "新規 Repository",
            "value": str(stats["new_repository_count"]),
            "inline": True,
        },
        {
            "name": "新規 Release",
            "value": str(stats["new_release_count"]),
            "inline": True,
        },
        {
            "name": "チェック時刻",
            "value": f"`{_checked_at_jst(report)}`",
            "inline": False,
        },
    ]

    repo_block = _repo_lines(report, max_items=max_items)
    if repo_block:
        fields.append(
            {
                "name": "新しく作成された Repository",
                "value": repo_block,
                "inline": False,
            }
        )

    release_block = _release_lines(report, max_items=max_items)
    if release_block:
        fields.append(
            {
                "name": "新しく公開された Release",
                "value": release_block,
                "inline": False,
            }
        )

    payload = {
        "embeds": [
            {
                "title": "GitHub アカウント監視レポート",
                "description": description,
                "color": _discord_color(report),
                "fields": fields,
                "footer": {
                    "text": "github-account-scanner",
                },
                "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
        ]
    }
    return payload


def build_discord_dry_run_text(report: dict[str, Any], *, max_items: int = 5) -> str:
    payload = build_discord_payload(report, max_items=max_items)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def build_thread_name(report: dict[str, Any]) -> str:
    account = report["account"]["login"]
    stats = report["statistics"]
    checked_at = _checked_at_jst(report)
    return (
        f"{account} 監視 {checked_at} "
        f"Repo{stats['new_repository_count']}件 Release{stats['new_release_count']}件"
    )[:100]


def build_thread_starter_content(report: dict[str, Any]) -> str:
    account = report["account"]["login"]
    stats = report["statistics"]
    if report["bootstrap"]:
        status = "初回ベースラインを作成しました"
    elif report["changed"]:
        status = "新しい更新を検知しました"
    else:
        status = "変更はありませんでした"

    lines = [f"{account}: {status}"]

    new_repositories = report.get("new_repositories", [])
    if new_repositories:
        first_repo = new_repositories[0]["full_name"]
        suffix = f" 他{len(new_repositories) - 1}件" if len(new_repositories) > 1 else ""
        lines.append(f"Repo: {first_repo}{suffix}")

    new_releases = report.get("new_releases", [])
    if new_releases:
        first_release = new_releases[0]
        repo_name = first_release["repository"]["full_name"]
        release_name = first_release["release"]["name"] or first_release["release"]["tag_name"]
        suffix = f" 他{len(new_releases) - 1}件" if len(new_releases) > 1 else ""
        lines.append(f"Release: {repo_name} / {release_name}{suffix}")

    if not new_repositories and not new_releases:
        lines.append(
            f"Repository {stats['new_repository_count']}件 / "
            f"Release {stats['new_release_count']}件"
        )

    lines.append("詳細はスレッドへ。")
    return "\n".join(lines)


@lru_cache(maxsize=None)
def _load_explainer_template(name: str) -> str:
    return (
        resources.files("github_scan")
        .joinpath("prompts")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def _build_explainer_repository_lines(report: dict[str, Any]) -> str:
    lines: list[str] = []

    new_repositories = report.get("new_repositories", [])
    for repo in new_repositories[:3]:
        lines.append(f"- Repository: {repo['full_name']}")
        lines.append(f"  URL: {repo['html_url']}")
        if repo.get("description"):
            lines.append(f"  説明: {repo['description']}")

    if not lines:
        lines.append("- 今回のレポートでは新規 repository はありませんでした。")

    return "\n".join(lines)


def _build_explainer_release_lines(report: dict[str, Any]) -> str:
    lines: list[str] = []

    new_releases = report.get("new_releases", [])
    for item in new_releases[:3]:
        repo = item["repository"]
        release = item["release"]
        lines.append(f"- Release: {repo['full_name']} / {release['tag_name']}")
        lines.append(f"  URL: {release['html_url']}")
        lines.append(f"  公開日時: {release.get('published_at') or release.get('created_at') or 'unknown'}")

    if not lines:
        lines.append("- 今回のレポートでは新規 release はありませんでした。")

    return "\n".join(lines)


def _build_explainer_related_url_lines(report: dict[str, Any]) -> str:
    lines = [f"- Account: {report['account']['html_url']}"]
    seen: set[str] = {report["account"]["html_url"]}

    for repo in report.get("new_repositories", [])[:3]:
        url = repo["html_url"]
        if url not in seen:
            lines.append(f"- Repository: {url}")
            seen.add(url)

    for item in report.get("new_releases", [])[:3]:
        repo_url = item["repository"]["html_url"]
        release_url = item["release"]["html_url"]
        if repo_url not in seen:
            lines.append(f"- Repository: {repo_url}")
            seen.add(repo_url)
        if release_url not in seen:
            lines.append(f"- Release: {release_url}")
            seen.add(release_url)

    return "\n".join(lines)


def build_explainer_request(report: dict[str, Any], mention_user_id: str) -> str:
    sections: list[str] = []

    if report.get("new_repositories"):
        sections.append(
            _load_explainer_template("discord_explainer_repository.md").format(
                repository_lines=_build_explainer_repository_lines(report),
            ).strip()
        )

    if report.get("new_releases"):
        sections.append(
            _load_explainer_template("discord_explainer_release.md").format(
                release_lines=_build_explainer_release_lines(report),
            ).strip()
        )

    if not sections:
        sections.append("## 対象イベント\n- 今回のレポートでは新規イベントはありませんでした。")

    return _load_explainer_template("discord_explainer_request.md").format(
        mention=f"<@{mention_user_id}>",
        account_login=report["account"]["login"],
        account_url=report["account"]["html_url"],
        checked_at=_checked_at_jst(report),
        event_sections="\n\n".join(sections),
        related_url_lines=_build_explainer_related_url_lines(report),
    )


def _bot_request(
    method: str,
    path: str,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    request = Request(
        f"https://discord.com/api/v10{path}",
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "github-account-scanner/0.1.0",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise DiscordNotificationError(f"Discord bot API error {error.code}: {body}") from error
    except URLError as error:
        raise DiscordNotificationError(f"Discord bot API request failed: {error}") from error


def post_via_discord_bot(
    token: str,
    channel_id: str,
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    mention_user_id: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    resolved_channel_id = normalize_discord_channel_id(channel_id)

    starter_message = _bot_request(
        "POST",
        f"/channels/{quote(resolved_channel_id, safe='')}/messages",
        token,
        payload={
            "content": build_thread_starter_content(report),
            "allowed_mentions": {"parse": []},
        },
        timeout=timeout,
    )

    thread = _bot_request(
        "POST",
        f"/channels/{quote(resolved_channel_id, safe='')}/messages/{quote(starter_message['id'], safe='')}/threads",
        token,
        payload={
            "name": build_thread_name(report),
            "auto_archive_duration": 1440,
        },
        timeout=timeout,
    )

    thread_message = _bot_request(
        "POST",
        f"/channels/{quote(thread['id'], safe='')}/messages",
        token,
        payload={
            **payload,
            "allowed_mentions": {"parse": []},
        },
        timeout=timeout,
    )

    explainer_message: dict[str, Any] | None = None
    if mention_user_id:
        explainer_message = _bot_request(
            "POST",
            f"/channels/{quote(thread['id'], safe='')}/messages",
            token,
            payload={
                "content": build_explainer_request(report, mention_user_id),
                "allowed_mentions": {"users": [mention_user_id]},
            },
            timeout=timeout,
        )

    return {
        "channel_id": resolved_channel_id,
        "starter_message_id": starter_message["id"],
        "thread_id": thread["id"],
        "thread_name": thread.get("name") or build_thread_name(report),
        "thread_message_id": thread_message["id"],
        "explainer_message_id": explainer_message["id"] if explainer_message else None,
    }


def post_to_discord(webhook_url: str, payload: dict[str, Any], *, timeout: float = 30.0) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "github-account-scanner/0.1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout):
            return
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise DiscordNotificationError(f"Discord webhook error {error.code}: {response_body}") from error
    except URLError as error:
        raise DiscordNotificationError(f"Discord webhook request failed: {error}") from error
JST = timezone(timedelta(hours=9))
