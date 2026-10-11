"""Keep only claims that cite a numbered evidence item."""

import re

ABSTAIN = "I do not have source evidence for that question in this snapshot."
_CITE = re.compile(r"\[(\d+)\]")


def validate_answer(text: str, evidence_count: int) -> tuple[str, list[int], bool]:
    """Return the kept text, the citation numbers it uses, and whether it abstains.

    A paragraph with no valid [n] marker is dropped. Numbers outside the evidence
    list are removed. The whole answer abstains when nothing citable remains.
    """

    stripped = " ".join(text.split())
    if evidence_count < 1 or stripped == "" or ABSTAIN in text:
        return ABSTAIN, [], True
    kept: list[str] = []
    used: set[int] = set()
    for paragraph in re.split(r"\n\s*\n|\n", text.strip()):
        numbers = [int(match) for match in _CITE.findall(paragraph)]
        valid = [number for number in numbers if 1 <= number <= evidence_count]
        if not valid:
            continue
        cleaned = _CITE.sub(lambda match: match.group(0) if 1 <= int(match.group(1)) <= evidence_count else "", paragraph)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        if cleaned:
            kept.append(cleaned)
            used.update(valid)
    if not kept:
        return ABSTAIN, [], True
    return "\n\n".join(kept), sorted(used), False


def renumber(text: str, used: list[int]) -> str:
    """Rewrite [n] markers so they index the list of cited evidence, not the list offered."""

    positions = {number: index for index, number in enumerate(used, start=1)}
    return _CITE.sub(lambda match: f"[{positions[int(match.group(1))]}]" if int(match.group(1)) in positions else "", text)
