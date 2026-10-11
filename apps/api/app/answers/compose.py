"""Write a direct answer from retrieved lines and the imports in those files.

The text may quote stored source and name an import specifier that appears in
that source. It does not paraphrase with a model and it does not execute code.
"""

import re

_STOPWORDS = {
    "a",
    "an",
    "the",
    "what",
    "which",
    "who",
    "how",
    "does",
    "do",
    "did",
    "is",
    "are",
    "was",
    "were",
    "for",
    "used",
    "use",
    "using",
    "this",
    "that",
    "these",
    "those",
    "with",
    "from",
    "into",
    "about",
    "where",
    "when",
    "why",
    "can",
    "could",
    "should",
    "would",
    "there",
    "here",
    "and",
    "or",
    "not",
    "any",
    "some",
    "in",
    "on",
    "of",
    "to",
    "it",
    "its",
    "be",
    "by",
    "at",
}
_IMPORT_FROM = re.compile(
    r"""^\s*import\s+(?:type\s+)?(.+?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*$"""
)
_IMPORT_SIDE = re.compile(r"""^\s*import\s+['"]([^'"]+)['"]\s*;?\s*$""")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RETURN = re.compile(r"\breturn\s+(.+?)\s*;?\s*$")
_FUNCTION = re.compile(r"\b(?:function|class)\s+([A-Za-z_][A-Za-z0-9_]*)")


def compose_answer(question: str, citations: list[dict], file_heads: dict[str, str]) -> str:
    """A few plain sentences. Every name in them appears in the stored files."""

    terms = _terms(question)
    relevant = _relevant_lines(citations, terms)
    identifiers = _identifiers(relevant)
    imports = _supporting_imports(citations, file_heads, terms, identifiers)
    packages = [item for item in imports if not item["specifier"].startswith(".")]
    return _spoken(terms, packages, relevant, citations)


def _terms(question: str) -> list[str]:
    found: list[str] = []
    for token in _IDENT.findall(question):
        lowered = token.lower()
        if len(lowered) < 3 or lowered in _STOPWORDS or lowered in found:
            continue
        found.append(lowered)
    return found[:8]


def _relevant_lines(citations: list[dict], terms: list[str]) -> list[dict]:
    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for citation in citations:
        snippet = citation.get("snippet")
        if not isinstance(snippet, str):
            continue
        start = int(citation["start_line"])
        for offset, raw in enumerate(snippet.splitlines()):
            line = raw.strip()
            if not _matches(line, terms):
                continue
            number = start + offset
            key = (citation["path"], number)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "path": citation["path"],
                    "line": number,
                    "text": _collapse(line),
                    "score": _score(line),
                }
            )
    rows.sort(key=lambda item: (-item["score"], item["path"], item["line"]))
    return rows[:8]


def _supporting_imports(
    citations: list[dict],
    file_heads: dict[str, str],
    terms: list[str],
    identifiers: set[str],
) -> list[dict]:
    found: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for citation in citations:
        head = file_heads.get(citation["path"])
        if not isinstance(head, str):
            continue
        for number, raw in enumerate(head.splitlines(), start=1):
            parsed = _parse_import(raw.strip())
            if parsed is None:
                continue
            specifier, names = parsed
            bound = [name for name in names if name in identifiers]
            if not bound and not _specifier_matches(specifier, terms):
                continue
            key = (citation["path"], number)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "path": citation["path"],
                    "line": number,
                    "text": _collapse(raw.strip()),
                    "specifier": specifier,
                    "names": bound or names[:3],
                }
            )
    return found


def _spoken(terms: list[str], packages: list[dict], relevant: list[dict], citations: list[dict]) -> str:
    if packages:
        return _package_sentence(packages)
    if "return" in terms:
        sentence = _return_sentence(relevant, citations, terms)
        if sentence:
            return sentence
    if relevant:
        line = relevant[0]
        return f"In {line['path']}, the line that matches your question is {line['text']}."
    sentences = _file_sentences(citations)
    if sentences:
        return " ".join(sentences)
    return "The retrieved files do not contain a line that states the answer."


def _package_sentence(packages: list[dict]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for item in packages:
        specifier = item["specifier"]
        if specifier in seen:
            continue
        seen.add(specifier)
        names = []
        for package in packages:
            if package["specifier"] != specifier:
                continue
            for name in package["names"]:
                if name not in names and not name.startswith("*"):
                    names.append(name)
        shown = ", ".join(names[:3])
        parts.append(f"{specifier}, through {shown}" if shown else specifier)
        if len(parts) == 3:
            break
    return "This commit uses " + " and ".join(parts) + "."


def _return_sentence(relevant: list[dict], citations: list[dict], terms: list[str]) -> str | None:
    returns = [line for line in relevant if _RETURN.search(line["text"])]
    named = [line for line in returns if (_function_name(line, citations) or "").lower() in terms]
    chosen = named[0] if named else (returns[0] if returns else None)
    if chosen is None:
        return None
    returned = _RETURN.search(chosen["text"])
    function = _function_name(chosen, citations)
    expr = returned.group(1).strip() if returned else ""
    if function:
        return f"{function} returns {expr}. That is in {chosen['path']}."
    return f"The retrieved source returns {expr}. That is in {chosen['path']}."


def _file_sentences(citations: list[dict]) -> list[str]:
    sentences: list[str] = []
    for citation in citations:
        snippet = citation.get("snippet")
        path = str(citation.get("path") or "")
        if not isinstance(snippet, str):
            continue
        base = path.rsplit("/", 1)[-1].lower()
        if base == "package.json":
            name = _json_field(snippet, "name")
            description = _json_field(snippet, "description")
            if name and description:
                sentences.append(f"This repository is named {name}. The package describes it as {description}.")
            elif name:
                sentences.append(f"This repository is named {name}.")
        elif base.startswith("readme"):
            prose = _readme_sentence(snippet)
            if prose:
                sentences.append(f"The README says {prose}")
        elif base.startswith("main.") or base == "index.html":
            sentences.append(f"The program starts in {path}.")
        elif base.startswith("app."):
            sentences.append(f"The screen is put together in {path}.")
        if len(sentences) == 4:
            break
    return sentences


def _json_field(snippet: str, field: str) -> str | None:
    matched = re.search(rf'"{field}"\s*:\s*"([^"]+)"', snippet)
    if matched is None:
        return None
    value = matched.group(1).strip()
    return value or None


def _readme_sentence(snippet: str) -> str | None:
    for raw in snippet.splitlines():
        text = _collapse(re.sub(r"^#+\s*", "", raw.strip()))
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        if len(text) < 24 or text[:1] in "-*`{[":
            continue
        if not text.endswith("."):
            text += "."
        lowered = text[0].lower() + text[1:]
        return lowered
    return None


def _function_name(line: dict, citations: list[dict]) -> str | None:
    for citation in citations:
        if citation["path"] != line["path"]:
            continue
        snippet = citation.get("snippet")
        if not isinstance(snippet, str):
            continue
        match = _FUNCTION.search(snippet)
        if match:
            return match.group(1)
    return None


def _identifiers(lines: list[dict]) -> set[str]:
    found: set[str] = set()
    for line in lines:
        found.update(_IDENT.findall(line["text"]))
    return found


def _parse_import(line: str) -> tuple[str, list[str]] | None:
    if line.startswith(("//", "#", "/*", "*")):
        return None
    matched = _IMPORT_FROM.match(line)
    if matched is None:
        side = _IMPORT_SIDE.match(line)
        if side is None:
            return None
        return side.group(1), []
    clause, specifier = matched.group(1), matched.group(2)
    names: list[str] = []
    brace = re.search(r"\{([^}]*)\}", clause)
    if brace:
        for part in brace.group(1).split(","):
            name = _binding(part)
            if name:
                names.append(name)
    remainder = re.sub(r"\{[^}]*\}", "", clause)
    for part in remainder.split(","):
        name = _binding(part)
        if name and name not in {"type"}:
            names.append(name)
    return specifier, names


def _binding(part: str) -> str | None:
    cleaned = part.strip()
    if cleaned == "":
        return None
    if " as " in cleaned:
        cleaned = cleaned.split(" as ")[-1].strip()
    if cleaned.startswith("* as "):
        cleaned = cleaned[5:].strip()
    token = cleaned.split()[-1]
    if _IDENT.fullmatch(token):
        return token
    return None


def _specifier_matches(specifier: str, terms: list[str]) -> bool:
    parts = [part.lower() for part in re.split(r"[^A-Za-z0-9]+", specifier) if part]
    return any(term in parts for term in terms)


def _matches(line: str, terms: list[str]) -> bool:
    if line == "" or len(line) > 200 or line.startswith(("//", "#", "/*", "*", "<!--")):
        return False
    lowered = line.lower()
    return any(term in lowered for term in terms)


def _score(line: str) -> int:
    score = 0
    if "(" in line:
        score += 5
    if "export " in line:
        score += 2
    if line.startswith("return ") or " return " in f" {line}":
        score += 3
    return score - len(line) // 40


def _collapse(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()
