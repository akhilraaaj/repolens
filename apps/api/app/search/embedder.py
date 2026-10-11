"""Local code embeddings, with an optional hosted replacement.

The local model is jinaai/jina-embeddings-v2-base-code. It writes 768-number
vectors, which is the width of the pgvector column, and it was trained on code
rather than general English. A hosted endpoint is used only when
REPOLENS_EMBEDDING_BASE_URL is set, and it must return that same width.
"""

import os

import httpx2
from fastembed import TextEmbedding

LOCAL_MODEL = "jinaai/jina-embeddings-v2-base-code"
DIMENSIONS = 768
VECTOR_MAX_DISTANCE = 0.75
LOCAL_BATCH_SIZE = 8

_model: TextEmbedding | None = None


class EmbeddingError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def model_name() -> str:
    configured = os.environ.get("REPOLENS_EMBEDDING_MODEL", "").strip()
    if configured and os.environ.get("REPOLENS_EMBEDDING_BASE_URL", "").strip():
        return configured
    return LOCAL_MODEL


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    base_url = os.environ.get("REPOLENS_EMBEDDING_BASE_URL", "").strip()
    if base_url:
        return _hosted_embeddings(base_url, texts)
    # A batch is padded to its longest text, and attention memory grows with batch * length^2.
    # Small batches of similar length keep a laptop from running out of memory.
    order = sorted(range(len(texts)), key=lambda index: len(texts[index]))
    vectors = list(_local_model().embed([texts[index] for index in order], batch_size=LOCAL_BATCH_SIZE))
    converted: list[list[float]] = [[] for _ in texts]
    for position, index in enumerate(order):
        converted[index] = [float(value) for value in vectors[position]]
    if any(len(vector) != DIMENSIONS for vector in converted):
        raise EmbeddingError(f"Embeddings must have {DIMENSIONS} dimensions.")
    return converted


def _local_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=LOCAL_MODEL)
    return _model


def _hosted_embeddings(base_url: str, texts: list[str]) -> list[list[float]]:
    key = os.environ.get("REPOLENS_EMBEDDING_API_KEY", "").strip()
    headers = {"content-type": "application/json"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    try:
        response = httpx2.post(
            f"{base_url.rstrip('/')}/embeddings",
            headers=headers,
            json={"model": model_name(), "input": texts},
            timeout=60,
        )
    except httpx2.HTTPError as exc:
        raise EmbeddingError("The embedding endpoint could not be reached.") from exc
    if response.status_code >= 400:
        raise EmbeddingError("The embedding endpoint rejected the request.")
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != len(texts):
        raise EmbeddingError("The embedding endpoint returned an unexpected response.")
    vectors: list[list[float]] = []
    for row in rows:
        embedding = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(embedding, list) or len(embedding) != DIMENSIONS:
            raise EmbeddingError(f"Embeddings must have {DIMENSIONS} dimensions.")
        vectors.append([float(value) for value in embedding])
    return vectors
