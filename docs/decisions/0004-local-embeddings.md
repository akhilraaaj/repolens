# 0004 Local sentence embeddings

## Status

Superseded by [0005](0005-code-embeddings.md). The distance cutoff and the hosted-endpoint rule still apply. The local model is now 768 dimensions, not 384.

## Context

The product needs keyword search, embeddings, and grounded answers without requiring a paid model. Hosted embeddings and chat are allowed only when they are explicitly configured.

## Decision

Chunks are stored in PostgreSQL. Keyword search ORs the question's words into a `to_tsquery` and adds a case-insensitive substring match. It first used `websearch_to_tsquery`, which requires every word, so a question in plain English almost never matched.

The default embedding is `sentence-transformers/all-MiniLM-L6-v2`, loaded locally by fastembed. It writes 384-number vectors into pgvector. Hybrid search uses reciprocal rank fusion. A vector neighbor is returned only when cosine distance is at most 0.75.

An OpenAI-compatible embeddings endpoint can replace the local model through `REPOLENS_EMBEDDING_BASE_URL`, `REPOLENS_EMBEDDING_MODEL`, and `REPOLENS_EMBEDDING_API_KEY`. The response must be 384 dimensions.

Answers quote retrieved lines. A chat model is used only when both `REPOLENS_CHAT_BASE_URL` and `REPOLENS_CHAT_MODEL` are set, and only if the reply names a cited path.

## Alternatives

A neural embedding model would match paraphrases better. It needs a downloaded model or a hosted key, so it is not the default.

Returning the nearest vector for every query would make unrelated questions look grounded. The distance cutoff prevents that for the local model.

## Consequences

The first analysis downloads the model if it is not cached. Later searches embed the question on this machine. A paraphrase can outrank a chunk that does not share its words. The distance cutoff still drops unrelated questions.
