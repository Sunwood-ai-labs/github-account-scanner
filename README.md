<p align="center">
  <img src="./assets/scan-beacon.svg" alt="github-account-scanner icon" width="112" />
</p>

<p align="center">
  <strong>github-account-scanner</strong><br />
  Worker-first GitHub App release notifications for Discord Bot API.
</p>

<p align="center">
  <a href="./README.md"><strong>English</strong></a>
  |
  <a href="./README.ja.md">Japanese</a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/Sunwood-ai-labs/github-account-scanner/validate.yml?branch=main&label=validate&style=flat-square" alt="Validate workflow status" />
  <img src="https://img.shields.io/badge/runtime-Cloudflare%20Workers-F38020?style=flat-square" alt="Cloudflare Workers" />
  <img src="https://img.shields.io/badge/source-GitHub%20App-181717?style=flat-square" alt="GitHub App" />
  <img src="https://img.shields.io/badge/notify-Discord%20Bot%20API-5865F2?style=flat-square" alt="Discord Bot API" />
  <img src="https://img.shields.io/badge/test-node--test-5FA04E?style=flat-square" alt="node:test" />
  <img src="https://img.shields.io/badge/license-MIT-2EA043?style=flat-square" alt="MIT License" />
</p>

## Overview

`github-account-scanner` is now a Worker-first repository.

The supported production path is:

`GitHub App -> Cloudflare Worker -> Discord Bot API`

This repository no longer supports the old Python polling flow. The polling CLI, local scheduler, and REST API diffing path were removed because they were not reliable enough for the intended production use.

## What The Worker Does

The main runtime lives under [`workers/github-app-discord-bot`](./workers/github-app-discord-bot).

It handles:

- GitHub App webhook delivery verification with `X-Hub-Signature-256`
- release-only filtering with `published` action handling
- Discord parent message posting, thread creation, and release embeds
- `test` / `production` delivery profiles
- production-only mention routing
- structured AgentAGI explainer prompt delivery when a mention user is configured
- optional GitHub release reaction stamping via the GitHub App installation token
- structured Worker logs for debugging
- optional KV-based duplicate suppression

The AgentAGI explainer prompt is optional and assumes the downstream bot can resolve the external `skills/sunwood-community/prompts/*` references included in the message.

## Quick Start

Install the Worker dependencies:

```powershell
npm --prefix workers/github-app-discord-bot install
```

Run the Worker locally:

```powershell
copy workers\github-app-discord-bot\.dev.vars.example workers\github-app-discord-bot\.dev.vars
npm run dev
```

Run the Worker tests:

```powershell
npm test
```

Deploy:

```powershell
npm run deploy
```

Tail logs:

```powershell
npm run tail
```

## Required GitHub App Settings

- `Webhook` enabled
- `Webhook URL` set to `https://<worker>.workers.dev/webhook`
- `Webhook secret` stored as `GITHUB_APP_WEBHOOK_SECRET`
- repository event subscription: `Release`
- repository permission: `Contents: Read`
- installation scope set to the repositories you want to monitor

## Required Discord Settings

- a bot token in `DISCORD_BOT_TOKEN`
- a production channel in `DISCORD_PRODUCTION_CHANNEL_ID` or shared `DISCORD_CHANNEL_ID`
- optional production mention target in `DISCORD_PRODUCTION_MENTION_USER_ID`
- `View Channel`, `Send Messages`, `Create Public Threads`, `Send Messages in Threads`, and `Embed Links` permissions for the bot

## Environment Variables

The root [`.env.example`](./.env.example) documents the Worker-focused settings:

- `GITHUB_APP_WEBHOOK_SECRET`
- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- `GITHUB_RELEASE_REACTION`
- `WORKER_LOG_LEVEL`
- `DISCORD_BOT_TOKEN`
- `DISCORD_DELIVERY_PROFILE`
- `DISCORD_CHANNEL_ID`
- `DISCORD_PRODUCTION_CHANNEL_ID`
- `DISCORD_TEST_CHANNEL_ID`
- `DISCORD_PRODUCTION_MENTION_USER_ID`
- `DISCORD_TEST_MENTION_USER_ID`

`GITHUB_APP_PRIVATE_KEY` accepts the GitHub-downloaded PEM as-is or a single-line value with `\n` escapes.

## Production Notes

- `test` does not inherit production mentions unless `DISCORD_TEST_MENTION_USER_ID` is set
- release reaction stamping is best-effort and runs after Discord delivery
- if `WEBHOOK_STATE` is not bound, redeliveries can notify Discord again
- `WEBHOOK_STATE` is intentionally optional; provision your own KV namespace before enabling dedupe in `wrangler.toml`
- KV duplicate suppression is still not atomic under true concurrent delivery

## Repository Layout

- [`workers/github-app-discord-bot/src/index.js`](./workers/github-app-discord-bot/src/index.js)
  Worker runtime
- [`workers/github-app-discord-bot/test/index.test.js`](./workers/github-app-discord-bot/test/index.test.js)
  Worker tests
- [`workers/github-app-discord-bot/wrangler.toml`](./workers/github-app-discord-bot/wrangler.toml)
  Cloudflare deployment config
- [`workers/github-app-discord-bot/README.md`](./workers/github-app-discord-bot/README.md)
  Worker-specific setup notes

## Validation

GitHub Actions now validates the Worker with Node only. The root `npm test` command delegates to the Worker test suite.

## Reference

- [GitHub App webhook docs](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps)
- [Cloudflare Workers docs](https://developers.cloudflare.com/workers/)
- [Discord Bot API docs](https://discord.com/developers/docs/intro)
