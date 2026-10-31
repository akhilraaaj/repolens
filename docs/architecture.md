# Architecture

This document describes the system that exists: ingestion, TypeScript analysis, keyword and vector search, and grounded answers.

## Components

RepoLens is one repository with two application processes and one database.

| Process | Directory | Role |
| --- | --- | --- |
| Web | `apps/web` | Landing page and the workspace (Overview, Map, Ask, source drawer). UI controls are shadcn/ui (`base-nova`, Base UI) |
| API | `apps/api` | Health, ingestion, analysis, search, questions, and impact |
| Analyzer | `apps/analyzer` | TypeScript compiler API, invoked by the API |
| PostgreSQL | local server | Snapshots, graph, chunks, and embeddings |

The browser calls the API directly. The Next.js server does not proxy those calls.

There is no queue or cache. An ingestion download runs as an `asyncio` task in the API process. The browser polls until the version row leaves `running`. A chat provider is optional and stored in `provider_settings`.

## Health

`GET /health` returns `200` and `{"status":"ok"}` when the API process can answer. It does not connect to PostgreSQL or GitHub.

1. Next.js serves `http://localhost:3000`.
2. `HealthStatus` sends `GET {API_BASE}/health`.
3. The default API base is `http://127.0.0.1:8000`.
4. `CORSMiddleware` allows the response to be read from `http://localhost:3000` and `http://127.0.0.1:3000`.

## Ingestion

`POST /ingestions` accepts `{ "url", "ref"? }`.

1. Parse the URL. Only `https://github.com/{owner}/{name}` is accepted, with an optional `.git` suffix and an optional `/tree/{ref}` when the ref contains no slash. A branch that contains a slash goes in the `ref` field.
2. Open PostgreSQL. If `DATABASE_URL` is missing or the server is down, return 503 `database_unavailable` before calling GitHub.
3. `GET https://api.github.com/repos/{owner}/{name}` and `GET /repos/{owner}/{name}/commits/{ref}`. The ref defaults to the repository's default branch. The commit response must contain a 40-character lowercase SHA.
4. Insert or reuse the repository row, then claim the version row for that SHA.
5. If the claim says `run`, schedule `execute`. That task downloads the tar, classifies members, and writes file rows.
6. Return the current row. HTTP 202 while `running`, otherwise 200.

`GET /ingestions/{id}` returns the same summary plus each file's path, disposition, reason, and size. It does not return file content.

Errors are JSON objects with `error_code` and `message` at the top level.

```text
Browser (localhost:3000)
  IngestForm
    POST /ingestions
    GET  /ingestions/{id}
        |
        v
API (127.0.0.1:8000)
  parse URL -> PostgreSQL probe -> GitHub metadata -> claim version
        |
        v
  asyncio task
    codeload tar.gz -> inspect members -> files rows
```

GitHub requests use `User-Agent: repolens`. Metadata requests also send `Accept: application/vnd.github+json` and `X-GitHub-Api-Version: 2022-11-28`. `Authorization: Bearer` is added only when `GITHUB_TOKEN` is set, and only for `api.github.com`. Redirects are checked manually, at most three, and only toward `api.github.com` or `codeload.github.com`.

## Tables

`repositories` is unique on host, owner, and name. `repository_versions` is unique on repository and commit SHA. `files` belongs to one version and is deleted with it. `content` is present only for `disposition = stored`.

Version status is `running`, `completed`, `completed_with_skips`, or `failed`. `completed` means the source snapshot was stored. `analysis_status` of `completed` means the graph was stored. Search indexing runs after that and records `embedding_status` separately.

## Limits

Defaults, overridable with positive integers:

| Bound | Default | Env |
| --- | --- | --- |
| Archive download | 100 MiB | `REPOLENS_MAX_ARCHIVE_BYTES` |
| Archive members examined | 20000 | `REPOLENS_MAX_ENTRIES` |
| Stored files | 10000 | `REPOLENS_MAX_STORED_FILES` |
| One file | 512 KiB | `REPOLENS_MAX_FILE_BYTES` |
| Stored text | 64 MiB | `REPOLENS_MAX_TOTAL_BYTES` |
| Wall clock | 180 seconds | `REPOLENS_MAX_DURATION_SECONDS` |

These defaults fit a repository the size of `fastapi/fastapi`. A live snapshot stored 2,987 text files and about 18 MiB of source and docs, and skipped 195 binary or oversized files. A single oversized file is skipped with `file_too_large`. A file with a NUL byte in its first 8 KiB is skipped as `binary`, and one that is not valid UTF-8 (for example an Illustrator `.ai` file) is skipped as `not_utf8`. Neither fails the snapshot. Crossing an archive, entry, stored-file, total-text, or time limit fails the version with `limit_exceeded`. Extract limits keep the file rows classified before the stop. The download-size limit has no rows, because the tar is not opened.

`progress_completed` is written when the version finishes. While the task is still extracting, a poll can show phase `extracting` and progress `0`.

## Important files

- `apps/web/app/page.tsx` is the landing page. The repository input posts an ingestion and opens the workspace.
- `apps/web/app/workspace/[id]/workspace.tsx` is the workspace shell: a left icon rail with four views and a resizable source drawer on the right.
- `apps/web/features/rag/pipeline-inspector.tsx` draws how one answer was retrieved.
- `apps/web/lib/api-base.ts` reads `NEXT_PUBLIC_API_BASE_URL`.
- `apps/api/app/main.py` builds the app, CORS, and `/health`.
- `apps/api/app/ingestion/routes.py` is the HTTP boundary.
- `apps/api/app/ingestion/github.py` talks to GitHub.
- `apps/api/app/ingestion/archive.py` classifies tar members.
- `apps/api/app/db/schema.sql` is the stored tables.

## Analysis

`POST /ingestions/{id}/analysis` reads the stored `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, and `.cjs` texts and sends them to `node apps/analyzer/parse.mjs` on stdin. The parser uses the TypeScript compiler API. Its compiler host can read only those texts. It does not execute a repository `tsconfig`, so a repository cannot enable a compiler plugin.

The parser reads `baseUrl` and `paths` from the shallowest `tsconfig.json` or `jsconfig.json` as JSON. It does not follow `extends` and it does not execute the config. The graph is built in memory and replaces `symbols` and `relationships` in one transaction. A crash before that commit leaves the previous graph in place. A syntax error in one file is stored on that file and the version becomes `completed_with_errors`. The other files are still saved. `.d.ts` files are marked `skipped`. `require` calls, capitalized JSX tags, and some property calls become edges.

`GET /ingestions/{id}/graph` returns at most 500 symbols and 500 relationships. `edge_type`, `file`, and `resolution_status` filter that page. A relative import that matches one stored file is `verified`. A call bound to one of those functions is `resolved`. A package import such as `react` is `unresolved`. RepoLens does not emit `inferred` edges.

`GET /health` still does not touch the database or the parser.

## Search and answers

After the graph is stored, the API slices each function, class, method, and value into a `code_chunks` row. A file with none of those symbols gets one truncated file chunk. PostgreSQL indexes `content_tsv` with English full-text search.

`chunk_embeddings` stores one `vector(768)` per chunk, with an HNSW index on cosine distance. The default model is `jinaai/jina-embeddings-v2-base-code`. A startup migration deletes 384-dimension vectors and widens the column; the graph and the files stay. Set `REPOLENS_EMBEDDING_BASE_URL` to replace the local model with an OpenAI-compatible `POST /embeddings` response that must also be 768 dimensions. An indexing failure sets `embedding_status` to `failed` and leaves `analysis_status` unchanged.

Each chunk has a `header` (file, symbol, parent, imports) that is embedded with the source and is not part of keyword search. `GET /ingestions/{id}/search` fuses keyword hits and vector hits with reciprocal rank fusion, constant 60. A vector hit is kept only when cosine distance is at most 0.75. `REPOLENS_RERANKER=1` reranks that fused list with a local cross-encoder. Every hit carries `rank`, `keyword_rank`, `vector_rank`, and `rrf_score`, the sum of `1 / (60 + rank)` over the lists that found it. `trace_search` in `app/search/retrieve.py` returns the keyword, vector, hybrid, and reranked lists plus `timings_ms` for `keyword`, `vector` (embedding the query and the cosine search), `fuse`, and `rerank`. `GET /ingestions/{id}/retrieval` returns the four lists. `POST /ingestions/{id}/evaluation` takes either `dataset` (a file under `evaluation/datasets/`) or `questions`, an inline list of 1 to 20 `{question, expected_paths}` items with 1 to 10 relative paths each. Sending both, sending neither, or sending a path with `..` returns 422. It stores Recall@k and MRR per strategy.

Local embedding sorts texts by length and embeds them 8 at a time. ONNX pads a batch to its longest text and attention memory grows with the square of that length, so one long chunk in a large batch used to get the API killed for running out of memory.

`POST /ingestions/{id}/questions` streams server-sent events. It searches, looks up symbol names, walks incoming relationships to depth 2, and reads the cited file again before keeping the citation. It abstains when no citation still matches the stored file. Before the model is asked, the stream sends an `event: retrieval` with the pipeline: the query, embedding model, reranker, RRF constant, the four stage lists without snippets, timings, the chat model, and `context` (chunks, characters, and an approximate token count at four characters per token). The `done` payload repeats that object as `pipeline`, adding `timings_ms.generate`, `generator` (`model`, `extractive`, or `abstain`), `cited`, and `abstained`. An abstained answer still carries it. When unused citations are dropped, the `[n]` markers in the answer are renumbered to match the shorter list. With no provider, the answer is a sentence built from those lines and from import statements in the first 80 lines of the same files. It names a package only when that specifier is an import in a cited file. A saved provider, or `REPOLENS_CHAT_BASE_URL` plus `REPOLENS_CHAT_MODEL` when no row is saved, asks that model. The model may call read-only tools at most six times. A paragraph without a valid `[n]` citation is dropped. `GET /provider` never returns the API key.

`POST /ingestions/{id}/impact` finds a symbol by name and lists incoming neighbors with the symbol they were reached through. `GET /ingestions/{id}/files` returns a line range only after the path is a relative path inside the snapshot. `GET /ingestions/{id}/overview` builds the brief from manifests and PageRank. `GET /ingestions/{id}/documentation` asks the configured chat model for a short guide: what the repo is, where to start reading, how it is organized, and how a request moves. The model only sees the README, the manifest, entry files, and the files other code imports. The guide is stored on the snapshot. With no model, or if the model fails, the same facts are written out directly. `GET /ingestions/{id}/graph/files` is the file-level graph the architecture view draws. `GET /ingestions/{id}/commits` reads up to 40 commits from GitHub, starting at the snapshot SHA, and returns each parent SHA.

The workspace has four views on a left icon rail:

- **Overview** is the brief: stack, entry points, core modules, and folder roles.
- **Guide** is the generated walkthrough for this commit. File chips open the source drawer.
- **Map** has two drawings of the same file graph. Orbs places each folder's files in a spiral and sets those spirals on a ring. Graph lays the same nodes out as labeled cards. A node takes its color from the folder it lives in.
- **Ask** is the full-width chat. Under each answer, "How this answer was built" opens the pipeline inspector: stage cards with timings, the keyword, vector, fused, and reranked hit tables, the RRF arithmetic for a hit, and the chunks that went into the prompt.

`GET /ingestions/{id}/retrieval` and `POST /ingestions/{id}/evaluation` are still served. The workspace no longer has a screen for them.

Clicking a citation, a map node, or a Cmd+K result opens the source drawer on those lines. The model settings dialog also shows the snapshot facts: commit, counts, embedding model, and whether the reranker is on. The Code, Commits, Search, and Settings tabs and the file-tree pane were removed. `/commits` and `/search` are still served. `docker-compose.yml` starts Postgres, the API, and the web app. The `ollama` service is behind the `ollama` profile, and its models persist in the `repolens-ollama` volume. The API container reads `apps/api/.env` at run time when it exists, keeps the local embedding model in the `repolens-models` volume (`FASTEMBED_CACHE_PATH`), and reaches an Ollama on the host as `host.docker.internal`.

## Boundaries

- Repository code is never executed.
- FastAPI still serves `/docs`, `/redoc`, and `/openapi.json`.
- Answers quote stored lines. They are not a general agent, and a hosted chat model stays off unless it is configured.
- Open the web app at `http://localhost:3000` during development. Next.js blocks its dev assets when the page is opened as `http://127.0.0.1:3000` unless `allowedDevOrigins` includes that host. The config includes it; a running `next dev` process has to be restarted before that host hydrates.
