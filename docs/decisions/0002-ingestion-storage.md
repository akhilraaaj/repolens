# ADR 0002: Ingestion storage and retrieval

## Status

Accepted

## Context

RepoLens must remember a public GitHub repository at one commit, skip another download of that same commit, and show which files were stored or skipped. That record has to survive a process restart. PostgreSQL is the database. A queue, Redis, or a second database needs evidence before it is added.

`completed` here means the source snapshot is stored. Parsing and embeddings are separate statuses.

## Decision

- Store repositories, versions, and file rows in PostgreSQL. Apply `apps/api/app/db/schema.sql` with `CREATE TABLE IF NOT EXISTS` on each connection.
- Identify a snapshot by `github.com` + owner + name + 40-character commit SHA.
- Download one gzip tar from `codeload.github.com`. Do not clone the repository and do not call the GitHub Contents API once per file.
- Run the download in an `asyncio` task inside the API process. The client polls `GET /ingestions/{id}`. There is no worker and no queue.
- Allow HTTPS requests only to `api.github.com` and `codeload.github.com`, and follow at most three redirects that stay on those hosts.
- Treat `completed` and `completed_with_skips` as "the source snapshot is stored." Set `analysis_status` to `not_started`. The UI says analysis has not started.
- When an extract limit stops the run, keep the file rows already classified and mark the version `failed` with `limit_exceeded`. A download that exceeds the archive size, or an archive with an unsafe path, stores no file rows.
- Read an optional `GITHUB_TOKEN` on the server. Send it only to `api.github.com`.

## Alternatives

- **Files on disk.** A directory per commit can hold the manifest, but a crash during the write can leave two partial copies, and a second request has to invent its own lock. PostgreSQL's unique key on repository plus commit is the lock.
- **SQLite.** It is one file and needs no server. Embeddings need pgvector, so starting on SQLite would be a migration.
- **A job queue.** The ingestion is one download and one database transaction. A queue would add a process this step does not need.

## Consequences

- `GET /health` stays a process check. A missing database returns 503 from `POST /ingestions` and still returns 200 from `/health`.
- PostgreSQL must be running before ingestion.
- `completed` means the source snapshot is stored. `analysis_status` stays `not_started` until analysis runs.
