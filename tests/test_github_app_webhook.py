from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import unittest

from github_scan.github_app_webhook import (
    GitHubAppWebhookProcessor,
    WebhookDeliveryStore,
    build_release_key,
    build_release_report_from_webhook,
    is_release_publication_event,
    normalize_webhook_path,
    verify_github_signature,
)


def _sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def sample_release_payload(
    *,
    action: str = "published",
    draft: bool = False,
    prerelease: bool = False,
    published_at: str | None = "2026-03-23T00:10:00Z",
) -> dict[str, object]:
    return {
        "action": action,
        "installation": {
            "id": 123456,
            "account": {"login": "Sunwood-ai-labs"},
        },
        "repository": {
            "id": 1,
            "name": "github-account-scanner-detection-sample-20260321-195933",
            "full_name": "Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933",
            "html_url": "https://github.com/Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933",
            "description": "sample repo",
            "private": False,
            "fork": False,
            "archived": False,
            "created_at": "2026-03-21T10:59:33Z",
            "updated_at": "2026-03-23T00:10:00Z",
            "pushed_at": "2026-03-23T00:10:00Z",
            "owner": {
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
            },
        },
        "release": {
            "id": 9001,
            "tag_name": "v0.0.1",
            "name": "v0.0.1",
            "html_url": "https://github.com/Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933/releases/tag/v0.0.1",
            "draft": draft,
            "prerelease": prerelease,
            "created_at": "2026-03-23T00:00:00Z",
            "published_at": published_at,
        },
    }


class GitHubAppWebhookTests(unittest.TestCase):
    def test_verify_github_signature_matches_known_secret(self) -> None:
        secret = "It's a Secret to Everybody"
        payload = b"Hello, World!"
        signature = _sign(secret, payload)

        self.assertTrue(verify_github_signature(secret, payload, signature))
        self.assertFalse(verify_github_signature(secret, payload, "sha256=deadbeef"))

    def test_release_publication_event_requires_non_draft_published_release(self) -> None:
        self.assertTrue(is_release_publication_event("release", sample_release_payload()))
        self.assertFalse(
            is_release_publication_event(
                "release",
                sample_release_payload(action="created"),
            )
        )
        self.assertFalse(
            is_release_publication_event(
                "release",
                sample_release_payload(action="released"),
            )
        )
        self.assertFalse(
            is_release_publication_event(
                "release",
                sample_release_payload(draft=True),
            )
        )
        self.assertFalse(
            is_release_publication_event(
                "release",
                sample_release_payload(published_at=None),
            )
        )
        self.assertFalse(
            is_release_publication_event(
                "release",
                sample_release_payload(action="edited"),
            )
        )

    def test_build_release_report_from_webhook_shapes_discord_report(self) -> None:
        report = build_release_report_from_webhook(sample_release_payload())

        self.assertEqual(report["statistics"]["new_release_count"], 1)
        self.assertEqual(report["new_releases"][0]["repository"]["full_name"], "Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933")
        self.assertEqual(report["new_releases"][0]["release"]["tag_name"], "v0.0.1")
        self.assertEqual(report["account"]["login"], "Sunwood-ai-labs")

    def test_build_release_key_uses_repo_and_release_id(self) -> None:
        key = build_release_key(sample_release_payload())
        self.assertEqual(key, "Sunwood-ai-labs/github-account-scanner-detection-sample-20260321-195933#9001")

    def test_normalize_webhook_path_enforces_leading_slash(self) -> None:
        self.assertEqual(normalize_webhook_path("/github/webhook/"), "/github/webhook")
        self.assertEqual(normalize_webhook_path("github/webhook"), "/github/webhook")

    def test_delivery_store_persists_delivery_and_release_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "webhook-state.json"
            store = WebhookDeliveryStore(path, max_entries=10)
            store.record("delivery-1", release_key="release-1")

            reloaded = WebhookDeliveryStore(path, max_entries=10)
            self.assertTrue(reloaded.has_delivery("delivery-1"))
            self.assertTrue(reloaded.has_release("release-1"))

    def test_processor_acknowledges_ping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "super-secret"
            store = WebhookDeliveryStore(Path(temp_dir) / "state.json")
            processor = GitHubAppWebhookProcessor(
                webhook_secret=secret,
                store=store,
                notifier=lambda report, **kwargs: {"mode": "dry-run"},
            )
            body = b'{"zen":"Keep it logically awesome."}'
            result = processor.process(
                {
                    "X-GitHub-Delivery": "delivery-ping",
                    "X-GitHub-Event": "ping",
                    "X-Hub-Signature-256": _sign(secret, body),
                },
                body,
            )

            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.handled)
            self.assertTrue(store.has_delivery("delivery-ping"))

    def test_processor_accepts_title_cased_http_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "super-secret"
            store = WebhookDeliveryStore(Path(temp_dir) / "state.json")
            payload = sample_release_payload()
            body = json.dumps(payload).encode("utf-8")
            processor = GitHubAppWebhookProcessor(
                webhook_secret=secret,
                store=store,
                notifier=lambda report, **kwargs: {"mode": "dry-run"},
            )

            result = processor.process(
                {
                    "X-Github-Delivery": "delivery-http",
                    "X-Github-Event": "release",
                    "X-Hub-Signature-256": _sign(secret, body),
                },
                body,
            )

            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.handled)

    def test_processor_sends_release_once_and_dedupes_redelivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            secret = "super-secret"
            store = WebhookDeliveryStore(Path(temp_dir) / "state.json")
            calls: list[dict[str, object]] = []

            def fake_notifier(report, **kwargs):  # type: ignore[no-untyped-def]
                calls.append({"report": report, "kwargs": kwargs})
                return {"mode": "bot", "thread_id": "123"}

            payload = sample_release_payload()
            body = json.dumps(payload).encode("utf-8")
            processor = GitHubAppWebhookProcessor(
                webhook_secret=secret,
                store=store,
                notifier=fake_notifier,
                discord_profile="production",
            )

            first = processor.process(
                {
                    "X-GitHub-Delivery": "delivery-1",
                    "X-GitHub-Event": "release",
                    "X-Hub-Signature-256": _sign(secret, body),
                },
                body,
            )
            second = processor.process(
                {
                    "X-GitHub-Delivery": "delivery-2",
                    "X-GitHub-Event": "release",
                    "X-Hub-Signature-256": _sign(secret, body),
                },
                body,
            )

            self.assertEqual(first.status_code, 200)
            self.assertTrue(first.handled)
            self.assertEqual(first.discord_result, {"mode": "bot", "thread_id": "123"})
            self.assertEqual(len(calls), 1)
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second.duplicate)
            self.assertEqual(len(calls), 1)

    def test_processor_rejects_invalid_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = WebhookDeliveryStore(Path(temp_dir) / "state.json")
            processor = GitHubAppWebhookProcessor(
                webhook_secret="super-secret",
                store=store,
                notifier=lambda report, **kwargs: {"mode": "dry-run"},
            )
            body = json.dumps(sample_release_payload()).encode("utf-8")
            result = processor.process(
                {
                    "X-GitHub-Delivery": "delivery-invalid",
                    "X-GitHub-Event": "release",
                    "X-Hub-Signature-256": "sha256=deadbeef",
                },
                body,
            )

            self.assertEqual(result.status_code, 401)
            self.assertFalse(result.handled)
            self.assertFalse(store.has_delivery("delivery-invalid"))


if __name__ == "__main__":
    unittest.main()
