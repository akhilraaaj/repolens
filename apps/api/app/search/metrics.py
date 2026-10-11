"""Retrieval metrics. A hit counts when its path is one of the expected files."""


def recall_at_k(expected: set[str], ranked_paths: list[str], k: int) -> float:
    if not expected or k < 1:
        return 0.0
    found = set(ranked_paths[:k]) & expected
    return len(found) / len(expected)


def reciprocal_rank(expected: set[str], ranked_paths: list[str]) -> float:
    for index, path in enumerate(ranked_paths, start=1):
        if path in expected:
            return 1.0 / index
    return 0.0


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
