"""Keyword search and reciprocal-rank fusion with vectors."""

from time import perf_counter
from uuid import UUID

import psycopg

from app.search.context import embed_input
from app.search.rerank import rerank, rerank_enabled
from app.search.vectors import vector_ranking

RRF_K = 60


def search_version(connection: psycopg.Connection, version_id: UUID, query: str, limit: int = 20) -> list[dict]:
    compared = compare_strategies(connection, version_id, query, limit)
    if rerank_enabled() and compared["reranked"] is not None:
        return compared["reranked"]
    return compared["hybrid"]


def compare_strategies(connection: psycopg.Connection, version_id: UUID, query: str, limit: int = 8) -> dict[str, list[dict] | None]:
    """Rank the same question four ways so the lab can show where they disagree."""

    traced = trace_search(connection, version_id, query, limit)
    return {name: traced[name] for name in ("keyword", "vector", "hybrid", "reranked")}


def trace_search(connection: psycopg.Connection, version_id: UUID, query: str, limit: int = 8) -> dict:
    """The four rankings plus how long each stage took, for the answer inspector."""

    timings: dict[str, float] = {}
    started = perf_counter()
    keyword_ids = _keyword_ids(connection, version_id, query, limit)
    timings["keyword"] = _elapsed(started)
    started = perf_counter()
    vector_hits = vector_ranking(connection, version_id, query, max(limit, 20))
    timings["vector"] = _elapsed(started)
    started = perf_counter()
    distances = {chunk_id: distance for chunk_id, distance in vector_hits}
    vector_ids = [chunk_id for chunk_id, _distance in vector_hits]
    fused, fused_scores = _fuse_scored([keyword_ids, vector_ids])
    timings["fuse"] = _elapsed(started)
    rows = _load_rows(connection, list({*keyword_ids, *vector_ids, *fused[:20]}))
    keyword_ranks = {chunk_id: index for index, chunk_id in enumerate(keyword_ids, start=1)}
    vector_ranks = {chunk_id: index for index, chunk_id in enumerate(vector_ids, start=1)}

    def hit(chunk_id: UUID, rank: int, methods: list[str]) -> dict | None:
        row = rows.get(chunk_id)
        if row is None:
            return None
        distance = distances.get(chunk_id)
        return {
            "path": row["path"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "chunk_type": row["chunk_type"],
            "snippet": row["content"][:500],
            "methods": methods,
            "distance": None if distance is None else round(distance, 3),
            "rank": rank,
            "keyword_rank": keyword_ranks.get(chunk_id),
            "vector_rank": vector_ranks.get(chunk_id),
            "rrf_score": round(fused_scores[chunk_id], 5),
        }

    def collect(ids: list[UUID]) -> list[dict]:
        found = []
        for chunk_id in ids[:limit]:
            item = hit(chunk_id, len(found) + 1, _methods(chunk_id, keyword_ranks, distances))
            if item:
                found.append(item)
        return found

    hybrid = collect(fused)
    reranked = None
    if rerank_enabled():
        started = perf_counter()
        candidates = [item for item in (hit(chunk_id, 0, _methods(chunk_id, keyword_ranks, distances)) for chunk_id in fused[:20]) if item]
        reranked = _reranked(query, candidates, rows, fused[:20], limit)
        timings["rerank"] = _elapsed(started)
    return {
        "keyword": collect(keyword_ids),
        "vector": collect(vector_ids),
        "hybrid": hybrid,
        "reranked": reranked,
        "timings_ms": timings,
    }


def _methods(chunk_id: UUID, keyword_ranks: dict[UUID, int], distances: dict[UUID, float]) -> list[str]:
    methods = []
    if chunk_id in keyword_ranks:
        methods.append("keyword")
    if chunk_id in distances:
        methods.append("vector")
    return methods or ["keyword"]


def _elapsed(started: float) -> float:
    return round((perf_counter() - started) * 1000, 1)


def _reranked(query: str, candidates: list[dict], rows: dict, ids: list[UUID], limit: int) -> list[dict] | None:
    if not candidates:
        return None
    present = [chunk_id for chunk_id in ids if chunk_id in rows]
    documents = [embed_input(rows[chunk_id]["header"], rows[chunk_id]["content"][:2000]) for chunk_id in present]
    scores = rerank(query, documents)
    if scores is None:
        return None
    order = sorted(range(len(present)), key=lambda index: scores[index], reverse=True)
    results = []
    for position, index in enumerate(order[:limit], start=1):
        item = dict(candidates[index])
        item["methods"] = [*item["methods"], "reranked"]
        item["rank"] = position
        item["score"] = round(scores[index], 4)
        results.append(item)
    return results


def _load_rows(connection: psycopg.Connection, ids: list[UUID]) -> dict:
    if not ids:
        return {}
    rows = connection.execute(
        """
        SELECT id, path, start_line, end_line, chunk_type, content, header
        FROM code_chunks
        WHERE id = ANY(%s)
        """,
        (ids,),
    ).fetchall()
    return {row["id"]: row for row in rows}


def _keyword_ids(connection: psycopg.Connection, version_id: UUID, query: str, limit: int) -> list[UUID]:
    pattern = f"%{query.strip()}%"
    try:
        rows = connection.execute(
            """
            SELECT id
            FROM code_chunks
            WHERE repository_version_id = %s
              AND (
                (
                  websearch_to_tsquery('english', %s)::text <> ''
                  AND content_tsv @@ websearch_to_tsquery('english', %s)
                )
                OR path ILIKE %s
                OR content ILIKE %s
              )
            ORDER BY ts_rank(content_tsv, websearch_to_tsquery('english', %s)) DESC, path, start_line
            LIMIT %s
            """,
            (version_id, query, query, pattern, pattern, query, limit),
        ).fetchall()
    except psycopg.Error:
        connection.rollback()
        rows = connection.execute(
            """
            SELECT id
            FROM code_chunks
            WHERE repository_version_id = %s AND (path ILIKE %s OR content ILIKE %s)
            ORDER BY path, start_line
            LIMIT %s
            """,
            (version_id, pattern, pattern, limit),
        ).fetchall()
    return [row["id"] for row in rows]


def _fuse_scored(rankings: list[list[UUID]]) -> tuple[list[UUID], dict[UUID, float]]:
    """Reciprocal rank fusion: each list adds 1 / (RRF_K + rank) for every item it contains."""

    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for index, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (RRF_K + index)
    return sorted(scores, key=lambda item_id: scores[item_id], reverse=True), scores
