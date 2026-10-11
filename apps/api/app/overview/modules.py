"""Core modules: files other files depend on, ordered by PageRank."""


def core_modules(
    files: list[dict],
    edges: list[dict],
    rank: dict[str, float],
    limit: int = 8,
) -> list[dict]:
    """Files ranked by PageRank that at least one other file depends on."""

    used_by: dict[str, set[str]] = {}
    uses: dict[str, set[str]] = {}
    for edge in edges:
        used_by.setdefault(edge["target"], set()).add(edge["source"])
        uses.setdefault(edge["source"], set()).add(edge["target"])
    by_path = {item["path"]: item for item in files}
    candidates = [path for path in rank if used_by.get(path)]
    candidates.sort(key=lambda path: (-rank[path], path))
    top = candidates[:limit]
    best = rank[top[0]] if top else 1.0
    rows = []
    for position, path in enumerate(top, start=1):
        rows.append(
            {
                "path": path,
                "position": position,
                "score": round(rank[path] / best, 4),
                "used_by": len(used_by.get(path, ())),
                "uses": len(uses.get(path, ())),
                "symbol": _focus_symbol(by_path.get(path)),
            }
        )
    return rows


def _focus_symbol(file: dict | None) -> dict | None:
    if not file:
        return None
    symbols = file.get("top_symbols") or []
    exported = [item for item in symbols if item.get("exported")]
    chosen = (exported or symbols or [None])[0]
    if chosen is None:
        return None
    return {"name": chosen["name"], "entity_type": chosen["entity_type"], "start_line": chosen["start_line"], "end_line": chosen["end_line"]}
