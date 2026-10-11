"""Store and query chunk embeddings."""

from uuid import UUID

import psycopg

from app.search.context import embed_input
from app.search.embedder import DIMENSIONS, VECTOR_MAX_DISTANCE, EmbeddingError, embed_texts, model_name


# Commit after each batch so a status read is not blocked for the whole job,
# and so the header can show how many chunks are done.
EMBED_BATCH = 32


def embed_version(connection: psycopg.Connection, version_id: UUID) -> None:
    try:
        chunks = connection.execute(
            """
            SELECT id, content, header
            FROM code_chunks
            WHERE repository_version_id = %s
            ORDER BY path, start_line
            """,
            (version_id,),
        ).fetchall()
        stored = {
            row["chunk_id"]
            for row in connection.execute(
                """
                SELECT chunk_embeddings.chunk_id
                FROM chunk_embeddings
                JOIN code_chunks ON code_chunks.id = chunk_embeddings.chunk_id
                WHERE code_chunks.repository_version_id = %s
                  AND chunk_embeddings.model_name = %s
                  AND chunk_embeddings.dimensions = %s
                """,
                (version_id, model_name(), DIMENSIONS),
            ).fetchall()
        }
        pending = [row for row in chunks if row["id"] not in stored]
        done = len(chunks) - len(pending)
        _progress(connection, version_id, done, len(chunks))
        connection.commit()
        for start in range(0, len(pending), EMBED_BATCH):
            batch = pending[start : start + EMBED_BATCH]
            vectors = embed_texts([embed_input(row["header"], row["content"]) for row in batch])
            if any(len(vector) != DIMENSIONS for vector in vectors):
                raise EmbeddingError(f"Embeddings must have {DIMENSIONS} dimensions.")
            for row, vector in zip(batch, vectors, strict=True):
                connection.execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, model_name, dimensions, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE
                    SET model_name = EXCLUDED.model_name,
                        dimensions = EXCLUDED.dimensions,
                        embedding = EXCLUDED.embedding
                    """,
                    (row["id"], model_name(), DIMENSIONS, _literal(vector)),
                )
            done += len(batch)
            _progress(connection, version_id, done, len(chunks))
            connection.commit()
        connection.execute(
            """
            UPDATE repository_versions
            SET embedding_status = 'completed', embedding_error = NULL, embedding_model = %s, phase = NULL
            WHERE id = %s
            """,
            (model_name(), version_id),
        )
        connection.commit()
    except (EmbeddingError, psycopg.Error) as exc:
        connection.rollback()
        message = exc.message if isinstance(exc, EmbeddingError) else "Embeddings could not be stored."
        connection.execute(
            """
            UPDATE repository_versions
            SET embedding_status = 'failed', embedding_error = %s
            WHERE id = %s
            """,
            (message, version_id),
        )
        connection.commit()


def vector_ranking(connection: psycopg.Connection, version_id: UUID, query: str, limit: int) -> list[tuple[UUID, float]]:
    status = connection.execute(
        "SELECT embedding_status FROM repository_versions WHERE id = %s",
        (version_id,),
    ).fetchone()
    if status is None or status["embedding_status"] != "completed":
        return []
    try:
        vector = embed_texts([query])[0]
    except EmbeddingError:
        return []
    rows = connection.execute(
        """
        SELECT code_chunks.id, chunk_embeddings.embedding <=> %s::vector AS distance
        FROM chunk_embeddings
        JOIN code_chunks ON code_chunks.id = chunk_embeddings.chunk_id
        WHERE code_chunks.repository_version_id = %s
          AND chunk_embeddings.model_name = %s
          AND chunk_embeddings.dimensions = %s
          AND chunk_embeddings.embedding <=> %s::vector <= %s
        ORDER BY distance
        LIMIT %s
        """,
        ( _literal(vector), version_id, model_name(), DIMENSIONS, _literal(vector), VECTOR_MAX_DISTANCE, limit),
    ).fetchall()
    return [(row["id"], float(row["distance"])) for row in rows]


def _progress(connection: psycopg.Connection, version_id: UUID, done: int, total: int) -> None:
    connection.execute(
        """
        UPDATE repository_versions
        SET phase = 'embedding', progress_completed = %s, progress_total = %s
        WHERE id = %s
        """,
        (done, total, version_id),
    )


def _literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"
