from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.analysis.parser import ANALYZER_DIR, run_parser
from app.db.connection import connect
from app.db.store import upsert_repository
from app.main import create_app

DATABASE_URL = "postgresql://localhost:5432/repolens_test"
MATH = "export function add(left: number, right: number): number {\n  return left + right;\n}\n"
MAIN = 'import { add } from "./math";\nimport { useState } from "react";\nexport function total(): number {\n  return add(1, 2);\n}\n'
BROKEN = "export function {\n"


def test_parser_resolves_a_relative_import_and_call() -> None:
    result = run_parser(
        [
            {"path": "src/math.ts", "content": MATH},
            {"path": "src/main.ts", "content": MAIN},
            {"path": "src/bad.ts", "content": BROKEN},
        ],
        timeout_seconds=30,
    )

    assert result.parser_name == "typescript"
    imports = [item for item in result.relationships if item.relationship_type == "imports"]
    verified = next(item for item in imports if item.specifier == "./math")
    unresolved = next(item for item in imports if item.specifier == "react")
    call = next(item for item in result.relationships if item.relationship_type == "calls")
    assert verified.resolution_status == "verified"
    assert verified.target_local_id == "src/math.ts#module@1"
    assert unresolved.resolution_status == "unresolved"
    assert unresolved.target_local_id is None
    assert call.resolution_status == "resolved"
    assert call.target_local_id == "src/math.ts#add@1"
    assert call.source_local_id == "src/main.ts#total@3"
    failed = next(item for item in result.files if item.path == "src/bad.ts")
    assert failed.parse_status == "failed"
    assert any(item.path == "src/math.ts" and item.entity_type == "function" and item.name == "add" for item in result.symbols)


def test_parser_follows_aliases_require_jsx_and_property_calls() -> None:
    tsconfig = '{\n  // comments are allowed\n  "compilerOptions": { "baseUrl": ".", "paths": { "@/*": ["src/*"] } }\n}\n'
    button = "export function Button() {\n  return null;\n}\n"
    helpers = "export const helpers = {\n  fmt(value: string) { return value; },\n};\nexport function slug(value: string) {\n  return value;\n}\n"
    legacy = "module.exports = { a: 1 };\n"
    page = (
        'import { Button } from "@/ui/button";\n'
        'import * as text from "@/text";\n'
        'const legacy = require("./legacy");\n'
        "export function Page() {\n"
        "  text.slug(\"x\");\n"
        "  return <Button />;\n"
        "}\n"
    )
    result = run_parser(
        [
            {"path": "src/ui/button.tsx", "content": button},
            {"path": "src/text.ts", "content": helpers},
            {"path": "src/legacy.js", "content": legacy},
            {"path": "src/page.tsx", "content": page},
        ],
        timeout_seconds=30,
        config={"path": "tsconfig.json", "content": tsconfig},
    )

    imports = {item.specifier: item for item in result.relationships if item.relationship_type == "imports"}
    assert imports["@/ui/button"].resolution_status == "resolved"
    assert imports["@/ui/button"].target_local_id == "src/ui/button.tsx#module@1"
    assert imports["./legacy"].resolution_status == "verified"
    renders = [item for item in result.relationships if item.relationship_type == "renders"]
    assert [(item.source_local_id, item.target_local_id) for item in renders] == [
        ("src/page.tsx#Page@4", "src/ui/button.tsx#Button@1")
    ]
    calls = [item for item in result.relationships if item.relationship_type == "calls"]
    assert any(item.target_local_id == "src/text.ts#slug@4" and item.target_name == "slug" for item in calls)


def test_alias_without_config_stays_unresolved() -> None:
    result = run_parser(
        [
            {"path": "src/ui/button.tsx", "content": "export function Button() { return null; }\n"},
            {"path": "src/page.tsx", "content": 'import { Button } from "@/ui/button";\n'},
        ],
        timeout_seconds=30,
    )
    alias = next(item for item in result.relationships if item.specifier == "@/ui/button")
    assert alias.resolution_status == "unresolved"


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


def test_analysis_persists_the_graph_and_a_rerun_does_not_duplicate_it(api) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN, "src/bad.ts": BROKEN, "types.d.ts": "export type Id = string;\n"})
    client = TestClient(api)

    first = client.post(f"/ingestions/{version_id}/analysis")
    second = client.post(f"/ingestions/{version_id}/analysis")

    assert first.status_code == 200
    body = first.json()
    assert body["analysis_status"] == "completed_with_errors"
    assert body["parser_version"] == "6.0.3"
    assert body["unresolved_count"] == 1
    assert second.status_code == 200
    assert second.json()["symbol_count"] == body["symbol_count"]
    connection = connect()
    count = connection.execute("SELECT count(*) AS count FROM symbols").fetchone()
    declaration = connection.execute(
        "SELECT parse_status FROM files WHERE path = 'types.d.ts'"
    ).fetchone()
    connection.close()
    assert count["count"] == body["symbol_count"]
    assert declaration["parse_status"] == "skipped"
    graph = client.get(f"/ingestions/{version_id}/graph", params={"resolution_status": "unresolved", "limit": 20})
    assert graph.status_code == 200
    assert graph.json()["relationships"][0]["specifier"] == "react"
    limited = client.get(f"/ingestions/{version_id}/graph", params={"limit": 1})
    assert limited.json()["truncated"] is True
    assert len(limited.json()["symbols"]) == 1


def test_file_graph_collapses_symbol_edges_and_lists_packages(api) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH, "src/main.ts": MAIN})
    client = TestClient(api)
    client.post(f"/ingestions/{version_id}/analysis")

    response = client.get(f"/ingestions/{version_id}/graph/files")

    assert response.status_code == 200
    body = response.json()
    assert {item["path"] for item in body["files"]} == {"src/math.ts", "src/main.ts"}
    edge = next(item for item in body["edges"] if item["source"] == "src/main.ts")
    assert edge["target"] == "src/math.ts"
    assert edge["kinds"] == {"imports": 1, "calls": 1}
    assert edge["status"] == "verified"
    assert body["packages"] == [{"name": "react", "importers": ["src/main.ts"]}]
    math = next(item for item in body["files"] if item["path"] == "src/math.ts")
    assert math["top_symbols"][0]["name"] == "add"


def test_package_names_drop_subpaths_and_aliases() -> None:
    from app.analysis.store import package_name

    assert package_name("react-dom/client") == "react-dom"
    assert package_name("@tanstack/react-query/devtools") == "@tanstack/react-query"
    assert package_name("@/lib/utils") is None


def test_analysis_waits_until_a_snapshot_is_stored(api) -> None:
    version_id = _seed_snapshot({"src/math.ts": MATH}, status="failed")

    response = TestClient(api).post(f"/ingestions/{version_id}/analysis")

    assert response.status_code == 409
    assert response.json()["error_code"] == "analysis_not_ready"


def test_parser_script_is_present() -> None:
    assert (ANALYZER_DIR / "parse.mjs").is_file()
    assert (ANALYZER_DIR / "node_modules" / "typescript" / "package.json").is_file()


def _seed_snapshot(files: dict[str, str], *, status: str = "completed") -> str:
    connection = connect()
    repository_id = upsert_repository(
        connection,
        owner="fixture",
        name="graph",
        canonical_url="https://github.com/fixture/graph",
        default_branch="main",
    )
    version_id = uuid4()
    now = datetime.now(timezone.utc)
    connection.execute(
        """
        INSERT INTO repository_versions (
            id, repository_id, commit_sha, requested_ref, status, analysis_status, started_at, finished_at
        )
        VALUES (%s, %s, %s, 'main', %s, 'not_started', %s, %s)
        """,
        (version_id, repository_id, "b" * 40, status, now, now),
    )
    for path, content in files.items():
        connection.execute(
            """
            INSERT INTO files (
                id, repository_version_id, path, disposition, size_bytes, content
            )
            VALUES (%s, %s, %s, 'stored', %s, %s)
            """,
            (uuid4(), version_id, path, len(content.encode()), content),
        )
    connection.commit()
    connection.close()
    return str(version_id)
