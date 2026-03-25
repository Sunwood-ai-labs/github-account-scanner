# Release QA Inventory

## Release Context

- repository: `github-account-scanner`
- release tag: `v0.2.0`
- compare range: `v0.1.0..v0.2.0`
- requested outputs: GitHub release body, GitHub tag, GitHub release publication, QA inventory
- validation commands run: `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\collect-release-context.ps1 -Tag v0.2.0 -BaseTag v0.1.0`, `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\verify-svg-assets.ps1 -RepoPath . -Path assets\scan-beacon.svg,assets\release-header-v0.2.0.svg`, `npm test`, `git rev-parse 'v0.2.0^{commit}'`, `git ls-remote --tags origin refs/tags/v0.2.0`, `curl.exe -I -L https://raw.githubusercontent.com/Sunwood-ai-labs/github-account-scanner/v0.2.0/assets/release-header-v0.2.0.svg`, `gh release create v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --title "v0.2.0" --notes-file tmp/release-notes-v0.2.0.md`, `gh release view v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --json url,name,body,publishedAt,tagName,targetCommitish`
- release URLs: `https://github.com/Sunwood-ai-labs/github-account-scanner/releases/tag/v0.2.0`

## Claim Matrix

| claim | code refs | validation refs | docs surfaces touched | scope |
| --- | --- | --- | --- | --- |
| v0.2.0 ships the supported Worker-first production path for GitHub App release webhooks to Discord, including `published`-only filtering and `test`/`production` routing | `workers/github-app-discord-bot/src/index.js:309`, `workers/github-app-discord-bot/src/index.js:434`, `workers/github-app-discord-bot/src/index.js:451`, `workers/github-app-discord-bot/src/index.js:514`, `workers/github-app-discord-bot/src/index.js:687`, `workers/github-app-discord-bot/src/index.js:801` | `workers/github-app-discord-bot/test/index.test.js:162`, `workers/github-app-discord-bot/test/index.test.js:177`, `workers/github-app-discord-bot/test/index.test.js:245`, `workers/github-app-discord-bot/test/index.test.js:265`, `npm test` | `README.md, README.ja.md, .env.example, workers/github-app-discord-bot/README.md` | steady_state |
| v0.2.0 adds structured Worker observability, best-effort GitHub release reaction stamping, and optional duplicate suppression without blocking Discord delivery | `workers/github-app-discord-bot/src/index.js:52`, `workers/github-app-discord-bot/src/index.js:613`, `workers/github-app-discord-bot/src/index.js:661`, `workers/github-app-discord-bot/src/index.js:785` | `workers/github-app-discord-bot/test/index.test.js:189`, `workers/github-app-discord-bot/test/index.test.js:326`, `workers/github-app-discord-bot/test/index.test.js:360`, `workers/github-app-discord-bot/test/index.test.js:394`, `npm test` | `README.md, README.ja.md, .env.example, workers/github-app-discord-bot/README.md` | steady_state |
| v0.2.0 retires the Python polling release path and formalizes the Node-based Worker packaging, CI validation, and versioned release collateral | `package.json:4`, `.github/workflows/validate.yml:1`, `workers/github-app-discord-bot/package.json:4`, `assets/release-header-v0.2.0.svg:51` | `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\verify-svg-assets.ps1 -RepoPath . -Path assets\scan-beacon.svg,assets\release-header-v0.2.0.svg`, `npm test`, `gh release view v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --json url,name,body,publishedAt,tagName,targetCommitish`, `curl.exe -I -L https://raw.githubusercontent.com/Sunwood-ai-labs/github-account-scanner/v0.2.0/assets/release-header-v0.2.0.svg` | `README.md, README.ja.md, workers/github-app-discord-bot/README.md` | steady_state |

## Steady-State Docs Review

| surface | status | evidence |
| --- | --- | --- |
| README.md | pass | Reviewed the English Worker-first overview, supported production path, mention behavior, release reaction notes, and `WEBHOOK_STATE` guidance against `workers/github-app-discord-bot/src/index.js:309`, `workers/github-app-discord-bot/src/index.js:514`, `workers/github-app-discord-bot/src/index.js:687`, `workers/github-app-discord-bot/src/index.js:785`, and `workers/github-app-discord-bot/src/index.js:801`; the merged release content already matched the shipped runtime and needed no extra truth-sync edits after release publication. |
| README.ja.md | pass | Reviewed the Japanese overview, profile routing, mention behavior, and duplicate-suppression caveats against the same Worker runtime surfaces; no additional release-only wording change was required beyond the merged Worker-first rewrite. |
| .env.example | pass | Reviewed the shared environment example for `DISCORD_DELIVERY_PROFILE`, `GITHUB_RELEASE_REACTION`, and mention target variables against `workers/github-app-discord-bot/src/index.js:514` and `workers/github-app-discord-bot/src/index.js:613`; the documented variables already matched the shipped runtime. |
| workers/github-app-discord-bot/README.md | pass | Reviewed the Worker operator guide for local development, deploy steps, reaction setup, logging, and `WEBHOOK_STATE` dedupe behavior against `workers/github-app-discord-bot/src/index.js:52`, `workers/github-app-discord-bot/src/index.js:613`, `workers/github-app-discord-bot/src/index.js:661`, and `workers/github-app-discord-bot/src/index.js:785`; no post-release correction was needed. |

## QA Inventory

| criterion_id | status | evidence |
| --- | --- | --- |
| compare_range | pass | `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\collect-release-context.ps1 -Tag v0.2.0 -BaseTag v0.1.0` reported `compare range: v0.1.0..v0.2.0` for tagged commit `eb0a7f632f556c71f53310ce8073c5b7501ad33f`. |
| release_claims_backed | pass | Release notes and QA claims were grounded in `workers/github-app-discord-bot/src/index.js`, `workers/github-app-discord-bot/test/index.test.js`, `package.json`, `.github/workflows/validate.yml`, `.env.example`, and the merged README surfaces rather than commit subjects alone. |
| docs_release_notes | not_applicable | The repository still has no `docs/` publishing surface or deployed docs site; the GitHub release body is the canonical release-note output for `v0.2.0`. |
| companion_walkthrough | not_applicable | There is no repository docs article surface where a companion walkthrough page could be published. |
| operator_claims_extracted | pass | The claim matrix above extracts operator-facing claims for webhook filtering, profile routing, reaction stamping, logging, dedupe, and the Node-based validation path. |
| impl_sensitive_claims_verified | pass | Verified implementation-sensitive claims against `workers/github-app-discord-bot/src/index.js:52`, `workers/github-app-discord-bot/src/index.js:309`, `workers/github-app-discord-bot/src/index.js:514`, `workers/github-app-discord-bot/src/index.js:613`, `workers/github-app-discord-bot/src/index.js:661`, `workers/github-app-discord-bot/src/index.js:687`, `workers/github-app-discord-bot/src/index.js:785`, `workers/github-app-discord-bot/src/index.js:801`, and the matching tests listed in the claim matrix. |
| steady_state_docs_reviewed | pass | Reviewed `README.md`, `README.ja.md`, `.env.example`, and `workers/github-app-discord-bot/README.md` in the steady-state docs table above. |
| claim_scope_precise | pass | Release wording stayed scoped to the GitHub App Worker runtime, its Discord thread delivery path, and the Worker-only validation workflow instead of implying generic repository-wide monitoring behavior. |
| latest_release_links_updated | not_applicable | The repository does not expose a latest-release landing page, docs navigation entry, or release index pointer that needed updating for `v0.2.0`. |
| svg_assets_validated | pass | `powershell -ExecutionPolicy Bypass -File D:\Prj\gh-release-notes-skill\scripts\verify-svg-assets.ps1 -RepoPath . -Path assets\scan-beacon.svg,assets\release-header-v0.2.0.svg` passed, and `curl.exe -I -L https://raw.githubusercontent.com/Sunwood-ai-labs/github-account-scanner/v0.2.0/assets/release-header-v0.2.0.svg` returned `HTTP/1.1 200 OK`. |
| docs_assets_committed_before_tag | not_applicable | No docs-backed release pages or docs-hosted assets were required because the repository still has no docs publishing surface. |
| docs_deployed_live | not_applicable | The repository has no docs deployment to verify. |
| tag_local_remote | pass | `git rev-parse 'v0.2.0^{commit}'` resolved to `eb0a7f632f556c71f53310ce8073c5b7501ad33f`, `git push origin refs/tags/v0.2.0` published the tag, and `git ls-remote --tags origin refs/tags/v0.2.0` confirmed the remote tag ref exists. |
| github_release_verified | pass | `gh release create v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --title "v0.2.0" --notes-file tmp/release-notes-v0.2.0.md` succeeded, and `gh release view v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --json url,name,body,publishedAt,tagName,targetCommitish` returned the expected body, target `main`, and published URL. |
| validation_commands_recorded | pass | All commands actually executed for the release are recorded in Release Context. |
| publish_date_verified | pass | `gh release view v0.2.0 --repo Sunwood-ai-labs/github-account-scanner --json url,name,body,publishedAt,tagName,targetCommitish` returned `publishedAt: 2026-03-25T12:27:32Z`, and the release notes body did not hardcode a publish date before publication. |

## Notes

- blockers: none
- waivers: docs-backed release notes and companion walkthrough skipped because there is no docs publishing surface in this repository.
- follow-up docs tasks: none for `v0.2.0`; the merged Worker-first README and Worker operator guide already reflect the shipped behavior.
