"""One row of provider settings. The API key is never copied into a response."""

from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg

PROVIDERS = {"ollama", "openai_compatible", "none"}


def read_provider(connection: psycopg.Connection) -> dict | None:
    return connection.execute(
        "SELECT provider, base_url, model, api_key FROM provider_settings WHERE id = 1"
    ).fetchone()


def public_provider(row: dict | None) -> dict:
    if row is None:
        return {"configured": False, "provider": None, "base_url": None, "model": None, "has_api_key": False}
    return {
        "configured": True,
        "provider": row["provider"],
        "base_url": row["base_url"],
        "model": row["model"],
        "has_api_key": bool(row["api_key"]),
    }


def save_provider(
    connection: psycopg.Connection,
    *,
    provider: str,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    keep_api_key: bool,
) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Choose local Ollama, a hosted OpenAI-compatible model, or none.")
    if provider == "none":
        base_url, model = None, None
        api_key = None
        keep_api_key = False
    else:
        base_url = _base_url(base_url)
        model = (model or "").strip()
        if model == "" or len(model) > 120:
            raise ValueError("A model name is required.")
    existing = read_provider(connection)
    stored_key = existing["api_key"] if existing and keep_api_key else None
    if api_key is not None and not keep_api_key:
        stored_key = api_key.strip() or None
    connection.execute(
        """
        INSERT INTO provider_settings (id, provider, base_url, model, api_key, updated_at)
        VALUES (1, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET provider = EXCLUDED.provider,
            base_url = EXCLUDED.base_url,
            model = EXCLUDED.model,
            api_key = EXCLUDED.api_key,
            updated_at = EXCLUDED.updated_at
        """,
        (provider, base_url, model, stored_key, datetime.now(timezone.utc)),
    )
    connection.commit()
    saved = read_provider(connection)
    return public_provider(saved)


def _base_url(value: str | None) -> str:
    raw = (value or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("The base URL must be an http or https address.")
    if parsed.username or parsed.password:
        raise ValueError("Put the API key in the key field, not in the URL.")
    if len(raw) > 300:
        raise ValueError("That base URL is too long.")
    return raw.rstrip("/")
