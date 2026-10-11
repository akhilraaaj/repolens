"""Resolve the active chat provider from the database, then from the environment."""

import os

import psycopg

from app.llm.ollama import Ollama
from app.llm.openai_compatible import OpenAICompatible
from app.llm.store import read_provider


def get_provider(connection: psycopg.Connection):
    row = read_provider(connection)
    if row is not None and row["provider"] not in {None, "none"} and row["base_url"] and row["model"]:
        if row["provider"] == "ollama":
            return Ollama(base_url=row["base_url"], model=row["model"])
        return OpenAICompatible(base_url=row["base_url"], model=row["model"], api_key=row["api_key"])
    return _from_env()


def _from_env():
    base_url = os.environ.get("REPOLENS_CHAT_BASE_URL", "").strip()
    model = os.environ.get("REPOLENS_CHAT_MODEL", "").strip()
    api_key = os.environ.get("REPOLENS_CHAT_API_KEY", "").strip()
    if not base_url or not model or not api_key:
        return None
    return OpenAICompatible(base_url=base_url, model=model, api_key=api_key)


def provider_label(connection: psycopg.Connection) -> str | None:
    provider = get_provider(connection)
    if provider is None:
        return None
    return getattr(provider, "model", None)
