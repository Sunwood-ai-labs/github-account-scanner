<p align="center">
  <img src="./assets/scan-beacon.svg" alt="github-account-scanner icon" width="112" />
</p>

<p align="center">
  <strong>github-account-scanner</strong><br />
  GitHub アカウントの新規公開リポジトリと新規公開 release を監視し、必要なら Discord へ通知するローカル運用向け CLI です。
</p>

<p align="center">
  <a href="./README.md">English</a>
  |
  <a href="./README.ja.md"><strong>日本語</strong></a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/actions/workflow/status/Sunwood-ai-labs/github-account-scanner/validate.yml?branch=main&label=validate&style=flat-square" alt="Validate workflow status" />
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/package-uv-6C47FF?style=flat-square" alt="uv package manager" />
  <img src="https://img.shields.io/badge/source-GitHub%20API-181717?style=flat-square" alt="GitHub API" />
  <img src="https://img.shields.io/badge/notify-Discord-5865F2?style=flat-square" alt="Discord notifications" />
  <img src="https://img.shields.io/badge/license-MIT-2EA043?style=flat-square" alt="MIT License" />
</p>

## ✨ 概要

`github-account-scanner` は、`Sunwood-ai-labs` のような GitHub アカウントをローカルから定期監視するための Python CLI です。

監視対象は次のとおりです。

- 新しく作成された公開リポジトリ
- 新しく公開された GitHub release
- 必要に応じた Discord 通知
- AgentAGI 向けの follow-up 解説 prompt

運用は CI 常駐ではなく、ローカル定期実行を前提にしています。

## 🔍 何を監視するか

- 対象ユーザーまたは organization 配下の公開リポジトリ一覧
- 各リポジトリの直近 `100` 件の release
- `draft release` から公開状態になった release

release は `100` 件に絞ることで、1 リポジトリあたり 1 API 呼び出しで監視しています。通常の定期実行には実用的ですが、1 回の実行間隔中に同じリポジトリで `100` 件を超える release が増えるケースでは、監視頻度を上げるかページネーション対応が必要です。

## 🧠 なぜ polling 方式か

GitHub には、他人のアカウント全体をそのまま監視できる ready-to-use webhook がありません。

そのため、この project では GitHub REST API を定期実行し、前回のローカル state と比較する方式を採っています。

## ⚙️ 前提条件

- Python `3.11+`
- `uv`
- 大規模アカウント向けの `GITHUB_TOKEN` または `GH_TOKEN`

2026-03-21 時点で `Sunwood-ai-labs` は `700` 件超の public repo を持っています。unauthenticated の GitHub REST API 制限では足りないため、release まで含めた本格運用には token 設定を強く推奨します。

## 🚀 クイックスタート

```powershell
uv sync
```

必要なら token を設定します。

```powershell
$env:GITHUB_TOKEN = "ghp_xxx"
```

初回 baseline を作るには:

```powershell
uv run github-scan check Sunwood-ai-labs
```

出力先を明示する例:

```powershell
uv run github-scan check Sunwood-ai-labs `
  --state-file state/sunwood-ai-labs.json `
  --json-report state/last-report.json `
  --markdown-report state/last-report.md
```

## ⏱️ ローカル定期実行

バックグラウンドで継続監視したい場合は、Python の scheduler runner を使います。

本体は [`scripts/run_scheduled_monitor.py`](./scripts/run_scheduled_monitor.py) で、次をまとめて実行します。

- 対象アカウントへの `check`
- `state/` 配下のレポート更新
- 差分があったときだけ Discord 通知
- `logs/scheduled-monitor/` への実行ログ保存

Windows Task Scheduler の登録は Python helper から行えます。

```powershell
.venv\Scripts\python.exe .\scripts\register_monitor_task.py --interval-minutes 15 --run-now
```

これで `github-account-scanner-monitor` という task が作成され、`15` 分おきに repo ローカルの Python 環境から監視が走ります。

リリース時のみ通知したい場合は、スケジューラ実行時に以下を指定します（環境変数方式も利用可）。

```powershell
$env:DISCORD_NOTIFY_RELEASES_ONLY = "true"
.venv\Scripts\python.exe .\scripts\run_scheduled_monitor.py --notify-releases-only
```

通知プロファイルを `production` / `test` で分けたい場合は、以下のように使えます。

```powershell
.venv\Scripts\python.exe .\scripts\run_scheduled_monitor.py --discord-profile production
.venv\Scripts\python.exe .\scripts\run_scheduled_monitor.py --discord-profile test
```

## 🔔 Discord 通知

`.env` または `.env.local` に `DISCORD_BOT_TOKEN` と `DISCORD_CHANNEL_ID` を設定すると、検知結果を Discord に送れます。

`DISCORD_CHANNEL_ID` には、チャンネルの ID 文字列（`1234567890...`）または Discord のチャンネル URL（例: `https://discord.com/channels/1234567890/1234567890`）を指定できます。

`test` と `production` を分けたい場合は `DISCORD_TEST_*` / `DISCORD_PRODUCTION_*` を使えます。`test` 側は `DISCORD_TEST_MENTION_USER_ID` を明示しない限り、本番用メンションを引き継ぎません。

change を検知したときは次の流れで通知します。

- 親チャンネルへ短い要約を投稿
- イベント単位の thread を作成
- thread 内へ詳細 embed を投稿

`DISCORD_EXPLAINER_USER_ID` も設定すると、その user を thread 内でメンションし、GitHub 通知向けの structured prompt を追加で送ります。参照されるテンプレートは次の 3 つです。

- [`src/github_scan/prompts/discord_explainer_request.md`](./src/github_scan/prompts/discord_explainer_request.md)
- [`src/github_scan/prompts/discord_explainer_repository.md`](./src/github_scan/prompts/discord_explainer_repository.md)
- [`src/github_scan/prompts/discord_explainer_release.md`](./src/github_scan/prompts/discord_explainer_release.md)

現在の prompt では、下流 Bot が作る投稿文章は英語で出すように指示しています。

これらのテンプレートは、下流の AgentAGI 実行環境で `skills/sunwood-community/prompts/*` を参照できる前提です。別環境の bot で使う場合は、その prompt path を先に調整してください。

`DISCORD_WEBHOOK_URL` 互換経路も残していますが、bot token がある場合は Bot API を優先します。

通知 payload の dry-run:

```powershell
uv run github-scan notify-discord --report-file state/last-report.json --dry-run
```

## 📁 出力ファイル

- `state/<account>.json`
  差分判定に使う保存済み snapshot
- `state/last-report.json`
  最新の機械可読レポート
- `state/last-report.md`
  運用確認しやすい Markdown レポート

state 配下は実行時生成物なので、git では追跡しません。

## 🧪 ローカル開発

基本的な確認コマンド:

```powershell
uv run python -m unittest discover -s tests
uv run github-scan --help
```

手動の end-to-end 確認例:

```powershell
uv run github-scan check Sunwood-ai-labs
uv run github-scan notify-discord --report-file state/last-report.json
```

## ⚠️ 運用メモ

- 本番運用はローカル定期実行向けです
- GitHub Actions は検証専用で、本番監視ランタイムには使いません
- 監視対象は公開面のみです
- draft release は公開されるまで通知しません

## 📚 参考

- [Repositories REST API](https://docs.github.com/rest/repos/repos)
- [Releases REST API](https://docs.github.com/rest/releases)
- [REST API rate limits](https://docs.github.com/enterprise-cloud@latest/rest/overview/rate-limits-for-the-rest-api)
- [Actions limits (`GITHUB_TOKEN`)](https://docs.github.com/en/enterprise-cloud@latest/actions/reference/actions-limits)

## GitHub App Webhook Mode

GitHub App をインストールできる環境では、こちらが優先の運用モードです。

GitHub App 側では以下を設定します。

- `Webhook` を有効化し、このサービスを指す公開 URL を設定
- `Webhook secret` を `GITHUB_APP_WEBHOOK_SECRET` と一致させる
- repository permission `Contents: Read`
- subscribed webhook event `Release`
- 監視したい repository 群へインストール

Webhook 受信サーバーは次で起動できます。

```powershell
uv run github-scan serve-github-app-webhook `
  --host 0.0.0.0 `
  --port 8787 `
  --path /github/webhook `
  --discord-profile production
```

## Cloudflare Worker Deployment

GitHub App の webhook URL を公開運用するなら、`workers/github-app-discord-bot` の Cloudflare Worker 版を主線として使います。

この構成は [`onizuka-agi-co/github-app-worker`](https://github.com/onizuka-agi-co/github-app-worker) を参考にしつつ、`pull_request -> PR comment` ではなく `release -> Discord Bot API` に合わせて組み替えています。

対応している内容:

- `GitHub App -> webhook -> Discord Bot API`
- release イベントだけを通知
- `test` / `production` プロファイル切り替え
- `test` では production 用メンションを継承しない
- Cloudflare KV を使った任意の重複抑止

ローカル開発:

```powershell
cd workers/github-app-discord-bot
copy .dev.vars.example .dev.vars
npm install
npm run dev
```

デプロイ:

```powershell
cd workers/github-app-discord-bot
npm install
npm run deploy
```

GitHub App 側の設定:

- `Webhook URL`: `https://<your-worker>.workers.dev/webhook`
- `Webhook secret`: `GITHUB_APP_WEBHOOK_SECRET` と同じ値
- subscribed webhook event: `Release`
- repository permission: `Contents: Read`

release 通知だけであれば GitHub API を追加で叩かないので、GitHub App private key は不要です。

通知実験では `--discord-profile test` を使うと、本番用メンションを継承しません。
