# GitHub App Discord Bot Worker

Cloudflare Worker implementation for:

`GitHub App -> webhook -> Discord Bot API`

This worker is based on the same deployment shape as [`onizuka-agi-co/github-app-worker`](https://github.com/onizuka-agi-co/github-app-worker), but it is adapted for release notifications instead of PR comments.

## What It Does

- accepts GitHub App webhook deliveries
- verifies `X-Hub-Signature-256`
- ignores non-release events
- sends release notifications to Discord using the Bot API
- supports `production` and `test` delivery profiles
- never inherits production mentions in `test` unless explicitly configured
- can optionally dedupe deliveries via Cloudflare KV

## Required GitHub App Settings

- `Webhook` enabled
- `Webhook URL` set to `https://<worker>.workers.dev/webhook`
- `Webhook secret` set and stored as `GITHUB_APP_WEBHOOK_SECRET`
- repository event subscription: `Release`
- repository permission: `Contents: Read`

This worker does not call the GitHub API, so it does not need the App private key for the release notification flow.

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
```

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
