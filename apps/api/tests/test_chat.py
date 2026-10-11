from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.answers.agent import execute_tool
from app.answers.validate import validate_answer
from app.db.connection import connect
from app.main import create_app
from tests.test_analysis import _seed_snapshot
from tests.test_mvp import DATABASE_URL, done_event


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.delenv("REPOLENS_CHAT_BASE_URL", raising=False)
    monkeypatch.delenv("REPOLENS_CHAT_MODEL", raising=False)
    connection = connect()
    connection.execute("TRUNCATE repositories CASCADE")
    connection.commit()
    connection.close()
    application = create_app(origins=["http://localhost:3000"])

    async def inline(work):
        await work

    application.state.schedule = inline
    return TestClient(application)


def test_uncited_paragraphs_are_dropped() -> None:
    text = "The function adds two numbers [1].\n\nIt also charges a card.\n\nSee [9] for the secret."
    cleaned, used, abstained = validate_answer(text, 2)

    assert abstained is False
    assert used == [1]
    assert "charges" not in cleaned
    assert "[9]" not in cleaned
    assert "[1]" in cleaned


def test_an_answer_with_no_valid_citation_abstains() -> None:
    cleaned, used, abstained = validate_answer("This invents a billing webhook [4].", 1)
    assert abstained is True
    assert used == []
    assert cleaned.startswith("I do not have source evidence")


def test_provider_settings_never_return_the_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    connection = connect()
    connection.execute("DELETE FROM provider_settings")
    connection.commit()
    connection.close()
    from app.main import create_app

    client = TestClient(create_app(origins=["http://localhost:3000"]))
    saved = client.post(
        "/provider",
        json={"provider": "openai_compatible", "base_url": "https://example.test/v1", "model": "demo", "api_key": "sk-secret"},
    )
    assert saved.status_code == 200
    assert "sk-secret" not in saved.text
    assert saved.json()["has_api_key"] is True
    again = client.post(
        "/provider",
        json={"provider": "openai_compatible", "base_url": "https://example.test/v1", "model": "demo"},
    )
    assert again.json()["has_api_key"] is True
    cleared = client.post("/provider", json={"provider": "none"})
    assert cleared.json()["provider"] == "none"
    assert client.get("/provider").json()["has_api_key"] is False


def test_env_chat_is_used_when_the_saved_provider_is_none(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("REPOLENS_CHAT_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("REPOLENS_CHAT_MODEL", "openrouter/free")
    monkeypatch.setenv("REPOLENS_CHAT_API_KEY", "sk-test")
    from app.llm.registry import get_provider
    from app.llm.store import save_provider

    connection = connect()
    try:
        save_provider(connection, provider="none", base_url=None, model=None, api_key=None, keep_api_key=False)
        provider = get_provider(connection)
    finally:
        connection.close()
    assert provider is not None
    assert provider.model == "openrouter/free"
    assert provider.api_key == "sk-test"


def test_provider_rejects_a_key_hidden_in_the_url(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    from app.main import create_app

    client = TestClient(create_app(origins=["http://localhost:3000"]))
    response = client.post(
        "/provider",
        json={"provider": "ollama", "base_url": "http://user:secret@127.0.0.1:11434", "model": "qwen"},
    )
    assert response.status_code == 422
    assert "secret" not in response.text


def test_tool_file_reads_reject_paths_outside_the_snapshot(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    connection = connect()
    connection.execute("TRUNCATE repositories CASCADE")
    connection.commit()
    connection.close()
    version_id = _seed_snapshot({"src/math.ts": "export function add() { return 1; }\n"})
    connection = connect()
    try:
        text, paths = execute_tool(connection, UUID(version_id), "get_file", {"path": "../secrets.ts"})
    finally:
        connection.close()
    assert paths == []
    assert "not valid" in text


def test_a_repository_question_reads_the_readme_when_search_misses(client) -> None:
    version_id = _seed_snapshot(
        {
            "README.md": "# React + Vite\n\nThis template provides a minimal setup to get React working in Vite.\n",
            "package.json": '{\n  "name": "crypto-tracker"\n}\n',
        }
    )
    assert client.post(f"/ingestions/{version_id}/analysis").status_code == 200
    done = done_event(client.post(f"/ingestions/{version_id}/questions", json={"question": "What does this repository do?"}).text)
    assert done["abstained"] is False
    assert any(item["path"] == "README.md" for item in done["citations"])
    assert "React" in done["answer"]


def test_a_follow_up_stays_on_the_same_thread(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": "export function add(left: number, right: number) { return left + right; }\n"})
    client.post(f"/ingestions/{version_id}/analysis")
    first = done_event(client.post(f"/ingestions/{version_id}/questions", json={"question": "What does add return?"}).text)
    second = done_event(
        client.post(
            f"/ingestions/{version_id}/questions",
            json={"question": "Where is add defined?", "thread_id": first["thread_id"]},
        ).text
    )
    assert second["thread_id"] == first["thread_id"]
    missing = client.post(
        f"/ingestions/{version_id}/questions",
        json={"question": "again", "thread_id": str(uuid4())},
    )
    assert "event: error" in missing.text
