import json

import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.main import create_app
from tests.test_analysis import MAIN, MATH, _seed_snapshot

DATABASE_URL = "postgresql://localhost:5432/repolens_test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.delenv("REPOLENS_CHAT_BASE_URL", raising=False)
    monkeypatch.delenv("REPOLENS_EMBEDDING_BASE_URL", raising=False)
    connection = connect()
    connection.execute("TRUNCATE repositories CASCADE")
    connection.commit()
    connection.close()
    application = create_app(origins=["http://localhost:3000"])

    async def inline(work):
        await work

    application.state.schedule = inline
    return TestClient(application)


def test_search_impact_and_grounded_answer(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    analyzed = client.post(f"/ingestions/{version_id}/analysis")
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["analysis_status"] == "completed"
    assert body["chunk_count"] > 0
    assert body["embedding_status"] == "completed"

    found = client.get(f"/ingestions/{version_id}/search", params={"q": "add"})
    assert found.status_code == 200
    assert any(item["path"] == "src/math.ts" for item in found.json()["results"])
    assert "keyword" in found.json()["results"][0]["methods"]

    impact = client.post(f"/ingestions/{version_id}/impact", json={"name": "add", "depth": 2})
    assert impact.status_code == 200
    assert any(item["name"] == "total" for item in impact.json()["affected"])

    answer = client.post(
        f"/ingestions/{version_id}/questions",
        json={"question": "What does add return?"},
    )
    assert answer.status_code == 200
    payload = done_event(answer.text)
    assert payload["abstained"] is False
    assert any(item["path"] == "src/math.ts" and item["valid"] for item in payload["citations"])
    assert "add returns left + right" in payload["answer"]
    assert "payment" not in payload["answer"].lower()

    paraphrase = client.get(
        f"/ingestions/{version_id}/search",
        params={"q": "how are two numbers summed?"},
    )
    assert paraphrase.status_code == 200
    summed = paraphrase.json()["results"]
    assert any(item["path"] == "src/math.ts" and "vector" in item["methods"] for item in summed)
    assert summed[0]["distance"] is not None
    assert summed[0]["distance"] <= 0.75

    missing = client.post(
        f"/ingestions/{version_id}/questions",
        json={"question": "Where is the billing webhook?"},
    )
    missing_payload = done_event(missing.text)
    assert missing_payload["abstained"] is True
    assert missing_payload["citations"] == []


def test_keyword_search_matches_a_question_whose_words_are_not_all_in_one_chunk(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    assert client.post(f"/ingestions/{version_id}/analysis").status_code == 200

    # "helper" and "numbers" appear nowhere. Before, every word had to match.
    found = client.get(f"/ingestions/{version_id}/search", params={"q": "Where is the add helper used on numbers?"})
    assert found.status_code == 200
    keyword = [item for item in found.json()["results"] if "keyword" in item["methods"]]
    assert {item["path"] for item in keyword} >= {"src/math.ts", "src/main.ts"}


def test_file_path_must_stay_inside_the_snapshot(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH})
    client.post(f"/ingestions/{version_id}/analysis")

    escaped = client.get(f"/ingestions/{version_id}/files", params={"path": "../secrets.ts"})
    assert escaped.status_code == 422
    assert escaped.json()["error_code"] == "invalid_path"

    opened = client.get(f"/ingestions/{version_id}/files", params={"path": "src/math.ts", "start_line": 1, "end_line": 1})
    assert opened.status_code == 200
    assert "export function add" in opened.json()["content"]


def done_event(body: str) -> dict:
    payload = None
    for block in body.split("\n\n"):
        event = next((line[7:] for line in block.splitlines() if line.startswith("event: ")), None)
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if event == "done" and data:
            payload = json.loads(data)
    if payload is None:
        raise AssertionError(body)
    return payload


def events(body: str) -> list[tuple[str, dict]]:
    found = []
    for block in body.split("\n\n"):
        event = next((line[7:] for line in block.splitlines() if line.startswith("event: ")), None)
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if event and data:
            found.append((event, json.loads(data)))
    return found


def test_retrieval_lab_reports_rrf_scores_and_timings(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    client.post(f"/ingestions/{version_id}/analysis")

    response = client.get(f"/ingestions/{version_id}/retrieval", params={"q": "add", "limit": 5})
    assert response.status_code == 200
    body = response.json()
    assert set(body["strategies"]) == {"keyword", "vector", "hybrid", "reranked"}
    assert {"keyword", "vector", "fuse"} <= set(body["timings_ms"])
    assert all(value >= 0 for value in body["timings_ms"].values())
    hybrid = body["strategies"]["hybrid"]
    assert hybrid
    assert [hit["rank"] for hit in hybrid] == list(range(1, len(hybrid) + 1))
    for hit in hybrid:
        expected = sum(1 / (60 + rank) for rank in (hit["keyword_rank"], hit["vector_rank"]) if rank is not None)
        assert hit["rrf_score"] == pytest.approx(expected, abs=1e-5)
    scores = [hit["rrf_score"] for hit in hybrid]
    assert scores == sorted(scores, reverse=True)


def test_answer_stream_sends_the_pipeline_before_the_answer(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    client.post(f"/ingestions/{version_id}/analysis")

    streamed = events(client.post(f"/ingestions/{version_id}/questions", json={"question": "What does add return?"}).text)
    names = [name for name, _data in streamed]
    assert "retrieval" in names
    assert names.index("retrieval") < names.index("token")
    done = dict(streamed)["done"]
    pipeline = done["pipeline"]
    assert pipeline["embedding_model"] == "jinaai/jina-embeddings-v2-base-code"
    assert pipeline["context"]["chunks"] == len(done["citations"])
    assert pipeline["context"]["approx_tokens"] == pipeline["context"]["chars"] // 4
    assert pipeline["generator"] == "extractive"
    assert pipeline["abstained"] is False
    assert "generate" in pipeline["timings_ms"]
    assert pipeline["stages"]["hybrid"]
    assert "snippet" not in pipeline["stages"]["hybrid"][0]

    missing = dict(events(client.post(f"/ingestions/{version_id}/questions", json={"question": "Where is the billing webhook?"}).text))["done"]
    assert missing["abstained"] is True
    assert missing["pipeline"]["abstained"] is True
    assert missing["pipeline"]["context"]["chunks"] == 0


def test_inline_golden_set_is_scored_and_validated(client) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    client.post(f"/ingestions/{version_id}/analysis")
    url = f"/ingestions/{version_id}/evaluation"

    scored = client.post(url, json={"questions": [{"question": "add", "expected_paths": ["src/math.ts"]}], "k": 3})
    assert scored.status_code == 200
    body = scored.json()
    assert body["dataset"] == "lab-golden-set"
    assert body["summary"]["hybrid"]["recall_at_k"] == 1.0
    assert client.get(url).json()["runs"][0]["dataset"] == "lab-golden-set"

    too_many = [{"question": "add", "expected_paths": ["src/math.ts"]}] * 21
    assert client.post(url, json={"questions": too_many}).status_code == 422
    assert client.post(url, json={"questions": [{"question": "add", "expected_paths": []}]}).status_code == 422
    assert client.post(url, json={"questions": [{"question": "add", "expected_paths": ["../secrets.ts"]}]}).status_code == 422
    both = {"dataset": "example", "questions": [{"question": "add", "expected_paths": ["src/math.ts"]}]}
    assert client.post(url, json=both).status_code == 422
    assert client.post(url, json={}).status_code == 422


def test_config_does_not_expose_secrets(client, monkeypatch) -> None:
    monkeypatch.setenv("REPOLENS_CHAT_API_KEY", "secret-value")
    response = client.get("/config")
    assert response.status_code == 200
    assert "secret-value" not in response.text
    assert response.json()["embedding_model"] == "jinaai/jina-embeddings-v2-base-code"
    assert response.json()["embedding_dimensions"] == 768
