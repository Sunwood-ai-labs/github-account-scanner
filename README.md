<p align="center">
  <img src="./assets/scan-beacon.svg" alt="github-account-scanner icon" width="112" />
</p>

<p align="center">
  <strong>github-account-scanner</strong><br />
  Monitor a GitHub account for newly created public repositories and published releases, then fan out Discord alerts.
</p>

<p align="center">
  <a href="./README.md"><strong>English</strong></a>
  |
  <a href="./README.ja.md">日本語</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/Sunwood-ai-labs/github-account-scanner/validate.yml?branch=main&label=validate&style=flat-square" alt="Validate workflow status" />
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/package-uv-6C47FF?style=flat-square" alt="uv package manager" />
  <img src="https://img.shields.io/badge/source-GitHub%20API-181717?style=flat-square" alt="GitHub API" />
  <img src="https://img.shields.io/badge/notify-Discord-5865F2?style=flat-square" alt="Discord notifications" />
  <img src="https://img.shields.io/badge/license-MIT-2EA043?style=flat-square" alt="MIT License" />
</p>

## ✨ Overview

`github-account-scanner` is a local-first Python CLI for watching a GitHub account such as `Sunwood-ai-labs`.

It tracks:

- newly created public repositories
- newly published GitHub releases
- optional Discord notifications with per-event threads
- optional AgentAGI mention prompts for follow-up explainers

The repository is intentionally optimized for local scheduled runs instead of CI-based production monitoring.

## 🔍 What It Monitors

- the full list of public repositories under a target user or organization
- up to the latest `100` releases per repository
- transitions from `draft release` to published release

That `100 release` window keeps the release scan to a single API request per repository. It is a practical tradeoff for recurring scans, but if one repository can publish more than `100` releases between runs, you should either scan more frequently or extend the pagination logic.

## 🧠 Why Polling

GitHub does not provide a ready-to-use webhook for monitoring another account's entire public repository surface.

Because of that, this project uses periodic polling with the GitHub REST API and compares the latest snapshot against the saved local state.

## ⚙️ Requirements

- Python `3.11+`
- `uv`
- `GITHUB_TOKEN` or `GH_TOKEN` for large accounts

As of March 21, 2026, `Sunwood-ai-labs` already had more than `700` public repositories. Unauthenticated GitHub REST API limits are too small for a complete repository-plus-release scan, so authenticated runs are strongly recommended.

## 🚀 Quick Start

```powershell
uv sync
```

Set a GitHub token when needed:

```powershell
$env:GITHUB_TOKEN = "ghp_xxx"
```

Create the initial baseline:

```powershell
uv run github-scan check Sunwood-ai-labs
```

Write the latest report explicitly:

```powershell
uv run github-scan check Sunwood-ai-labs `
  --state-file state/sunwood-ai-labs.json `
  --json-report state/last-report.json `
  --markdown-report state/last-report.md
```

## ⏱️ Local Scheduler

Use the Python scheduler runner when you want the monitor to keep checking in the background on your machine.

The scheduled runner lives at [`scripts/run_scheduled_monitor.py`](./scripts/run_scheduled_monitor.py) and performs:

- one `check` run against the configured account
- report updates under `state/`
- Discord notification only when the new report actually contains changes
- log output under `logs/scheduled-monitor/`

Register the Windows Scheduled Task with the Python helper:

```powershell
.venv\Scripts\python.exe .\scripts\register_monitor_task.py --interval-minutes 15 --run-now
```

That creates a task named `github-account-scanner-monitor` which launches the repo-local Python environment on a `15` minute cadence.

## 🔔 Discord Notifications

Add `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` to `.env` or `.env.local` to send notifications into Discord.

When a change is detected, the notifier:

- posts a compact parent message in the target channel
- creates a dedicated thread for that event
- posts a detailed embed inside the thread

If you also set `DISCORD_EXPLAINER_USER_ID`, the notifier mentions that user in the thread and posts a structured GitHub-notification prompt that references:

- [`src/github_scan/prompts/discord_explainer_request.md`](./src/github_scan/prompts/discord_explainer_request.md)
- [`src/github_scan/prompts/discord_explainer_repository.md`](./src/github_scan/prompts/discord_explainer_repository.md)
- [`src/github_scan/prompts/discord_explainer_release.md`](./src/github_scan/prompts/discord_explainer_release.md)

That prompt currently asks the downstream bot to prepare the outgoing post in English.

Those prompt templates assume the downstream AgentAGI environment can resolve the referenced `skills/sunwood-community/prompts/*` paths. If your explainer bot runs elsewhere, adjust those prompt paths before enabling explainer mentions.

The legacy `DISCORD_WEBHOOK_URL` path is still available, but Bot API delivery is preferred whenever bot token settings exist.

Preview the notification payload locally:

```powershell
uv run github-scan notify-discord --report-file state/last-report.json --dry-run
```

## 📁 Output Files

- `state/<account>.json`
  Saved snapshot used for change detection
- `state/last-report.json`
  Latest machine-readable diff result
- `state/last-report.md`
  Latest Markdown summary for operator review

State artifacts are treated as runtime output and are intentionally ignored by git.

## 🧪 Local Development

Run the main verification flow:

```powershell
uv run python -m unittest discover -s tests
uv run github-scan --help
```

Typical manual end-to-end loop:

```powershell
uv run github-scan check Sunwood-ai-labs
uv run github-scan notify-discord --report-file state/last-report.json
```

## ⚠️ Operating Notes

- this project is designed for local recurring execution, such as Windows Task Scheduler
- GitHub Actions is used only for validation, not as the production watcher runtime
- repository and release detection is public-surface only
- draft releases are ignored until they become published

## 📚 References

- [Repositories REST API](https://docs.github.com/rest/repos/repos)
- [Releases REST API](https://docs.github.com/rest/releases)
- [REST API rate limits](https://docs.github.com/enterprise-cloud@latest/rest/overview/rate-limits-for-the-rest-api)
- [Actions limits (`GITHUB_TOKEN`)](https://docs.github.com/en/enterprise-cloud@latest/actions/reference/actions-limits)
