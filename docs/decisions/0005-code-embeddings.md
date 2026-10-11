# 0005 Code embeddings and optional reranking

## Status

Accepted. This replaces the embedding model in 0004. The distance cutoff and the hosted-endpoint rule stay.

## Context

`all-MiniLM-L6-v2` is a general English model with 384 dimensions and a short context. It is a weak match for source code. The roadmap names `jinaai/jina-embeddings-v2-base-code`: 768 dimensions, a long context, Apache-2.0, and already supported by fastembed.

Changing the width invalidates every stored vector.

## Decision

The local model is `jinaai/jina-embeddings-v2-base-code`. `chunk_embeddings.embedding` is `vector(768)`. An HNSW index uses cosine distance, which is the `<=>` operator the search already uses.

On startup, a column that is still `vector(384)` is widened. The old vectors are deleted and `embedding_status` is cleared. Source files and the graph are kept. Rebuild re-indexes that commit.

Each chunk stores its source text unchanged, plus a `header` that names the file, symbol, parent, and imports. Only the embedding sees the header. Keyword search and snippets stay on the source text.

A cross-encoder reranker is off unless `REPOLENS_RERANKER` is set. The default model is `jinaai/jina-reranker-v1-tiny-en` because `BAAI/bge-reranker-base` is about a gigabyte. Set `REPOLENS_RERANKER_MODEL` to use that larger model. Keep whichever one the evaluation scores say is better.

`evaluation/datasets/*.json` holds questions and expected paths. `POST /ingestions/{id}/evaluation` writes Recall@k and MRR for keyword, vector, hybrid, and reranked search. `GET /ingestions/{id}/retrieval` returns the four lists for one question. The workspace does not display those endpoints.

## Alternatives

Staying on MiniLM avoids a migration and a larger download. It also leaves code search on a model that was not trained for code.

Putting the header into `content` would change keyword hits and the text shown in the UI. A separate column avoids that.

## Consequences

The first analysis after this change downloads the code model if it is not cached. Snapshots embedded with MiniLM must be rebuilt. A hosted embedding endpoint must return 768 numbers. The reranker downloads its own model the first time it is turned on.
