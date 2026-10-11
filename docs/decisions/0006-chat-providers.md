# 0006 Chat providers

## Status

Accepted

## Context

Answers were extractive quotes. The product also needs a local model and a hosted OpenAI-compatible model, chosen in the interface, with keys that never reach the browser.

## Decision

One `provider_settings` row stores the choice: `ollama`, `openai_compatible`, or `none`. The API key stays in that row. `GET /provider` returns `has_api_key` and never the key. The base URL must be `http` or `https` and must not contain a username or password.

`POST /ingestions/{id}/questions` streams server-sent events. With no provider, the stream is the extractive answer. With a provider, the model may call `search_code`, `get_file`, `find_symbol`, and `dependents`. The loop stops at 6 calls. Every tool reads the stored snapshot and rejects a path that leaves it. Paragraphs that do not cite a numbered evidence item are dropped. If nothing citable remains, the extractive answer is shown instead.

Threads and messages are stored on the snapshot. Source comments are described to the model as data, not instructions.

## Alternatives

Keeping chat configuration only in environment variables cannot support the first-run picker, and it cannot rotate a key without a restart. `apps/api/.env` is loaded at startup. Those variables supply chat when no row is saved and when the saved provider is none. A saved Ollama or hosted row still wins. The key in that file is required; a blank key leaves answers on the quoted path.

Streaming the model's tokens before validation would show a sentence that is later deleted. The stream sends the answer after citation checks.

## Consequences

Choosing a hosted provider sends retrieved source to that host. Choosing none, or not saving a provider, does not. Ollama is reached at the URL the operator saved, usually `http://127.0.0.1:11434`.
