"""Run a checked-in question set and store Recall@k and MRR for each strategy."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from app.search.metrics import mean, recall_at_k, reciprocal_rank
from app.search.rerank import rerank_enabled
from app.search.retrieve import compare_strategies

REPO_ROOT = Path(__file__).resolve().parents[4]
DATASETS = REPO_ROOT / "evaluation" / "datasets"
RESULTS = REPO_ROOT / "evaluation" / "results"
STRATEGIES = ("keyword", "vector", "hybrid", "reranked")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")
GOLDEN_SET = "lab-golden-set"


def load_dataset(name: str) -> dict:
    if NAME.fullmatch(name) is None:
        raise ValueError("Unknown dataset.")
    path = DATASETS / f"{name}.json"
    if not path.is_file() or not path.resolve().is_relative_to(DATASETS.resolve()):
        raise ValueError("Unknown dataset.")
    payload = json.loads(path.read_text())
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("The dataset has no questions.")
    for item in questions:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str) or not isinstance(item.get("expected_paths"), list):
            raise ValueError("A dataset question needs a question and expected_paths.")
    payload["name"] = name
    return payload


def golden_set(questions: list[dict]) -> dict:
    """A question set built in the RAG Lab for one snapshot. It is stored with the run, not as a file."""

    return {
        "name": GOLDEN_SET,
        "questions": [
            {"id": f"q{index}", "question": item["question"], "expected_paths": item["expected_paths"]}
            for index, item in enumerate(questions, start=1)
        ],
    }


def list_datasets() -> list[str]:
    if not DATASETS.is_dir():
        return []
    return sorted(path.stem for path in DATASETS.glob("*.json") if NAME.fullmatch(path.stem))


def evaluate_dataset(connection: psycopg.Connection, version_id: UUID, dataset: dict, *, k: int = 5) -> dict:
    buckets: dict[str, dict[str, list[float]]] = {name: {"recall": [], "mrr": []} for name in STRATEGIES}
    questions = []
    for item in dataset["questions"]:
        compared = compare_strategies(connection, version_id, item["question"], max(k, 8))
        expected = set(item["expected_paths"])
        scored = {}
        for name in STRATEGIES:
            hits = compared[name]
            if hits is None:
                scored[name] = None
                continue
            paths = [hit["path"] for hit in hits]
            recall = recall_at_k(expected, paths, k)
            rank = reciprocal_rank(expected, paths)
            buckets[name]["recall"].append(recall)
            buckets[name]["mrr"].append(rank)
            scored[name] = {"recall_at_k": round(recall, 4), "reciprocal_rank": round(rank, 4), "paths": paths[:k]}
        questions.append({"id": item.get("id"), "question": item["question"], "expected_paths": item["expected_paths"], "strategies": scored})
    summary = {}
    for name, bucket in buckets.items():
        if not bucket["recall"]:
            continue
        summary[name] = {"recall_at_k": round(mean(bucket["recall"]), 4), "mrr": round(mean(bucket["mrr"]), 4)}
    return {
        "dataset": dataset["name"],
        "k": k,
        "reranker": rerank_enabled(),
        "summary": summary,
        "questions": questions,
    }


def store_evaluation(connection: psycopg.Connection, version_id: UUID, report: dict) -> str:
    run_id = uuid4()
    connection.execute(
        """
        INSERT INTO evaluation_runs (id, repository_version_id, dataset_name, k, results, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (run_id, version_id, report["dataset"], report["k"], json.dumps(report), datetime.now(timezone.utc)),
    )
    connection.commit()
    if report["dataset"] == GOLDEN_SET:
        return str(run_id)
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RESULTS / f"{report['dataset']}-{stamp}.json").write_text(json.dumps(report, indent=2))
    return str(run_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score retrieval strategies against a dataset.")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--ingestion", required=True)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    from app.db.connection import connect

    dataset = load_dataset(args.dataset)
    connection = connect()
    try:
        report = evaluate_dataset(connection, UUID(args.ingestion), dataset, k=args.k)
        run_id = store_evaluation(connection, UUID(args.ingestion), report)
    finally:
        connection.close()
    print(json.dumps({"id": run_id, "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
