# Threat model

RepoLens stores source from a repository the operator chose and answers questions about that snapshot. The operator is trusted. The repository contents are not.

## What we defend against

- A repository URL that is not a public GitHub repository, including redirects off GitHub.
- Archive members that escape the snapshot directory, including symlinks and `..` paths.
- A file path in a question, a tool call, or a viewer request that leaves the stored tree.
- A model treating a comment or README as an instruction to ignore the system prompt or to call a tool outside the snapshot.
- An API key being returned to the browser or written into the repository.
- Repository text making the browser fetch a remote URL, such as a README badge that ends up in an answer.

## What the controls are

- Ingestion accepts only `https://github.com/{owner}/{name}`, checks redirects, and caps archive size, file count, file size, and time.
- Stored paths are relative. `safe_relative_path` rejects absolute paths, backslashes, and `..`.
- The TypeScript parser receives file text on stdin. It does not execute the repository, and it does not follow a tsconfig `extends`.
- Tool calls are read-only, limited to six, and use the same path check. Tool results are truncated.
- Chat answers keep a paragraph only when it cites a numbered evidence item from the snapshot.
- Answers render Markdown images as their alt text and never load the image. Links outside citations render as plain text. The extractive fallback strips images, links, and HTML tags from README lines.
- Provider keys live in PostgreSQL. `GET /provider` and `GET /config` do not include them. A base URL with embedded credentials is rejected.
- `.dockerignore` keeps `.env` files out of the Docker images. Compose passes `apps/api/.env` to the API container at run time only.
- Source is sent to a hosted model only after the operator saves a hosted provider. The default is no model.

## What this does not claim

- The hosted model, once configured, sees the retrieved excerpts and tool results. Do not point it at a repository you cannot share with that host.
- The parser does not understand every JavaScript pattern. Missing edges are a correctness limit, not a sandbox escape.
- PostgreSQL and the API process are as trusted as the operator. There is no multi-tenant isolation between people who can reach the API.
