# github-scan

`Sunwood-ai-labs` のような GitHub アカウントを監視して、新規リポジトリ作成と新規リリース公開を検知するための小さな Python ツールです。

このリポジトリには、ローカルで実行できる CLI が入っています。

## 何を監視するか

- 対象アカウント配下の公開リポジトリ一覧
- 各リポジトリの直近 100 件の release 一覧

`draft release` は通知対象にせず、公開された時点で初めて「新規 release」として扱います。

直近 100 件に絞ることで、1 リポジトリにつき 1 API 呼び出しで release 監視を済ませています。今回の初版は「毎時スキャン」前提です。この前提なら通常の監視用途では十分ですが、1 回の実行間隔のあいだに同じリポジトリで 100 件を超える release が増える特殊ケースは想定していません。その可能性があるなら、監視頻度を上げるか、release のページネーション対応を追加してください。

## なぜ polling 方式か

GitHub は「他人のアカウント全体」に対して、そのまま使える webhook を提供していません。なので今回は GitHub REST API を定期的に叩いて、前回スナップショットとの差分を取る方式にしています。

## 前提

- Python は `uv` で実行します
- release 監視まで有効にするなら `GITHUB_TOKEN` か `GH_TOKEN` の設定を強く推奨します

2026-03-21 時点で `Sunwood-ai-labs` は public repo が 707 件あります。unauthenticated の REST API は 1 時間あたり 60 リクエストなので、release まで含めた監視には足りません。ローカル実行でも `GITHUB_TOKEN` か `GH_TOKEN` を設定して使う前提です。

このため、このツールは大規模アカウントを token なしでフルスキャンしようとした場合、途中で待ってから失敗するのではなく、事前チェックで止めるようにしています。

## セットアップ

```powershell
uv sync
```

必要なら token を設定します。

```powershell
$env:GITHUB_TOKEN = "ghp_xxx"
```

## 使い方

初回実行では baseline を作ります。初回は「既存のものを新規」とは扱いません。

```powershell
uv run github-scan check Sunwood-ai-labs
```

明示的に出力先を指定する例です。

```powershell
uv run github-scan check Sunwood-ai-labs `
  --state-file state/sunwood-ai-labs.json `
  --json-report state/last-report.json `
  --markdown-report state/last-report.md
```

## 出力

- `state/<account>.json`
  前回までに観測済みのスナップショット
- `state/last-report.json`
  今回の差分結果
- `state/last-report.md`
  通知にそのまま使いやすい Markdown 版

## ローカル運用

このツールはローカル定期実行を前提にしています。Windows ならタスク スケジューラなどで `uv run github-scan check ...` を定期実行するのが素直です。

## Discord notification

Discord にも通知したい場合は、`.env` か `.env.local` に `DISCORD_BOT_TOKEN` と `DISCORD_CHANNEL_ID` を追加してください。change 検知時は、親チャンネルに短い通知を出し、投稿ごとに thread を作成して、その中に日本語の Embed 詳細を送ります。

互換用に `DISCORD_WEBHOOK_URL` も残していますが、`DISCORD_BOT_TOKEN` と `DISCORD_CHANNEL_ID` がある場合は Bot API を優先します。

ローカルで通知文面だけ確認したい場合は、次の dry-run が使えます。

```powershell
uv run github-scan notify-discord --report-file state/last-report.json --dry-run
```

## ローカル確認の流れ

```powershell
uv run github-scan check Sunwood-ai-labs
uv run python -m unittest discover -s tests
```

## 参考

- Repositories REST API: https://docs.github.com/rest/repos/repos
- Releases REST API: https://docs.github.com/rest/releases
- Actions schedule event: https://docs.github.com/en/enterprise-cloud@latest/actions/reference/events-that-trigger-workflows
- REST API rate limits: https://docs.github.com/enterprise-cloud@latest/rest/overview/rate-limits-for-the-rest-api
- Actions limits (`GITHUB_TOKEN`): https://docs.github.com/en/enterprise-cloud@latest/actions/reference/actions-limits
