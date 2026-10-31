import pytest

from app.search.context import context_header, embed_input
from app.search.evaluate import load_dataset
from app.search.metrics import mean, recall_at_k, reciprocal_rank
from app.search.retrieve import identifier_terms, keyword_terms


def test_context_header_names_the_file_symbol_parent_and_imports() -> None:
    header = context_header(
        "src/ui/button.tsx",
        name="render",
        entity_type="method",
        qualified_name="Button.render",
        imports=["react", "./icon"],
    )

    assert header.splitlines() == [
        "File: src/ui/button.tsx",
        "Symbol: method Button.render",
        "Parent: Button",
        "Imports: react, ./icon",
    ]
    assert embed_input(header, "return null;").startswith("File: src/ui/button.tsx")
    assert embed_input(None, "return null;") == "return null;"


def test_recall_and_reciprocal_rank() -> None:
    expected = {"src/math.ts", "src/main.ts"}
    ranked = ["README.md", "src/main.ts", "src/math.ts"]

    assert recall_at_k(expected, ranked, 1) == 0.0
    assert recall_at_k(expected, ranked, 3) == 1.0
    assert reciprocal_rank(expected, ranked) == pytest.approx(0.5)
    assert reciprocal_rank(set(), ranked) == 0.0
    assert mean([1.0, 0.0]) == 0.5


def test_dataset_names_cannot_leave_the_datasets_directory() -> None:
    assert load_dataset("example")["questions"][0]["expected_paths"] == ["src/math.ts"]
    with pytest.raises(ValueError):
        load_dataset("../schema")
    with pytest.raises(ValueError):
        load_dataset("missing")


def test_keyword_terms_split_code_names_and_drop_question_filler() -> None:
    terms = keyword_terms("Where is dedupingInterval used to skip duplicate requests?")

    assert "dedupinginterval" in terms
    assert {"deduping", "interval", "skip", "duplicate", "requests"} <= set(terms)
    assert "used" not in terms
    assert keyword_terms("How does use_swr work?")[-1] == "swr"
    assert keyword_terms("?! --") == []


def test_identifier_terms_keep_names_written_like_code() -> None:
    assert identifier_terms("Where is dedupingInterval set, and what reads use_swr or URL?") == ["dedupingInterval", "use_swr"]
    assert identifier_terms("what does add return") == []
