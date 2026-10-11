"""Optional cross-encoder rerank.

Off unless REPOLENS_RERANKER is 1, true, or on. The default model is the small
jinaai/jina-reranker-v1-tiny-en so a laptop can run it. Set
REPOLENS_RERANKER_MODEL to BAAI/bge-reranker-base for the larger model named in
the roadmap; keep it only when evaluation shows a gain.
"""

import os

from fastembed.rerank.cross_encoder import TextCrossEncoder

DEFAULT_RERANKER = "jinaai/jina-reranker-v1-tiny-en"

_model: TextCrossEncoder | None = None
_failed = False


def rerank_enabled() -> bool:
    return os.environ.get("REPOLENS_RERANKER", "").strip().lower() in {"1", "true", "on"}


def reranker_name() -> str:
    configured = os.environ.get("REPOLENS_RERANKER_MODEL", "").strip()
    return configured or DEFAULT_RERANKER


def rerank(query: str, documents: list[str]) -> list[float] | None:
    """Higher scores are more relevant. None means the reranker is off or failed."""

    global _failed
    if not rerank_enabled() or not documents or _failed:
        return None
    try:
        scores = list(_encoder().rerank(query, documents))
    except Exception:
        _failed = True
        return None
    if len(scores) != len(documents):
        return None
    return [float(score) for score in scores]


def _encoder() -> TextCrossEncoder:
    global _model
    if _model is None:
        _model = TextCrossEncoder(model_name=reranker_name())
    return _model
