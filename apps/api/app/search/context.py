"""Contextual headers prepended to a chunk before it is embedded.

The stored chunk stays the source text, so snippets and keyword search are
unchanged. The header is embedded with that text so the vector knows the file,
the symbol, and the imports around it.
"""


def context_header(
    path: str,
    *,
    name: str | None = None,
    entity_type: str | None = None,
    qualified_name: str | None = None,
    imports: list[str] | None = None,
) -> str:
    lines = [f"File: {path}"]
    if name and entity_type:
        signature = qualified_name or name
        lines.append(f"Symbol: {entity_type} {signature}")
    parent = _parent(qualified_name, name)
    if parent:
        lines.append(f"Parent: {parent}")
    if imports:
        lines.append("Imports: " + ", ".join(imports[:12]))
    return "\n".join(lines)


def embed_input(header: str | None, content: str) -> str:
    if header:
        return f"{header}\n\n{content}"
    return content


def _parent(qualified_name: str | None, name: str | None) -> str | None:
    if not qualified_name or "." not in qualified_name:
        return None
    parent = qualified_name.rsplit(".", 1)[0]
    if parent == name:
        return None
    return parent
