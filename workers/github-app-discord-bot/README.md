# GitHub App Discord Bot Worker

Cloudflare Worker implementation for:

`GitHub App -> webhook -> Discord Bot API`

This worker is based on the same deployment shape as [`onizuka-agi-co/github-app-worker`](https://github.com/onizuka-agi-co/github-app-worker), but it is adapted for release notifications instead of PR comments.

## What It Does

- accepts GitHub App webhook deliveries
- verifies `X-Hub-Signature-256`
- ignores non-release events
- sends release notifications to Discord using the Bot API
- emits structured Worker logs for deliveries, duplicate suppression, Discord sends, and GitHub reaction stamping
- can stamp a reaction onto the detected GitHub release notes
- supports `production` and `test` delivery profiles
- never inherits production mentions in `test` unless explicitly configured
- can optionally dedupe deliveries via Cloudflare KV

## Required GitHub App Settings

- `Webhook` enabled
- `Webhook URL` set to `https://<worker>.workers.dev/webhook`
- `Webhook secret` set and stored as `GITHUB_APP_WEBHOOK_SECRET`
- repository event subscription: `Release`
- repository permission: `Contents: Read`

The base release notification path does not need the App private key. If you enable release-reaction stamping, the worker also calls the GitHub API and must be given `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY`.

If you want the worker to stamp the detected release notes with a GitHub reaction, set:

- `GITHUB_APP_ID`
- `GITHUB_APP_PRIVATE_KEY`
- optional `GITHUB_RELEASE_REACTION` such as `eyes`, `rocket`, or `hooray`

GitHub's reactions API accepts GitHub App installation access tokens, and the endpoint does not require extra repository permissions beyond the installation token itself.
The worker runs reaction stamping as a best-effort background step after the Discord send succeeds, so webhook delivery is not blocked by a slow GitHub API call.

## Local Development

```powershell
cd workers/github-app-discord-bot
copy .dev.vars.example .dev.vars
npm install
npm run dev
```

## Deploy

```powershell
cd workers/github-app-discord-bot
npm install
npm run deploy
```

Optional secrets via Wrangler:

```powershell
npx wrangler secret put GITHUB_APP_WEBHOOK_SECRET
npx wrangler secret put DISCORD_BOT_TOKEN
npx wrangler secret put DISCORD_CHANNEL_ID
npx wrangler secret put GITHUB_APP_ID
npx wrangler secret put GITHUB_APP_PRIVATE_KEY
npx wrangler secret put GITHUB_RELEASE_REACTION
npx wrangler secret put WORKER_LOG_LEVEL
```

`GITHUB_APP_PRIVATE_KEY` accepts the GitHub-downloaded PEM as-is or a single-line value with `\n` escapes.

Recommended logging setup:

- `WORKER_LOG_LEVEL=debug` while bringing the app up
- use `npm run tail` or the Workers dashboard logs while testing releases

## Test / Production Profiles

- `DISCORD_DELIVERY_PROFILE=production`
  Uses `DISCORD_PRODUCTION_*`, then falls back to shared `DISCORD_*`
- `DISCORD_DELIVERY_PROFILE=test`
  Uses `DISCORD_TEST_*`, then falls back to shared `DISCORD_*`
- `test` does not inherit `DISCORD_PRODUCTION_MENTION_USER_ID`

## Dedupe

If you bind `WEBHOOK_STATE`, the worker stores:

- `delivery:<github-delivery-id>`
- `release:<repo>#<release-id>`

Without KV, the worker still runs, but duplicate redeliveries can notify Discord again.
