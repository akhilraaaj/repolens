# ADR 0003: Static analysis parser

## Status

Accepted

## Context

Analysis needs symbols, resolved relative imports, and a call graph for JavaScript and TypeScript. The parser is the TypeScript compiler API, chosen over Tree-sitter after a prototype. Relationships stay in PostgreSQL.

The source texts are already stored. The analyzer must not execute repository code and must not load a repository `tsconfig`, because compiler plugins can run arbitrary code.

## Decision

- Parse with the TypeScript compiler API, version 6.0.3, in `apps/analyzer/parse.mjs`.
- The API process runs `node parse.mjs`, writes the stored texts to stdin, and reads one JSON graph from stdout.
- The compiler host answers `readFile` only from that JSON. `noLib` is set. The repository's `tsconfig` is ignored.
- Store symbols and relationships in PostgreSQL, keyed by the existing repository version.
- Replace that graph in one transaction after the parser succeeds.
- Record a relative import that matches one stored file as `verified`, a call bound to a recorded function as `resolved`, and a package import as `unresolved`.
- Do not emit `inferred` edges or confidence scores.
- Keep the HTTP paths under `/ingestions/{id}` instead of adding `/api/jobs`.

## Alternatives

- **Tree-sitter in the Python process.** One runtime, and no Node dependency. The prototype would then have to reimplement binding for `export { add as plus }` and re-exports. The compiler already does that, and the fixture confirmed a relative import and a call in one run.
- **Loading the repository `tsconfig`.** Path aliases such as `@/lib` would resolve. Plugins and project references could execute code. Aliases stay unresolved until there is a safe subset of config to honor.
- **Docker Compose as a parser dependency.** Compose provides PostgreSQL. It does not help the parser.

## Consequences

- Analysis requires Node.js on the PATH and `bun install` inside `apps/analyzer`.
- A syntax error in one file does not discard the other files.
- `require` calls, capitalized JSX tags, and some property calls are stored as edges. A package import stays `unresolved`. See `docs/architecture.md`.
- Docker Compose is how a new contributor gets PostgreSQL and pgvector. Analysis itself only needs Node.js.
