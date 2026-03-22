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

## 🔔 Discord 通知

`.env` または `.env.local` に `DISCORD_BOT_TOKEN` と `DISCORD_CHANNEL_ID` を設定すると、検知結果を Discord に送れます。

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
