"""PageRank over the file dependency graph."""

from collections import defaultdict

DAMPING = 0.85
MAX_ITERATIONS = 100
TOLERANCE = 1e-10


def pagerank(nodes: list[str], edges: list[tuple[str, str, float]]) -> dict[str, float]:
    """Return a score per node; the scores sum to 1.

    An edge points from a dependent to its dependency, so rank flows toward the
    modules many others rely on. Edge weight is how many relationships the pair
    has. A node with no outgoing edges spreads its rank evenly over every node,
    which keeps the total stable instead of leaking.
    """

    if not nodes:
        return {}
    known = set(nodes)
    out_weight: dict[str, float] = defaultdict(float)
    incoming: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for source, target, weight in edges:
        if source in known and target in known and source != target and weight > 0:
            out_weight[source] += weight
            incoming[target].append((source, weight))
    count = len(nodes)
    rank = {node: 1.0 / count for node in nodes}
    for _ in range(MAX_ITERATIONS):
        dangling = sum(rank[node] for node in nodes if out_weight[node] == 0)
        base = (1.0 - DAMPING) / count + DAMPING * dangling / count
        following = {
            node: base + DAMPING * sum(rank[source] * weight / out_weight[source] for source, weight in incoming[node])
            for node in nodes
        }
        change = sum(abs(following[node] - rank[node]) for node in nodes)
        rank = following
        if change < TOLERANCE:
            break
    return rank
