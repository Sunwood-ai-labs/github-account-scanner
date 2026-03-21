from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
RECENT_RELEASE_WINDOW = 100
SCHEMA_VERSION = 1


class GitHubApiError(RuntimeError):
    """Raised when the GitHub API returns an error response."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_url(path: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return f"{API_ROOT}{path}"
    return f"{API_ROOT}{path}?{urlencode(params)}"


def _parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        url = section.split(";", 1)[0].strip()
        if url.startswith("<") and url.endswith(">"):
            return url[1:-1]
    return None


def _estimate_minimum_request_count(public_repo_count: int) -> int:
    repo_pages = max(1, math.ceil(public_repo_count / 100))
    return 1 + repo_pages + public_repo_count


@dataclass(slots=True)
class ReleaseInfo:
    id: int
    tag_name: str
    name: str | None
    html_url: str
    is_draft: bool
    is_prerelease: bool
    created_at: str | None
    published_at: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ReleaseInfo":
        return cls(
            id=int(data["id"]),
            tag_name=data["tag_name"],
            name=data.get("name"),
            html_url=data["html_url"],
            is_draft=bool(data.get("draft", False)),
            is_prerelease=bool(data.get("prerelease", False)),
            created_at=data.get("created_at"),
            published_at=data.get("published_at"),
        )

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "ReleaseInfo":
        return cls(
            id=int(data["id"]),
            tag_name=data["tag_name"],
            name=data.get("name"),
            html_url=data["html_url"],
            is_draft=bool(data.get("is_draft", False)),
            is_prerelease=bool(data.get("is_prerelease", False)),
            created_at=data.get("created_at"),
            published_at=data.get("published_at"),
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tag_name": self.tag_name,
            "name": self.name,
            "html_url": self.html_url,
            "is_draft": self.is_draft,
            "is_prerelease": self.is_prerelease,
            "created_at": self.created_at,
            "published_at": self.published_at,
        }


@dataclass(slots=True)
class RepositoryInfo:
    id: int
    name: str
    full_name: str
    html_url: str
    description: str | None
    is_private: bool
    is_fork: bool
    is_archived: bool
    created_at: str
    updated_at: str
    pushed_at: str | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RepositoryInfo":
        return cls(
            id=int(data["id"]),
            name=data["name"],
            full_name=data["full_name"],
            html_url=data["html_url"],
            description=data.get("description"),
            is_private=bool(data.get("private", False)),
            is_fork=bool(data.get("fork", False)),
            is_archived=bool(data.get("archived", False)),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            pushed_at=data.get("pushed_at"),
        )

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "RepositoryInfo":
        return cls(
            id=int(data["id"]),
            name=data["name"],
            full_name=data["full_name"],
            html_url=data["html_url"],
            description=data.get("description"),
            is_private=bool(data.get("is_private", False)),
            is_fork=bool(data.get("is_fork", False)),
            is_archived=bool(data.get("is_archived", False)),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            pushed_at=data.get("pushed_at"),
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "html_url": self.html_url,
            "description": self.description,
            "is_private": self.is_private,
            "is_fork": self.is_fork,
            "is_archived": self.is_archived,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pushed_at": self.pushed_at,
        }


@dataclass(slots=True)
class Snapshot:
    account: dict[str, Any]
    repositories: list[RepositoryInfo]
    releases_by_repo: dict[str, list[ReleaseInfo]]

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> "Snapshot":
        repositories = [RepositoryInfo.from_state(item) for item in data.get("repositories", [])]
        releases = {
            repo_name: [ReleaseInfo.from_state(release) for release in repo_releases]
            for repo_name, repo_releases in data.get("releases_by_repo", {}).items()
        }
        return cls(account=data["account"], repositories=repositories, releases_by_repo=releases)

    def to_state(self) -> dict[str, Any]:
        ordered_repositories = sorted(self.repositories, key=lambda repo: repo.full_name.lower())
        ordered_releases = {
            repo_name: [release.to_state() for release in releases]
            for repo_name, releases in sorted(self.releases_by_repo.items(), key=lambda item: item[0].lower())
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "account": self.account,
            "repositories": [repo.to_state() for repo in ordered_repositories],
            "releases_by_repo": ordered_releases,
        }


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: float = 30.0,
        request_pause_seconds: float = 0.0,
    ) -> None:
        self.token = token
        self.timeout = timeout
        self.request_pause_seconds = request_pause_seconds
        self.request_count = 0
        self.rate_limit: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-scan/0.1.0",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _update_rate_limit(self, headers: Any) -> None:
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        resource = headers.get("X-RateLimit-Resource")
        if limit is None and remaining is None and reset is None:
            return
        current_remaining = int(remaining) if remaining is not None else None
        min_remaining = self.rate_limit.get("min_remaining")
        if current_remaining is not None:
            self.rate_limit["min_remaining"] = (
                current_remaining if min_remaining is None else min(min_remaining, current_remaining)
            )
        self.rate_limit["limit"] = int(limit) if limit is not None else None
        self.rate_limit["remaining"] = current_remaining
        self.rate_limit["reset"] = int(reset) if reset is not None else None
        self.rate_limit["resource"] = resource

    def _request_json(self, url: str) -> tuple[Any, Any]:
        request = Request(url, headers=self._headers(), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                self.request_count += 1
                self._update_rate_limit(response.headers)
                payload = response.read().decode("utf-8")
                return json.loads(payload), response.headers
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                message = data.get("message", body)
            except json.JSONDecodeError:
                message = body or str(error)
            rate_remaining = error.headers.get("X-RateLimit-Remaining")
            if error.code == 403 and rate_remaining == "0":
                raise GitHubApiError(
                    "GitHub API rate limit was exhausted. "
                    "Set GITHUB_TOKEN or GH_TOKEN before running the scan."
                ) from error
            raise GitHubApiError(f"GitHub API error {error.code}: {message}") from error
        except URLError as error:
            raise GitHubApiError(f"GitHub API request failed: {error}") from error

    def _paginate(self, path: str, params: dict[str, Any] | None = None) -> list[Any]:
        items: list[Any] = []
        next_url = _request_url(path, params)
        while next_url:
            page_items, headers = self._request_json(next_url)
            if not isinstance(page_items, list):
                raise GitHubApiError(f"Expected a list response from {next_url}")
            items.extend(page_items)
            next_url = _parse_next_link(headers.get("Link"))
        return items

    def fetch_snapshot(self, login: str) -> Snapshot:
        account_data, _ = self._request_json(_request_url(f"/users/{login}"))
        account_type = account_data["type"]
        public_repo_count = int(account_data["public_repos"])
        minimum_request_count = _estimate_minimum_request_count(public_repo_count)
        if not self.token and minimum_request_count > 60:
            raise GitHubApiError(
                "This account is too large for an unauthenticated full scan. "
                f"At least {minimum_request_count} REST requests are needed for {public_repo_count} repositories, "
                "but unauthenticated GitHub API access is limited to 60 requests per hour. "
                "Set GITHUB_TOKEN or GH_TOKEN before running the scan."
            )
        repo_path = f"/users/{login}/repos" if account_type == "User" else f"/orgs/{login}/repos"
        repositories = [
            RepositoryInfo.from_api(item)
            for item in self._paginate(
                repo_path,
                {
                    "type": "owner" if account_type == "User" else "public",
                    "sort": "full_name",
                    "direction": "asc",
                    "per_page": 100,
                },
            )
        ]

        releases_by_repo: dict[str, list[ReleaseInfo]] = {}
        for repository in repositories:
            release_items, _ = self._request_json(
                _request_url(
                    f"/repos/{repository.full_name}/releases",
                    {"per_page": RECENT_RELEASE_WINDOW},
                )
            )
            if not isinstance(release_items, list):
                raise GitHubApiError(f"Expected releases list for {repository.full_name}")
            releases_by_repo[repository.full_name] = [ReleaseInfo.from_api(item) for item in release_items]
            if self.request_pause_seconds > 0:
                time.sleep(self.request_pause_seconds)

        account = {
            "login": account_data["login"],
            "type": account_type,
            "html_url": account_data["html_url"],
            "public_repos": public_repo_count,
            "release_window": RECENT_RELEASE_WINDOW,
        }
        return Snapshot(account=account, repositories=repositories, releases_by_repo=releases_by_repo)


def load_snapshot(path: Path) -> Snapshot | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot.from_state(data)


def save_snapshot(path: Path, snapshot: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_state(), indent=2), encoding="utf-8")


def _release_sort_key(entry: dict[str, Any]) -> tuple[str, str]:
    release = entry["release"]
    repository = entry["repository"]
    timestamp = release.published_at or release.created_at or repository.created_at
    return (timestamp or "", repository.full_name.lower())


def compare_snapshots(previous: Snapshot | None, current: Snapshot) -> dict[str, Any]:
    checked_at = utc_now()
    if previous is None:
        return {
            "checked_at": checked_at,
            "bootstrap": True,
            "changed": False,
            "account": current.account,
            "new_repositories": [],
            "new_releases": [],
        }

    previous_repositories = {repo.id for repo in previous.repositories}
    new_repositories = [repo for repo in current.repositories if repo.id not in previous_repositories]
    new_repositories.sort(key=lambda repo: repo.created_at, reverse=True)

    previous_releases = {
        repo_name: {release.id: release for release in releases}
        for repo_name, releases in previous.releases_by_repo.items()
    }
    new_releases: list[dict[str, Any]] = []
    current_repo_map = {repo.full_name: repo for repo in current.repositories}
    for repo_name, releases in current.releases_by_repo.items():
        seen_releases = previous_releases.get(repo_name, {})
        repository = current_repo_map[repo_name]
        for release in releases:
            previous_release = seen_releases.get(release.id)
            if release.is_draft:
                continue
            if previous_release is not None and not previous_release.is_draft:
                continue
            new_releases.append({"repository": repository, "release": release})
    new_releases.sort(key=_release_sort_key, reverse=True)

    return {
        "checked_at": checked_at,
        "bootstrap": False,
        "changed": bool(new_repositories or new_releases),
        "account": current.account,
        "new_repositories": new_repositories,
        "new_releases": new_releases,
    }


def _repo_report_item(repo: RepositoryInfo) -> dict[str, Any]:
    return {
        "id": repo.id,
        "name": repo.name,
        "full_name": repo.full_name,
        "html_url": repo.html_url,
        "description": repo.description,
        "created_at": repo.created_at,
        "updated_at": repo.updated_at,
        "pushed_at": repo.pushed_at,
        "is_private": repo.is_private,
        "is_fork": repo.is_fork,
        "is_archived": repo.is_archived,
    }


def _release_report_item(repository: RepositoryInfo, release: ReleaseInfo) -> dict[str, Any]:
    return {
        "repository": _repo_report_item(repository),
        "release": {
            "id": release.id,
            "tag_name": release.tag_name,
            "name": release.name,
            "html_url": release.html_url,
            "is_draft": release.is_draft,
            "is_prerelease": release.is_prerelease,
            "created_at": release.created_at,
            "published_at": release.published_at,
        },
    }


def build_report_document(
    comparison: dict[str, Any],
    *,
    request_count: int,
    token_used: bool,
    rate_limit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    new_repositories = [_repo_report_item(repo) for repo in comparison["new_repositories"]]
    new_releases = [
        _release_report_item(item["repository"], item["release"])
        for item in comparison["new_releases"]
    ]
    return {
        "checked_at": comparison["checked_at"],
        "bootstrap": comparison["bootstrap"],
        "changed": comparison["changed"],
        "account": comparison["account"],
        "statistics": {
            "request_count": request_count,
            "token_used": token_used,
            "new_repository_count": len(new_repositories),
            "new_release_count": len(new_releases),
            "rate_limit": rate_limit or {},
        },
        "new_repositories": new_repositories,
        "new_releases": new_releases,
    }


def write_report_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    account = report["account"]
    stats = report["statistics"]
    lines = [
        f"# github-scan report for {account['login']}",
        "",
        f"- Checked at: {report['checked_at']}",
        f"- Account type: {account['type']}",
        f"- Public repositories: {account['public_repos']}",
        f"- API requests: {stats['request_count']}",
        f"- Token used: {'yes' if stats['token_used'] else 'no'}",
    ]

    min_remaining = stats.get("rate_limit", {}).get("min_remaining")
    if min_remaining is not None:
        lines.append(f"- Lowest remaining rate limit observed: {min_remaining}")

    lines.append("")

    if report["bootstrap"]:
        lines.extend(
            [
                "Initial baseline snapshot was created.",
                "Future runs will report only repositories and releases that appear after this baseline.",
            ]
        )
        return "\n".join(lines) + "\n"

    if not report["changed"]:
        lines.append("No new repositories or releases were detected.")
        return "\n".join(lines) + "\n"

    if report["new_repositories"]:
        lines.append("## New repositories")
        lines.append("")
        for repo in report["new_repositories"]:
            description = f" - {repo['description']}" if repo.get("description") else ""
            lines.append(
                f"- [{repo['full_name']}]({repo['html_url']}) "
                f"(created {repo['created_at']}, fork={str(repo['is_fork']).lower()}, archived={str(repo['is_archived']).lower()})"
                f"{description}"
            )
        lines.append("")

    if report["new_releases"]:
        lines.append("## New releases")
        lines.append("")
        for item in report["new_releases"]:
            repo = item["repository"]
            release = item["release"]
            release_name = release["name"] or release["tag_name"]
            published = release["published_at"] or release["created_at"] or "unknown"
            qualifier_parts = []
            if release["is_draft"]:
                qualifier_parts.append("draft")
            if release["is_prerelease"]:
                qualifier_parts.append("prerelease")
            qualifier = f" ({', '.join(qualifier_parts)})" if qualifier_parts else ""
            lines.append(
                f"- [{repo['full_name']}]({repo['html_url']}) -> "
                f"[{release_name}]({release['html_url']}) "
                f"[tag: `{release['tag_name']}`] published {published}{qualifier}"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8")
