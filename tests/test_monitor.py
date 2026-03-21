from pathlib import Path
import tempfile
import unittest

from github_scan.discord_webhook import (
    build_discord_dry_run_text,
    build_discord_payload,
    build_explainer_request,
    build_thread_name,
    build_thread_starter_content,
)
from github_scan.monitor import (
    GitHubApiError,
    GitHubClient,
    RECENT_RELEASE_WINDOW,
    ReleaseInfo,
    RepositoryInfo,
    Snapshot,
    _estimate_minimum_request_count,
    build_report_document,
    compare_snapshots,
    load_snapshot,
    render_markdown_report,
    save_snapshot,
)


def sample_repository(repo_id: int, name: str, created_at: str) -> RepositoryInfo:
    return RepositoryInfo(
        id=repo_id,
        name=name,
        full_name=f"Sunwood-ai-labs/{name}",
        html_url=f"https://github.com/Sunwood-ai-labs/{name}",
        description=f"{name} description",
        is_private=False,
        is_fork=False,
        is_archived=False,
        created_at=created_at,
        updated_at=created_at,
        pushed_at=created_at,
    )


def sample_release(release_id: int, tag: str, created_at: str) -> ReleaseInfo:
    return ReleaseInfo(
        id=release_id,
        tag_name=tag,
        name=tag,
        html_url=f"https://github.com/Sunwood-ai-labs/example/releases/tag/{tag}",
        is_draft=False,
        is_prerelease=False,
        created_at=created_at,
        published_at=created_at,
    )


class MonitorTests(unittest.TestCase):
    def test_request_estimate_matches_repo_and_release_scan_shape(self) -> None:
        self.assertEqual(_estimate_minimum_request_count(707), 716)

    def test_large_account_requires_token_before_full_scan(self) -> None:
        class FakeClient(GitHubClient):
            def __init__(self) -> None:
                super().__init__(token=None)

            def _request_json(self, url: str):  # type: ignore[override]
                return (
                    {
                        "login": "Sunwood-ai-labs",
                        "type": "User",
                        "html_url": "https://github.com/Sunwood-ai-labs",
                        "public_repos": 707,
                    },
                    {},
                )

            def _paginate(self, path, params=None):  # type: ignore[override]
                raise AssertionError("_paginate should not be reached without a token")

        with self.assertRaises(GitHubApiError) as context:
            FakeClient().fetch_snapshot("Sunwood-ai-labs")

        self.assertIn("unauthenticated full scan", str(context.exception))

    def test_compare_snapshots_detects_new_repo_and_release(self) -> None:
        previous_repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        current_repo = sample_repository(2, "beta", "2026-03-20T00:00:00Z")
        previous = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 1,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[previous_repo],
            releases_by_repo={
                previous_repo.full_name: [sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")]
            },
        )
        current = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 2,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[previous_repo, current_repo],
            releases_by_repo={
                previous_repo.full_name: [
                    sample_release(11, "v1.1.0", "2026-03-20T03:00:00Z"),
                    sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z"),
                ],
                current_repo.full_name: [],
            },
        )

        comparison = compare_snapshots(previous, current)

        self.assertTrue(comparison["changed"])
        self.assertEqual([repo.full_name for repo in comparison["new_repositories"]], [current_repo.full_name])
        self.assertEqual(len(comparison["new_releases"]), 1)
        self.assertEqual(comparison["new_releases"][0]["release"].tag_name, "v1.1.0")

    def test_draft_release_is_reported_when_it_becomes_published(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        previous = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 1,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[repo],
            releases_by_repo={
                repo.full_name: [
                    ReleaseInfo(
                        id=10,
                        tag_name="v1.0.0",
                        name="v1.0.0",
                        html_url="https://github.com/Sunwood-ai-labs/alpha/releases/tag/v1.0.0",
                        is_draft=True,
                        is_prerelease=False,
                        created_at="2026-03-18T01:00:00Z",
                        published_at=None,
                    )
                ]
            },
        )
        current = Snapshot(
            account=previous.account,
            repositories=[repo],
            releases_by_repo={
                repo.full_name: [sample_release(10, "v1.0.0", "2026-03-18T02:00:00Z")]
            },
        )

        comparison = compare_snapshots(previous, current)

        self.assertEqual(len(comparison["new_releases"]), 1)
        self.assertEqual(comparison["new_releases"][0]["release"].id, 10)

    def test_new_draft_release_is_not_reported(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        previous = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 1,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[repo],
            releases_by_repo={repo.full_name: []},
        )
        current = Snapshot(
            account=previous.account,
            repositories=[repo],
            releases_by_repo={
                repo.full_name: [
                    ReleaseInfo(
                        id=12,
                        tag_name="v1.1.0",
                        name="v1.1.0",
                        html_url="https://github.com/Sunwood-ai-labs/alpha/releases/tag/v1.1.0",
                        is_draft=True,
                        is_prerelease=False,
                        created_at="2026-03-19T01:00:00Z",
                        published_at=None,
                    )
                ]
            },
        )

        comparison = compare_snapshots(previous, current)

        self.assertEqual(comparison["new_releases"], [])

    def test_bootstrap_run_is_not_reported_as_change(self) -> None:
        current = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 1,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[sample_repository(1, "alpha", "2026-03-18T00:00:00Z")],
            releases_by_repo={},
        )

        comparison = compare_snapshots(None, current)

        self.assertTrue(comparison["bootstrap"])
        self.assertFalse(comparison["changed"])

    def test_snapshot_roundtrip(self) -> None:
        snapshot = Snapshot(
            account={
                "login": "Sunwood-ai-labs",
                "type": "User",
                "html_url": "https://github.com/Sunwood-ai-labs",
                "public_repos": 1,
                "release_window": RECENT_RELEASE_WINDOW,
            },
            repositories=[sample_repository(1, "alpha", "2026-03-18T00:00:00Z")],
            releases_by_repo={
                "Sunwood-ai-labs/alpha": [sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")]
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            save_snapshot(path, snapshot)
            reloaded = load_snapshot(path)

        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded.account["login"], "Sunwood-ai-labs")
        self.assertEqual(reloaded.repositories[0].full_name, "Sunwood-ai-labs/alpha")
        self.assertEqual(reloaded.releases_by_repo["Sunwood-ai-labs/alpha"][0].tag_name, "v1.0.0")

    def test_markdown_render_includes_changes(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        release = sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")
        report = build_report_document(
            {
                "checked_at": "2026-03-21T00:00:00Z",
                "bootstrap": False,
                "changed": True,
                "account": {
                    "login": "Sunwood-ai-labs",
                    "type": "User",
                    "html_url": "https://github.com/Sunwood-ai-labs",
                    "public_repos": 1,
                    "release_window": RECENT_RELEASE_WINDOW,
                },
                "new_repositories": [repo],
                "new_releases": [{"repository": repo, "release": release}],
            },
            request_count=5,
            token_used=True,
            rate_limit={"min_remaining": 995},
        )

        markdown = render_markdown_report(report)

        self.assertIn("## New repositories", markdown)
        self.assertIn("## New releases", markdown)
        self.assertIn("Sunwood-ai-labs/alpha", markdown)
        self.assertIn("`v1.0.0`", markdown)

    def test_discord_payload_includes_repo_and_release(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        release = sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")
        report = build_report_document(
            {
                "checked_at": "2026-03-21T00:00:00Z",
                "bootstrap": False,
                "changed": True,
                "account": {
                    "login": "Sunwood-ai-labs",
                    "type": "User",
                    "html_url": "https://github.com/Sunwood-ai-labs",
                    "public_repos": 1,
                    "release_window": RECENT_RELEASE_WINDOW,
                },
                "new_repositories": [repo],
                "new_releases": [{"repository": repo, "release": release}],
            },
            request_count=5,
            token_used=True,
            rate_limit={"min_remaining": 995},
        )

        payload = build_discord_payload(report, max_items=5)
        embed = payload["embeds"][0]
        field_values = "\n".join(field["value"] for field in embed["fields"])

        self.assertEqual(embed["title"], "GitHub アカウント監視レポート")
        self.assertIn("新しい更新を検知しました", embed["description"])
        self.assertIn("Sunwood-ai-labs/alpha", field_values)
        self.assertIn("v1.0.0", field_values)

    def test_discord_dry_run_text_is_japanese_json(self) -> None:
        report = build_report_document(
            {
                "checked_at": "2026-03-21T00:00:00Z",
                "bootstrap": True,
                "changed": False,
                "account": {
                    "login": "Sunwood-ai-labs",
                    "type": "User",
                    "html_url": "https://github.com/Sunwood-ai-labs",
                    "public_repos": 1,
                    "release_window": RECENT_RELEASE_WINDOW,
                },
                "new_repositories": [],
                "new_releases": [],
            },
            request_count=1,
            token_used=True,
            rate_limit={"min_remaining": 999},
        )

        dry_run = build_discord_dry_run_text(report)

        self.assertIn("GitHub アカウント監視レポート", dry_run)
        self.assertIn("初回ベースラインを作成しました", dry_run)

    def test_thread_metadata_is_japanese(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        release = sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")
        report = build_report_document(
            {
                "checked_at": "2026-03-21T11:37:00Z",
                "bootstrap": False,
                "changed": True,
                "account": {
                    "login": "Sunwood-ai-labs",
                    "type": "User",
                    "html_url": "https://github.com/Sunwood-ai-labs",
                    "public_repos": 709,
                    "release_window": RECENT_RELEASE_WINDOW,
                },
                "new_repositories": [repo],
                "new_releases": [{"repository": repo, "release": release}],
            },
            request_count=1,
            token_used=True,
            rate_limit={"min_remaining": 999},
        )

        thread_name = build_thread_name(report)
        starter = build_thread_starter_content(report)

        self.assertIn("Sunwood-ai-labs", thread_name)
        self.assertIn("監視", thread_name)
        self.assertIn("Sunwood-ai-labs: 新しい更新を検知しました", starter)
        self.assertIn("Repo: Sunwood-ai-labs/alpha", starter)
        self.assertIn("Release: Sunwood-ai-labs/alpha / v1.0.0", starter)
        self.assertIn("新しい更新を検知しました", starter)

    def test_explainer_request_mentions_user_and_event(self) -> None:
        repo = sample_repository(1, "alpha", "2026-03-18T00:00:00Z")
        release = sample_release(10, "v1.0.0", "2026-03-18T01:00:00Z")
        report = build_report_document(
            {
                "checked_at": "2026-03-21T11:37:00Z",
                "bootstrap": False,
                "changed": True,
                "account": {
                    "login": "Sunwood-ai-labs",
                    "type": "User",
                    "html_url": "https://github.com/Sunwood-ai-labs",
                    "public_repos": 709,
                    "release_window": RECENT_RELEASE_WINDOW,
                },
                "new_repositories": [repo],
                "new_releases": [{"repository": repo, "release": release}],
            },
            request_count=1,
            token_used=True,
            rate_limit={"min_remaining": 999},
        )

        prompt = build_explainer_request(report, "123456789012345678")

        self.assertIn("<@123456789012345678>", prompt)
        self.assertIn("sunwood-community skill", prompt)
        self.assertIn("Release: Sunwood-ai-labs/alpha / v1.0.0", prompt)
        self.assertIn("投稿したリツイートのURL", prompt)
        self.assertNotIn("{mention}", prompt)
        self.assertNotIn("{event_lines}", prompt)


if __name__ == "__main__":
    unittest.main()
