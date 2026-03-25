<p align="center">
  <img src="./assets/scan-beacon.svg" alt="github-account-scanner icon" width="112" />
</p>

<p align="center">
  <strong>github-account-scanner</strong><br />
  Cloudflare Worker を主役にした GitHub App release 通知リポジトリです。
</p>

<p align="center">
  <a href="./README.md">English</a>
  |
  <a href="./README.ja.md"><strong>日本語</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/Sunwood-ai-labs/github-account-scanner/validate.yml?branch=main&label=validate&style=flat-square" alt="Validate workflow status" />
  <img src="https://img.shields.io/badge/runtime-Cloudflare%20Workers-F38020?style=flat-square" alt="Cloudflare Workers" />
  <img src="https://img.shields.io/badge/source-GitHub%20App-181717?style=flat-square" alt="GitHub App" />
  <img src="https://img.shields.io/badge/notify-Discord%20Bot%20API-5865F2?style=flat-square" alt="Discord Bot API" />
  <img src="https://img.shields.io/badge/test-node--test-5FA04E?style=flat-square" alt="node:test" />
  <img src="https://img.shields.io/badge/license-MIT-2EA043?style=flat-square" alt="MIT License" />
</p>

## 概要

`github-account-scanner` は Worker-first 構成に切り替えました。

現在の本番経路はこれだけです。

`GitHub App -> Cloudflare Worker -> Discord Bot API`

以前の Python polling CLI、ローカル scheduler、REST API 差分監視経路は削除しました。production 用として十分ではなかったため、この repository では今後サポートしません。

## 何をする Worker か

主実装は [`workers/github-app-discord-bot`](./workers/github-app-discord-bot) にあります。

対応している内容:

- GitHub App webhook の署名検証
- `release` の `published` だけを通知
- Discord の親メッセージ投稿、thread 作成、embed 投稿
- `test` / `production` プロファイル切り替え
- production 専用メンション
- mention user 設定時の AgentAGI 向け structured explainer prompt 投稿
- GitHub App installation token を使った release reaction 付与
- デバッグしやすい structured Worker logs
- Cloudflare KV を使った任意の重複抑止

AgentAGI 向け prompt はオプションです。本文には `skills/sunwood-community/prompts/*` の外部参照が含まれるため、メンション先の bot 側でその path を解決できる前提です。

## クイックスタート

まず Worker の依存を入れます。

```powershell
npm --prefix workers/github-app-discord-bot install
```

ローカル起動:

```powershell
copy workers\github-app-discord-bot\.dev.vars.example workers\github-app-discord-bot\.dev.vars
npm run dev
```

テスト:

```powershell
npm test
```

デプロイ:

```powershell
npm run deploy
```

ログ確認:

```powershell
npm run tail
```

## GitHub App 側の必須設定

- `Webhook` を有効化
- `Webhook URL` を `https://<worker>.workers.dev/webhook` に設定
- `Webhook secret` を `GITHUB_APP_WEBHOOK_SECRET` と一致させる
- subscribed event は `Release`
- repository permission は `Contents: Read`
- 監視したい repository に app を install

## Discord 側の必須設定

- `DISCORD_BOT_TOKEN`
- `DISCORD_PRODUCTION_CHANNEL_ID` または共通の `DISCORD_CHANNEL_ID`
- 必要なら `DISCORD_PRODUCTION_MENTION_USER_ID`
- Bot に `View Channel` `Send Messages` `Create Public Threads` `Send Messages in Threads` `Embed Links` を付与

## 環境変数

root の [`.env.example`](./.env.example) は Worker 前提の項目だけにしています。

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

`GITHUB_APP_PRIVATE_KEY` は GitHub から落とした PEM そのままでも、`\n` 形式の 1 行文字列でも使えます。

## 運用メモ

- `test` は `DISCORD_TEST_MENTION_USER_ID` を入れない限り production のメンションを継承しません
- release reaction は Discord 通知の後段で best-effort に実行します
- `WEBHOOK_STATE` がない場合は redelivery で二重通知することがあります
- `WEBHOOK_STATE` はあえて必須にしていません。重複抑止を有効にしたいときだけ、自分の KV namespace を作って `wrangler.toml` に追加してください
- KV ベースの重複抑止は真の同時到着には atomic ではありません

## リポジトリ構成

- [`workers/github-app-discord-bot/src/index.js`](./workers/github-app-discord-bot/src/index.js)
  Worker 本体
- [`workers/github-app-discord-bot/test/index.test.js`](./workers/github-app-discord-bot/test/index.test.js)
  Worker テスト
- [`workers/github-app-discord-bot/wrangler.toml`](./workers/github-app-discord-bot/wrangler.toml)
  Cloudflare 設定
- [`workers/github-app-discord-bot/README.md`](./workers/github-app-discord-bot/README.md)
  Worker 個別の詳細手順

## 検証

GitHub Actions は Node ベースの Worker テストだけを実行します。root の `npm test` も Worker のテストを呼び出します。

## 参考

- [GitHub App webhook docs](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/using-webhooks-with-github-apps)
- [Cloudflare Workers docs](https://developers.cloudflare.com/workers/)
- [Discord Bot API docs](https://discord.com/developers/docs/intro)
