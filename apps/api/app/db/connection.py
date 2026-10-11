"""Database connections for ingestion records."""

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class DatabaseUnavailable(Exception):
    """The ingestion store cannot be reached."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseUnavailable("DATABASE_URL is not set.")
    return url


def connect() -> psycopg.Connection:
    try:
        connection = psycopg.connect(database_url(), row_factory=dict_row)
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailable("The database is not reachable.") from exc
    apply_schema(connection)
    return connection


def apply_schema(connection: psycopg.Connection) -> None:
    statements = [part.strip() for part in SCHEMA_PATH.read_text().split(";") if part.strip()]
    vector_ready = _ensure_vector(connection)
    for statement in statements:
        if not vector_ready and ("vector(" in statement or "vector_cosine_ops" in statement):
            continue
        if statement.startswith("ALTER TABLE"):
            table, column = _alter_target(statement)
            if _column_exists(connection, table, column):
                continue
        connection.execute(statement)
    if vector_ready:
        _migrate_embedding_width(connection)
        _ensure_hnsw(connection)
    connection.commit()


def _migrate_embedding_width(connection: psycopg.Connection) -> None:
    """Widen an older vector(384) column. Stored vectors cannot be reused."""

    row = connection.execute(
        """
        SELECT a.atttypmod AS dim
        FROM pg_attribute AS a
        JOIN pg_class AS c ON c.oid = a.attrelid
        WHERE c.relname = 'chunk_embeddings' AND a.attname = 'embedding' AND NOT a.attisdropped
        """
    ).fetchone()
    if row is None or row["dim"] == 768:
        return
    connection.execute("DROP INDEX IF EXISTS chunk_embeddings_hnsw_idx")
    connection.execute("DELETE FROM chunk_embeddings")
    connection.execute("ALTER TABLE chunk_embeddings ALTER COLUMN embedding TYPE vector(768)")
    connection.execute(
        """
        UPDATE repository_versions
        SET embedding_status = NULL,
            embedding_model = NULL,
            embedding_error = 'Embeddings were cleared because the vector width changed to 768. Rebuild to re-index.'
        WHERE embedding_status IS NOT NULL
        """
    )


def _ensure_hnsw(connection: psycopg.Connection) -> None:
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS chunk_embeddings_hnsw_idx
        ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)
        """
    )


def _ensure_vector(connection: psycopg.Connection) -> bool:
    try:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except psycopg.Error:
        connection.rollback()
        return False
    return True


def _alter_target(statement: str) -> tuple[str, str]:
    parts = statement.split()
    return parts[2], parts[8]


def _column_exists(connection: psycopg.Connection, table: str, column: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()
    return row is not None
