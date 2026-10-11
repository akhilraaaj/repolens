# ADR 0001: Application stack

## Status

Accepted

## Context

RepoLens is a local web app and a local API. The languages and frameworks are Next.js, React, TypeScript, Tailwind CSS, Python, FastAPI, and Pydantic. The repository also needs a Python environment tool, backend tests, frontend lint, typecheck, and a production build.

Package versions were read from the npm and PyPI registries on 10 October 2026 and checked against each tool's supported range. FastAPI 0.143.0 supports Python 3.10 through 3.14, so a system Python 3.15 is outside that range.

## Decision

- Put the web app in `apps/web` and the API in `apps/api`.
- Install frontend packages with Bun 1.3.2 and track `apps/web/bun.lock`.
- Install API packages with uv and track `apps/api/uv.lock`.
- Run the API on CPython 3.12, installed by uv.
- Pin the direct packages that were current and compatible:
  - next 16.4.0, react 19.3.0, react-dom 19.3.0
  - typescript 6.0.3
  - tailwindcss 4.3.3, @tailwindcss/postcss 4.3.3, postcss 8.5.29
  - eslint 10.12.0, eslint-config-next 16.4.0
  - @types/react 19.3.0, @types/react-dom 19.3.0, @types/node 24.19.2
  - fastapi 0.143.0, pydantic 2.14.0, uvicorn 0.54.0
  - pytest 9.1.1, httpx2 2.13.1
- Serve `GET /health` with the body `{"status":"ok"}`.
- Let the browser call the API directly and allow the two local page origins through CORS.
- Test the API with pytest. Use a direct function call for the response value and FastAPI's `TestClient` for the HTTP contract. `TestClient` loads httpx2 when that package is installed.
- Check the frontend with ESLint, `tsc --noEmit`, and `next build`.
- License the repository under MIT.
- Leave Next.js `agentRules` off. `next dev` otherwise writes `apps/web/AGENTS.md`, and this repository keeps its project instructions in the root `AGENTS.md`.

## Alternatives

- **npm and `package-lock.json`.** Bun is the frontend package manager, so there is one frontend lockfile: `bun.lock`.
- **TypeScript 7.** `typescript-eslint`, which `eslint-config-next` loads, refuses TypeScript 7 because that release has no JavaScript compiler API. TypeScript 6.0.3 is the newest release inside the supported range.
- **A Next.js rewrite that proxies `/health`.** The browser calls the API directly so the origin boundary stays visible.
- **`create-next-app`.** The generator adds a demo page and extra dependencies.
- **Apache-2.0.** MIT is the license for this repository.
- **httpx 0.28.1.** Starlette 1.7, which FastAPI 0.143 uses, prefers httpx2. The tests use httpx2 2.13.1.

## Consequences

- `bun install` and `uv sync --frozen` reproduce the locked trees.
- TypeScript stays on 6.0.3 until the ESLint toolchain supports TypeScript 7.
- ESLint 10 may print peer warnings because `eslint-plugin-react` and `eslint-plugin-jsx-a11y` do not yet list ESLint 10 in their peer ranges. Next.js documents that ESLint 10 is supported.
- `GET /health` checks that the API process can answer. It does not check PostgreSQL.
- A page opened from a host or port outside the CORS list will see the error state even when the API is running.
