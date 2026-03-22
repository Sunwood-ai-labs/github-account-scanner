# github-account-scanner v0.1.0

Initial release covering the full shipped history through `v0.1.0`.

## Highlights

- Added a local-first GitHub account scanner that snapshots public repositories, scans up to the latest `100` releases per repository, and detects both newly created repositories and newly published releases.
- Added safe API behavior for large accounts, including an unauthenticated-scan guardrail for repository-plus-release polling and draft-to-published release detection.
- Added Discord notification delivery with compact parent messages, event threads, detailed embeds, and optional explainer prompts for downstream AgentAGI workflows.

## Tooling And Automation

- Added a validation-only GitHub Actions workflow that installs dependencies with `uv`, runs the unit test suite, and checks the CLI entrypoint.
- Added package metadata, project URLs, and an MIT license so the repository can be consumed as a public Python CLI project.

## Docs And Assets

- Added English and Japanese top-level READMEs with mirrored quick-start guidance.
- Added a reusable scan beacon SVG for the README hero.
- Documented the explainer prompt template paths and the expectation that downstream posting is prepared in English.

## Validation

- `uv run python -m unittest discover -s tests`
- `uv run github-scan --help`
- `uv build`
- installed the built wheel into an isolated virtual environment with `uv pip install`
- ran the installed `github-scan --help`
- ran the installed `github-scan check octocat ...` to create an initial baseline report
- ran the installed `github-scan notify-discord --report-file ... --dry-run`

## Notes

- This repository is intended for local scheduled execution rather than CI-based production monitoring.
- `state/*.json` and `state/*.md` are runtime outputs and are not part of the tracked release payload.
