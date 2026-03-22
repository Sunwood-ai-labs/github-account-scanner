# Release QA Inventory

## Release Context

- repository: `github-account-scanner`
- release tag: `v0.1.0`
- compare range: `<none>; initial release mode from root commit f77237879e0dc1f9903b2e6866cd82510d779b4b to tagged commit d2128724e02626c2a903ee9ed826ccf9abc50e7b`
- requested outputs: GitHub release body, GitHub tag, GitHub release publication
- validation commands run: `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\collect-release-context.ps1 -Target HEAD`, `uv run python -m unittest discover -s tests`, `uv run github-scan --help`, `uv build`, `uv venv <temp>`, `uv pip install --python <temp-venv-python> dist/github_scan-0.1.0-py3-none-any.whl`, `github-scan check octocat ...`, `github-scan notify-discord --report-file ... --dry-run`, `gh release view v0.1.0 --json url,name,body,publishedAt,tagName,targetCommitish`
- release URLs: `https://github.com/Sunwood-ai-labs/github-account-scanner/releases/tag/v0.1.0`

## Claim Matrix

| claim | code refs | validation refs | docs surfaces touched | scope |
| --- | --- | --- | --- | --- |
| Initial release ships a local-first account scanner that snapshots public repositories, scans the latest 100 releases per repository, and compares snapshots into change reports | `src/github_scan/monitor.py:17`, `src/github_scan/monitor.py:194`, `src/github_scan/monitor.py:272`, `src/github_scan/monitor.py:341`, `src/github_scan/monitor.py:417` | `tests/test_monitor.py:61`, `tests/test_monitor.py:126`, `uv run python -m unittest discover -s tests` | `README.md`, `README.ja.md` | steady_state |
| Initial release ships Discord delivery via embeds, event threads, and optional explainer prompts through the CLI notify path | `src/github_scan/discord_webhook.py:77`, `src/github_scan/discord_webhook.py:163`, `src/github_scan/discord_webhook.py:265`, `src/github_scan/discord_webhook.py:327`, `src/github_scan/cli.py:180` | `tests/test_monitor.py:275`, `tests/test_monitor.py:366`, `uv run python -m unittest discover -s tests` | `README.md`, `README.ja.md`, `.env.example` | steady_state |
| Initial release includes public-facing packaging and verification surfaces for a reusable repository | `.github/workflows/validate.yml:1`, `.github/workflows/validate.yml:34`, `.github/workflows/validate.yml:37`, `.github/workflows/validate.yml:40`, `pyproject.toml:3`, `pyproject.toml:7`, `pyproject.toml:25`, `LICENSE` | `uv run github-scan --help`, `uv build` | `README.md`, `README.ja.md` | steady_state |

## Steady-State Docs Review

| surface | status | evidence |
| --- | --- | --- |
| README.md | pass | Reviewed the English public overview, quick start, Discord notification flow, and local-first operating notes against `src/github_scan/monitor.py`, `src/github_scan/cli.py`, and `src/github_scan/discord_webhook.py`; no further truth-sync change was needed for v0.1.0. |
| README.ja.md | pass | Reviewed the Japanese quick start, Discord guidance, and operating notes against the same implementation surfaces; no additional release-specific edits were required before tagging. |
| .env.example | pass | Reviewed the example environment variables against `src/github_scan/cli.py:32` and the current notify path to confirm the documented token and channel variables still match shipped behavior. |

## QA Inventory

| criterion_id | status | evidence |
| --- | --- | --- |
| compare_range | pass | `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\collect-release-context.ps1 -Target HEAD` reported `<none>; initial release mode`, and `git show --stat --summary v0.1.0` confirmed the tag resolves to merge commit `d2128724e02626c2a903ee9ed826ccf9abc50e7b`. |
| release_claims_backed | pass | Release notes were drafted from `src/github_scan/monitor.py`, `src/github_scan/cli.py`, `src/github_scan/discord_webhook.py`, `.github/workflows/validate.yml`, `pyproject.toml`, `LICENSE`, and the unit tests instead of commit subjects alone. |
| docs_release_notes | not_applicable | The repository has no `docs/` publishing surface or live documentation site; the release body is the canonical release note for `v0.1.0`. |
| companion_walkthrough | not_applicable | There is no docs site or article surface to host a companion walkthrough page for this repository. |
| operator_claims_extracted | pass | The claim matrix above extracts operator-facing claims for scanning, Discord notifications, and validation/package surfaces. |
| impl_sensitive_claims_verified | pass | Verified implementation-sensitive claims against `src/github_scan/monitor.py`, `src/github_scan/cli.py`, `src/github_scan/discord_webhook.py`, and matching tests in `tests/test_monitor.py`. |
| steady_state_docs_reviewed | pass | Reviewed `README.md`, `README.ja.md`, and `.env.example` in the steady-state docs table above. |
| claim_scope_precise | pass | Release wording was kept specific to the `check` and `notify-discord` CLI paths, Discord thread delivery, and validation-only CI. |
| latest_release_links_updated | not_applicable | The repository does not expose a latest-release landing page, release index, or docs navigation pointer that needed an update. |
| docs_assets_committed_before_tag | not_applicable | No docs-backed release pages or publish-only assets were created for this release because the repository has no docs surface. |
| docs_deployed_live | not_applicable | No docs deployment exists for this repository. |
| tag_local_remote | pass | `git show --stat --summary v0.1.0` resolved locally, and `git push origin refs/tags/v0.1.0` published the tag to GitHub. |
| github_release_verified | pass | `gh release create v0.1.0 --repo Sunwood-ai-labs/github-account-scanner --title "v0.1.0" --notes-file tmp/release-notes-v0.1.0.md` succeeded, and `gh release view v0.1.0 --json url,name,body,publishedAt,tagName,targetCommitish` returned the expected published body and URL. |
| validation_commands_recorded | pass | Validation commands are recorded in Release Context and were executed during this release task before GitHub publication. |
| publish_date_verified | pass | `gh release view v0.1.0 --json publishedAt` returned `2026-03-22T13:19:36Z`, and no date was hardcoded before publication. |

## Notes

- blockers: none
- waivers: docs-backed release notes and companion walkthrough skipped because there is no docs publishing surface.
- follow-up docs tasks: none for `v0.1.0`; steady-state README surfaces already reflect the shipped behavior.
