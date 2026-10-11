import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.connection import connect
from app.main import create_app
from app.overview.detect import Manifest, detect_entry_points, detect_stack, folder_roles, language_breakdown
from app.overview.rank import pagerank
from app.overview.modules import core_modules
from tests.test_analysis import DATABASE_URL, _seed_snapshot


def test_pagerank_favors_shared_dependencies_and_sums_to_one() -> None:
    rank = pagerank(
        ["main", "page", "util", "orphan"],
        [("main", "page", 1.0), ("page", "util", 1.0), ("main", "util", 3.0)],
    )

    assert abs(sum(rank.values()) - 1.0) < 1e-6
    assert rank["util"] > rank["page"] > rank["main"]
    assert rank["orphan"] == pytest.approx(rank["main"])
    assert pagerank([], []) == {}


def test_pagerank_ignores_self_loops_and_unknown_nodes() -> None:
    rank = pagerank(["a", "b"], [("a", "a", 5.0), ("a", "ghost", 1.0), ("a", "b", 1.0)])

    assert rank["b"] > rank["a"]


def test_stack_reads_dependencies_and_marker_files_in_category_order() -> None:
    manifest = Manifest(
        path="package.json",
        data={
            "dependencies": {"react": "^19.0.0", "next": "16.0.0", "@radix-ui/react-dialog": "1"},
            "devDependencies": {"tailwindcss": "4", "vitest": "3", "left-pad": "1"},
        },
    )

    stack = detect_stack([manifest], ["package.json", "Dockerfile", "deep/nested/go.mod"])

    names = [item["name"] for item in stack]
    assert names[:2] == ["Next.js", "React"]
    assert "Radix UI" in names and "Tailwind CSS" in names and "Vitest" in names and "Docker" in names
    assert "Go" not in names
    assert "left-pad" not in " ".join(names)
    tailwind = next(item for item in stack if item["name"] == "Tailwind CSS")
    assert tailwind["dev"] is True and tailwind["evidence"] == "package.json"


def test_entry_points_follow_manifests_html_scripts_and_conventions() -> None:
    paths = ["package.json", "src/index.ts", "src/cli.ts", "index.html", "src/main.tsx", "scripts/build.mjs", "server.js"]
    manifest = Manifest(
        path="package.json",
        data={
            "main": "dist/index.js",
            "bin": {"tool": "./dist/cli.js", "escape": "../../etc/passwd"},
            "scripts": {"build": "node scripts/build.mjs --prod", "weird": "FOO=1 $CMD"},
        },
    )
    html = {"index.html": '<script type="module" src="/src/main.tsx"></script><script src="https://cdn.example/x.js"></script>'}

    entries = detect_entry_points([manifest], paths, html, set())

    by_path = {entry["path"]: entry for entry in entries}
    assert by_path["src/index.ts"]["kind"] == "package"
    assert by_path["src/cli.ts"]["kind"] == "bin"
    assert by_path["src/main.tsx"]["kind"] == "html"
    assert by_path["scripts/build.mjs"]["kind"] == "script"
    assert by_path["server.js"]["kind"] == "convention"
    assert all(not entry["path"].startswith("..") for entry in entries)


def test_next_routes_count_only_when_next_is_in_the_stack() -> None:
    paths = ["app/layout.tsx", "app/page.tsx", "app/blog/[slug]/page.tsx", "src/pages/Home.jsx"]

    with_next = detect_entry_points([], paths, {}, {"Next.js"})
    without = detect_entry_points([], paths, {}, set())

    assert [entry["path"] for entry in with_next][:2] == ["app/layout.tsx", "app/page.tsx"]
    assert all(entry["kind"] != "route" for entry in without)


def test_folder_roles_use_names_then_contents_and_count_cross_folder_edges() -> None:
    paths = ["src/components/Button.tsx", "src/components/Card.tsx", "src/hooks/useX.ts", "notes/a.md", "notes/b.md", "misc/x.ts", "README.md"]
    edges = [{"source": "src/components/Card.tsx", "target": "src/hooks/useX.ts"}]

    rows = {row["path"]: row for row in folder_roles(paths, edges, {"src/components/Card.tsx": 0.3})}

    assert rows["src/components"]["role"] == "UI components" and rows["src/components"]["basis"] == "name"
    assert rows["src/components"]["depends_on"] == 1 and rows["src/hooks"]["used_by"] == 1
    assert rows["src/components"]["key_files"] == ["src/components/Card.tsx"]
    assert rows["notes"]["role"] == "Documentation" and rows["notes"]["basis"] == "contents"
    assert rows["misc"]["role"] is None
    assert "README.md" not in rows


def test_language_breakdown_weights_by_bytes() -> None:
    rows = language_breakdown([("a.ts", 300), ("b.tsx", 100), ("c.py", 100), ("logo.png", 9000)])

    assert rows[0] == {"language": "TypeScript", "files": 2, "bytes": 400, "share": 0.8}
    assert [row["language"] for row in rows] == ["TypeScript", "Python"]


def test_core_modules_rank_files_other_files_depend_on() -> None:
    files = [
        {"path": "src/main.ts", "top_symbols": []},
        {"path": "src/app.ts", "top_symbols": [{"name": "App", "entity_type": "function", "start_line": 3, "end_line": 9, "exported": True}]},
        {"path": "src/util.ts", "top_symbols": []},
    ]
    edges = [
        {"source": "src/main.ts", "target": "src/app.ts", "kinds": {"imports": 1}},
        {"source": "src/app.ts", "target": "src/util.ts", "kinds": {"imports": 1}},
        {"source": "src/main.ts", "target": "src/util.ts", "kinds": {"imports": 1}},
    ]
    rank = pagerank([item["path"] for item in files], [(edge["source"], edge["target"], 1.0) for edge in edges])

    core = core_modules(files, edges, rank)

    assert [row["path"] for row in core] == ["src/util.ts", "src/app.ts"]
    assert core[0]["score"] == 1.0
    assert core[1]["symbol"]["name"] == "App"


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    connection = connect()
    connection.execute("TRUNCATE repositories CASCADE")
    connection.commit()
    connection.close()
    application = create_app(origins=["http://localhost:3000"])

    async def inline(work):
        await work

    application.state.schedule = inline
    return application


def test_overview_endpoint_builds_a_brief(api) -> None:
    manifest = json.dumps(
        {"name": "demo", "description": "A demo   app.", "scripts": {"dev": "vite"}, "dependencies": {"react": "19"}, "devDependencies": {"vite": "7"}},
        indent=2,
    )
    version_id = _seed_snapshot(
        {
            "package.json": manifest,
            "README.md": "# Demo\n\nRun it.\n",
            "index.html": '<div id="root"></div><script type="module" src="/src/main.tsx"></script>\n',
            "src/main.tsx": 'import { App } from "./App";\nApp();\n',
            "src/App.tsx": 'import { slug } from "./lib/text";\nexport function App() {\n  return slug("x");\n}\n',
            "src/lib/text.ts": "export function slug(value: string) {\n  return value;\n}\n",
        }
    )
    client = TestClient(api)
    client.post(f"/ingestions/{version_id}/analysis")

    response = client.get(f"/ingestions/{version_id}/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "demo" and body["description"] == "A demo app."
    assert [item["name"] for item in body["stack"]] == ["React", "Vite"]
    assert body["entry_points"][0] == {
        "path": "src/main.tsx",
        "kind": "html",
        "reason": "Loaded by a script tag in index.html.",
        "evidence": "index.html",
    }
    assert body["core_modules"][0]["path"] == "src/lib/text.ts"
    assert "tour" not in body
    assert body["summary"]["graph_files"] == 3
    assert body["notes"] == []


def test_documentation_opens_with_an_overview(api, monkeypatch) -> None:
    monkeypatch.setattr("app.overview.docs.get_provider", lambda connection: None)
    version_id = _seed_snapshot(
        {
            "package.json": json.dumps(
                {"name": "demo", "description": "A demo app.", "dependencies": {"react": "19"}, "devDependencies": {"vite": "7"}}
            ),
            "README.md": "# Demo\n\nThis template provides a minimal setup to get React working in Vite.\n",
            "index.html": '<script type="module" src="/src/main.tsx"></script>\n',
            "src/main.tsx": "export {}\n",
            "src/components/Button.tsx": "export {}\n",
        }
    )
    client = TestClient(api)

    response = client.get(f"/ingestions/{version_id}/documentation")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "demo"
    assert body["sections"][0]["id"] == "overview"
    overview = " ".join(body["sections"][0]["paragraphs"])
    assert overview.startswith("demo is a demo app.")
    assert "This template provides a minimal setup to get React working in Vite." in overview
    assert "This snapshot stores 5 files." in overview
    assert "React draws the interface." in overview
    assert "Development also uses Vite." in overview
    assert "built with React, Vite" not in overview
    start = " ".join(body["sections"][1]["paragraphs"])
    assert "src/main.tsx is loaded by a script tag in index.html" in start
    assert "src/components holds the UI components in Button.tsx." in start
    assert body["model"] is None


def test_documentation_uses_the_configured_model_and_caches_it(api, monkeypatch) -> None:
    from app.llm.types import ModelTurn

    version_id = _seed_snapshot(
        {
            "package.json": json.dumps({"name": "demo", "description": "A demo app."}),
            "src/main.tsx": "export {}\n",
        }
    )
    calls = {"n": 0}

    class Fake:
        model = "openrouter/free"

        def complete(self, messages, tools=None, timeout=None):
            calls["n"] += 1
            assert "Package name: demo" in messages[-1]["content"]
            return ModelTurn(
                content=json.dumps(
                    {
                        "title": "demo",
                        "sections": [
                            {"heading": "What this is", "paragraphs": ["demo is a small app that starts in src/main.tsx."]},
                            {"heading": "Read this first", "paragraphs": ["Open src/main.tsx."]},
                        ],
                    }
                )
            )

    monkeypatch.setattr("app.overview.docs.get_provider", lambda connection: Fake())
    client = TestClient(api)

    first = client.get(f"/ingestions/{version_id}/documentation")
    second = client.get(f"/ingestions/{version_id}/documentation")

    assert first.status_code == 200
    body = first.json()
    assert body["model"] == "openrouter/free"
    assert body["sections"][0]["heading"] == "What this is"
    assert body["sections"][0]["sources"] == [{"path": "src/main.tsx"}]
    assert second.json()["sections"][1]["heading"] == "Read this first"
    assert calls["n"] == 1


def test_a_dead_embedding_job_is_no_longer_reported_as_running(api) -> None:
    from app.analysis.active import clear_active, mark_active

    version_id = _seed_snapshot({"src/main.ts": "export {}\n"})
    connection = connect()
    connection.execute(
        """
        UPDATE repository_versions
        SET analysis_status = 'completed', embedding_status = 'running', embedding_error = NULL
        WHERE id = %s
        """,
        (version_id,),
    )
    connection.commit()
    connection.close()
    client = TestClient(api)
    mark_active(UUID(version_id))
    try:
        owned = client.get(f"/ingestions/{version_id}").json()
    finally:
        clear_active(UUID(version_id))

    abandoned = client.get(f"/ingestions/{version_id}").json()

    assert owned["embedding_status"] == "running"
    assert abandoned["embedding_status"] == "failed"
    assert "API restarted" in abandoned["embedding_error"]


def test_overview_for_an_unknown_ingestion_is_404(api) -> None:
    client = TestClient(api)

    assert client.get(f"/ingestions/{uuid4()}/overview").status_code == 404
    assert client.get("/ingestions/not-a-uuid/overview").status_code == 404
