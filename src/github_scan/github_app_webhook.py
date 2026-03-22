from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from github_scan.scheduler import send_report_to_discord


class GitHubAppWebhookError(RuntimeError):
    """Raised when GitHub App webhook configuration or payload handling fails."""


def verify_github_signature(secret_token: str, payload: bytes, signature_header: str | None) -> bool:
    if not signature_header:
        return False

    expected = "sha256=" + hmac.new(
        secret_token.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _parse_json_payload(payload: bytes) -> dict[str, Any]:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubAppWebhookError(f"Invalid webhook JSON payload: {error}") from error

    if not isinstance(data, dict):
        raise GitHubAppWebhookError("Webhook JSON payload must be an object.")
    return data


def is_release_publication_event(
    event_name: str,
    payload: Mapping[str, Any],
    *,
    include_prereleases: bool = True,
) -> bool:
    if event_name != "release":
        return False

    release = payload.get("release")
    if not isinstance(release, Mapping):
        return False

    action = payload.get("action")
    if action != "published":
        return False

    if bool(release.get("draft", False)):
        return False

    published_at = release.get("published_at")
    if not isinstance(published_at, str) or not published_at.strip():
        return False

    if not include_prereleases and bool(release.get("prerelease", False)):
        return False

    return True


def build_release_report_from_webhook(
    payload: Mapping[str, Any],
    *,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    repository = payload.get("repository")
    release = payload.get("release")
    installation = payload.get("installation")

    if not isinstance(repository, Mapping):
        raise GitHubAppWebhookError("Webhook payload is missing a repository object.")
    if not isinstance(release, Mapping):
        raise GitHubAppWebhookError("Webhook payload is missing a release object.")

    owner = repository.get("owner")
    if not isinstance(owner, Mapping):
        raise GitHubAppWebhookError("Webhook repository is missing an owner object.")

    account_login = owner.get("login") or "unknown"
    account_type = owner.get("type") or "User"
    account_url = owner.get("html_url") or f"https://github.com/{account_login}"

    repo_item = {
        "id": repository.get("id"),
        "name": repository.get("name"),
        "full_name": repository.get("full_name"),
        "html_url": repository.get("html_url"),
        "description": repository.get("description"),
        "is_private": bool(repository.get("private", False)),
        "is_fork": bool(repository.get("fork", False)),
        "is_archived": bool(repository.get("archived", False)),
        "created_at": repository.get("created_at"),
        "updated_at": repository.get("updated_at"),
        "pushed_at": repository.get("pushed_at"),
    }
    release_item = {
        "id": release.get("id"),
        "tag_name": release.get("tag_name"),
        "name": release.get("name"),
        "html_url": release.get("html_url"),
        "is_draft": bool(release.get("draft", False)),
        "is_prerelease": bool(release.get("prerelease", False)),
        "created_at": release.get("created_at"),
        "published_at": release.get("published_at"),
    }

    account = {
        "login": account_login,
        "type": account_type,
        "html_url": account_url,
        "public_repos": owner.get("public_repos", 0),
        "installation_id": installation.get("id") if isinstance(installation, Mapping) else None,
    }

    timestamp = checked_at or datetime.now(UTC)
    return {
        "checked_at": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "bootstrap": False,
        "changed": True,
        "account": account,
        "statistics": {
            "request_count": 0,
            "token_used": False,
            "new_repository_count": 0,
            "new_release_count": 1,
            "rate_limit": None,
        },
        "new_repositories": [],
        "new_releases": [
            {
                "repository": repo_item,
                "release": release_item,
            }
        ],
    }


def build_release_key(payload: Mapping[str, Any]) -> str:
    repository = payload.get("repository")
    release = payload.get("release")
    if not isinstance(repository, Mapping) or not isinstance(release, Mapping):
        raise GitHubAppWebhookError("Webhook payload is missing repository or release data.")

    full_name = repository.get("full_name") or "unknown/unknown"
    release_id = release.get("id")
    if release_id is not None:
        return f"{full_name}#{release_id}"

    tag_name = release.get("tag_name") or "unknown-tag"
    published_at = release.get("published_at") or release.get("created_at") or "unknown-time"
    return f"{full_name}#{tag_name}@{published_at}"


def normalize_webhook_path(path: str) -> str:
    candidate = path.strip() or "/github/webhook"
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    if candidate != "/" and candidate.endswith("/"):
        candidate = candidate[:-1]
    return candidate


class WebhookDeliveryStore:
    def __init__(self, path: Path, *, max_entries: int = 5000) -> None:
        self.path = path
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._delivery_ids: list[str] = []
        self._release_keys: list[str] = []
        self._delivery_set: set[str] = set()
        self._release_set: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise GitHubAppWebhookError(f"Failed to load webhook state file: {error}") from error

        if not isinstance(raw, dict):
            raise GitHubAppWebhookError("Webhook state file must contain an object.")

        delivery_ids = raw.get("delivery_ids", [])
        release_keys = raw.get("release_keys", [])
        if isinstance(delivery_ids, list):
            self._delivery_ids = [value for value in delivery_ids if isinstance(value, str)]
            self._delivery_set = set(self._delivery_ids)
        if isinstance(release_keys, list):
            self._release_keys = [value for value in release_keys if isinstance(value, str)]
            self._release_set = set(self._release_keys)

    def has_delivery(self, delivery_id: str) -> bool:
        with self._lock:
            return delivery_id in self._delivery_set

    def has_release(self, release_key: str) -> bool:
        with self._lock:
            return release_key in self._release_set

    def record(self, delivery_id: str, *, release_key: str | None = None) -> None:
        with self._lock:
            changed = False
            if delivery_id not in self._delivery_set:
                self._delivery_set.add(delivery_id)
                self._delivery_ids.append(delivery_id)
                changed = True
            if release_key and release_key not in self._release_set:
                self._release_set.add(release_key)
                self._release_keys.append(release_key)
                changed = True
            if not changed:
                return
            self._trim()
            self._save()

    def _trim(self) -> None:
        if len(self._delivery_ids) > self.max_entries:
            self._delivery_ids = self._delivery_ids[-self.max_entries :]
            self._delivery_set = set(self._delivery_ids)
        if len(self._release_keys) > self.max_entries:
            self._release_keys = self._release_keys[-self.max_entries :]
            self._release_set = set(self._release_keys)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "delivery_ids": self._delivery_ids,
                    "release_keys": self._release_keys,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


@dataclass(slots=True)
class WebhookProcessResult:
    status_code: int
    delivery_id: str | None
    event_name: str
    action: str | None
    handled: bool
    duplicate: bool
    message: str
    discord_result: dict[str, Any] | None = None
    release_key: str | None = None


class GitHubAppWebhookProcessor:
    def __init__(
        self,
        *,
        webhook_secret: str,
        store: WebhookDeliveryStore,
        discord_profile: str = "production",
        max_items: int = 5,
        include_prereleases: bool = True,
        dry_run_discord: bool = False,
        notifier: Callable[..., dict[str, Any]] = send_report_to_discord,
    ) -> None:
        if not webhook_secret.strip():
            raise GitHubAppWebhookError("GITHUB_APP_WEBHOOK_SECRET is required.")

        self.webhook_secret = webhook_secret
        self.store = store
        self.discord_profile = discord_profile
        self.max_items = max_items
        self.include_prereleases = include_prereleases
        self.dry_run_discord = dry_run_discord
        self.notifier = notifier

    def process(self, headers: Mapping[str, str], body: bytes) -> WebhookProcessResult:
        normalized_headers = {key.lower(): value for key, value in headers.items()}
        delivery_id = normalized_headers.get("x-github-delivery")
        event_name = (normalized_headers.get("x-github-event") or "").strip().lower()
        signature = normalized_headers.get("x-hub-signature-256")

        if not delivery_id:
            return WebhookProcessResult(
                status_code=400,
                delivery_id=None,
                event_name=event_name or "unknown",
                action=None,
                handled=False,
                duplicate=False,
                message="Missing X-GitHub-Delivery header.",
            )

        if not event_name:
            return WebhookProcessResult(
                status_code=400,
                delivery_id=delivery_id,
                event_name="unknown",
                action=None,
                handled=False,
                duplicate=False,
                message="Missing X-GitHub-Event header.",
            )

        if not verify_github_signature(self.webhook_secret, body, signature):
            return WebhookProcessResult(
                status_code=401,
                delivery_id=delivery_id,
                event_name=event_name,
                action=None,
                handled=False,
                duplicate=False,
                message="Invalid webhook signature.",
            )

        if self.store.has_delivery(delivery_id):
            return WebhookProcessResult(
                status_code=200,
                delivery_id=delivery_id,
                event_name=event_name,
                action=None,
                handled=False,
                duplicate=True,
                message="Duplicate delivery ignored.",
            )

        payload = _parse_json_payload(body)
        action = payload.get("action") if isinstance(payload.get("action"), str) else None

        if event_name == "ping":
            self.store.record(delivery_id)
            return WebhookProcessResult(
                status_code=200,
                delivery_id=delivery_id,
                event_name=event_name,
                action=action,
                handled=True,
                duplicate=False,
                message="Ping acknowledged.",
            )

        if not is_release_publication_event(
            event_name,
            payload,
            include_prereleases=self.include_prereleases,
        ):
            self.store.record(delivery_id)
            return WebhookProcessResult(
                status_code=202,
                delivery_id=delivery_id,
                event_name=event_name,
                action=action,
                handled=False,
                duplicate=False,
                message="Event ignored.",
            )

        release_key = build_release_key(payload)
        if self.store.has_release(release_key):
            self.store.record(delivery_id)
            return WebhookProcessResult(
                status_code=200,
                delivery_id=delivery_id,
                event_name=event_name,
                action=action,
                handled=False,
                duplicate=True,
                message="Duplicate release ignored.",
                release_key=release_key,
            )

        report = build_release_report_from_webhook(payload)
        discord_result = self.notifier(
            report,
            profile=self.discord_profile,
            max_items=self.max_items,
            dry_run=self.dry_run_discord,
        )
        self.store.record(delivery_id, release_key=release_key)
        return WebhookProcessResult(
            status_code=200,
            delivery_id=delivery_id,
            event_name=event_name,
            action=action,
            handled=True,
            duplicate=False,
            message="Release notification processed.",
            discord_result=discord_result,
            release_key=release_key,
        )


class _GitHubAppWebhookHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler_class: type[BaseHTTPRequestHandler],
        *,
        processor: GitHubAppWebhookProcessor,
        webhook_path: str,
        log_dir: Path,
    ) -> None:
        super().__init__(server_address, request_handler_class)
        self.processor = processor
        self.webhook_path = webhook_path
        self.log_dir = log_dir


def _append_log(log_dir: Path, result: WebhookProcessResult) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        (
            f"[{timestamp}] delivery={result.delivery_id or '-'} "
            f"event={result.event_name} action={result.action or '-'} "
            f"status={result.status_code} handled={result.handled} duplicate={result.duplicate}"
        ),
        f"  message={result.message}",
    ]
    if result.release_key:
        lines.append(f"  release_key={result.release_key}")
    if result.discord_result is not None:
        lines.append(f"  discord={json.dumps(result.discord_result, ensure_ascii=False)}")

    with log_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line}\n")


def build_github_app_webhook_handler() -> type[BaseHTTPRequestHandler]:
    class GitHubAppWebhookHandler(BaseHTTPRequestHandler):
        server: _GitHubAppWebhookHTTPServer

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/healthz":
                self._send_json(200, {"status": "ok"})
                return
            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path != self.server.webhook_path:
                self._send_json(404, {"error": "Not found"})
                return

            content_length = self.headers.get("Content-Length")
            try:
                body_length = int(content_length or "0")
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length header"})
                return

            body = self.rfile.read(body_length)
            try:
                result = self.server.processor.process(dict(self.headers.items()), body)
            except GitHubAppWebhookError as error:
                self._send_json(400, {"error": str(error)})
                return
            except Exception as error:  # noqa: BLE001
                self._send_json(500, {"error": f"Internal webhook error: {error}"})
                return

            _append_log(self.server.log_dir, result)
            self._send_json(
                result.status_code,
                {
                    "delivery_id": result.delivery_id,
                    "event": result.event_name,
                    "action": result.action,
                    "handled": result.handled,
                    "duplicate": result.duplicate,
                    "message": result.message,
                    "release_key": result.release_key,
                    "discord_result": result.discord_result,
                },
            )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return GitHubAppWebhookHandler


def serve_github_app_webhook(
    *,
    host: str,
    port: int,
    webhook_path: str,
    webhook_secret: str,
    state_file: Path,
    log_dir: Path,
    discord_profile: str = "production",
    max_items: int = 5,
    include_prereleases: bool = True,
    dry_run_discord: bool = False,
) -> None:
    handler = build_github_app_webhook_handler()
    processor = GitHubAppWebhookProcessor(
        webhook_secret=webhook_secret,
        store=WebhookDeliveryStore(state_file),
        discord_profile=discord_profile,
        max_items=max_items,
        include_prereleases=include_prereleases,
        dry_run_discord=dry_run_discord,
    )
    server = _GitHubAppWebhookHTTPServer(
        (host, port),
        handler,
        processor=processor,
        webhook_path=normalize_webhook_path(webhook_path),
        log_dir=log_dir,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
