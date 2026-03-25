# github-account-scanner v0.2.0

![github-account-scanner v0.2.0 release header](https://raw.githubusercontent.com/Sunwood-ai-labs/github-account-scanner/v0.2.0/assets/release-header-v0.2.0.svg)

Release covering the shipped changes from `v0.1.0` to `v0.2.0`.

## Highlights

- Replaced the previous local Python polling path with the supported production flow: `GitHub App -> Cloudflare Worker -> Discord Bot API`.
- Added a dedicated Worker runtime that verifies GitHub App webhook signatures, filters release deliveries to the `published` action, posts Discord parent messages plus release threads, and keeps `test` and `production` routing separate.
- Added production mention routing with the structured AgentAGI explainer prompt so release threads can fan out into downstream explanation workflows without leaking production mentions into `test`.

## Tooling And Automation

- Added best-effort GitHub release reaction stamping via GitHub App installation tokens and deferred the stamp so Discord delivery does not block on the GitHub API.
- Added structured Worker logs for delivery receipt, dedupe decisions, Discord sends, and release reaction execution to make Cloudflare debugging practical.
- Added optional KV-backed duplicate suppression for release deliveries and narrowed release notifications to the canonical `published` action to prevent duplicate Discord posts.
- Replaced the old Python validation path with root `npm` entrypoints and a Node-only GitHub Actions workflow that installs Worker dependencies and runs the Worker test suite.

## Docs And Assets

- Rewrote the English and Japanese READMEs so the repository is explicitly Worker-first and no longer advertises the removed Python polling flow.
- Added Worker-specific setup notes under `workers/github-app-discord-bot/README.md` and refreshed `.env.example` for GitHub App auth, release reactions, profile routing, and mention targets.
- Added a versioned release header SVG derived from the repository scan beacon branding for `v0.2.0`.

## Validation

- `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\verify-svg-assets.ps1 -RepoPath . -Path assets\scan-beacon.svg,assets\release-header-v0.2.0.svg`
- `npm test`

## Upgrade Notes

- The old Python polling CLI, scheduler scripts, and Python packaging metadata are no longer part of the supported release payload.
- If you want release-note reaction stamping, configure `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY`; the base Discord notification flow still works without them.
- `WEBHOOK_STATE` remains optional. Without a KV binding, GitHub redeliveries can still notify Discord again.
