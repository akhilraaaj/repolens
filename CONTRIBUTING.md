# Contributing

Keep a change inside one area when you can: ingestion, analysis, search, answers, or the web workspace.

## Setup

Follow the README. API tests need the `repolens_test` database with the `vector` extension.

```bash
cd apps/api && uv run pytest
cd apps/web && bun run lint && bun run typecheck
```

`bun run e2e` in `apps/web` needs Playwright Chromium (`bunx playwright install chromium`) and a page at `http://localhost:3000`. It reuses a dev server that is already running.

## Expectations

- Do not execute code from an analyzed repository.
- Do not return API keys, database URLs, or file contents outside the snapshot path checks.
- Keep a new dependency justified. Do not add a queue, a second database, or a cache without a measured need.
- Update `docs/architecture.md` when behavior changes. Add a record in `docs/decisions/` when the change is a trade-off someone else would question.
- Prefer a failing test that names the behavior, then the change that makes it pass.

## Pull requests

Describe what a user can do after the change, how you tested it, and what you did not test. Screenshots help for workspace layout changes.
