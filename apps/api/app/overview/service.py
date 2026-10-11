"""Assemble the Repo Brief for one snapshot.

The brief is computed on request from stored files and the file graph. It uses
no model, so it works offline and always gives the same answer for a commit.
"""

import posixpath
from uuid import UUID

import psycopg

from app.analysis.store import load_file_graph
from app.overview.detect import (
    detect_entry_points,
    detect_stack,
    folder_roles,
    language_breakdown,
    parse_manifest,
    short_text,
)
from app.overview.rank import pagerank
from app.overview.modules import core_modules

MAX_MANIFESTS = 25
MAX_MANIFEST_DEPTH = 2
MAX_HTML_DEPTH = 1


def build_overview(connection: psycopg.Connection, version_id: UUID) -> dict | None:
    version = connection.execute(
        "SELECT analysis_status FROM repository_versions WHERE id = %s",
        (version_id,),
    ).fetchone()
    if version is None:
        return None
    stored = connection.execute(
        """
        SELECT path, coalesce(size_bytes, 0) AS size_bytes
        FROM files
        WHERE repository_version_id = %s AND disposition = 'stored'
        ORDER BY path
        """,
        (version_id,),
    ).fetchall()
    paths = [row["path"] for row in stored]
    texts = _read_texts(connection, version_id, paths)

    manifests = []
    for path in sorted((path for path in texts if posixpath.basename(path) == "package.json"), key=lambda path: (path.count("/"), path)):
        manifest = parse_manifest(path, texts[path])
        if manifest is not None:
            manifests.append(manifest)
    html_pages = {path: texts[path] for path in texts if posixpath.basename(path) == "index.html"}

    graph = load_file_graph(connection, version_id) or {"files": [], "edges": [], "truncated": False}
    graph_files = graph["files"]
    edges = graph["edges"]
    rank = pagerank(
        [item["path"] for item in graph_files],
        [(edge["source"], edge["target"], float(sum(edge["kinds"].values()))) for edge in edges],
    )

    stack = detect_stack(manifests, paths)
    entries = detect_entry_points(manifests, paths, html_pages, {item["name"] for item in stack})
    core = core_modules(graph_files, edges, rank)
    root = manifests[0] if manifests and manifests[0].directory == "" else None

    notes = []
    if not graph_files:
        notes.append("No JavaScript or TypeScript files were parsed, so core modules rely on file names only.")
    if graph.get("truncated"):
        notes.append("The file graph hit its size limit; ranking covers the files that fit.")
    if not manifests:
        notes.append("No package.json was found; the stack comes from marker files only.")
    if not entries:
        notes.append("No entry point was declared in a manifest, an HTML page, a script, or a conventional file name.")

    return {
        "analysis_status": version["analysis_status"],
        "name": short_text(root.data.get("name")) if root else None,
        "description": short_text(root.data.get("description")) if root else None,
        "summary": {
            "files": len(paths),
            "bytes": sum(row["size_bytes"] for row in stored),
            "graph_files": len(graph_files),
            "graph_edges": len(edges),
            "languages": language_breakdown([(row["path"], row["size_bytes"]) for row in stored]),
        },
        "stack": stack,
        "entry_points": entries,
        "core_modules": core,
        "folders": folder_roles(paths, edges, rank),
        "notes": notes,
    }


def _read_texts(connection: psycopg.Connection, version_id: UUID, paths: list[str]) -> dict[str, str]:
    wanted = [
        path
        for path in paths
        if (posixpath.basename(path) == "package.json" and path.count("/") <= MAX_MANIFEST_DEPTH)
        or (posixpath.basename(path) == "index.html" and path.count("/") <= MAX_HTML_DEPTH)
    ]
    manifests = [path for path in wanted if path.endswith("package.json")]
    if len(manifests) > MAX_MANIFESTS:
        drop = set(sorted(manifests, key=lambda path: (path.count("/"), path))[MAX_MANIFESTS:])
        wanted = [path for path in wanted if path not in drop]
    if not wanted:
        return {}
    rows = connection.execute(
        """
        SELECT path, content
        FROM files
        WHERE repository_version_id = %s AND disposition = 'stored' AND path = ANY(%s)
        """,
        (version_id, wanted),
    ).fetchall()
    return {row["path"]: row["content"] or "" for row in rows}
