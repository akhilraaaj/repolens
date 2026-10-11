"""Run the TypeScript parser on stored source text."""

import json
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

ANALYZER_DIR = Path(__file__).resolve().parents[3] / "analyzer"
MAX_SYMBOLS = 20_000
MAX_RELATIONSHIPS = 50_000


class AnalyzerFailure(Exception):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class ParsedFile(BaseModel):
    path: str
    parse_status: str
    parse_error: str | None = None


class ParsedSymbol(BaseModel):
    local_id: str
    path: str
    entity_type: str
    name: str
    qualified_name: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    exported: bool


class ParsedRelationship(BaseModel):
    relationship_type: str
    resolution_status: str
    source_local_id: str
    target_local_id: str | None = None
    evidence_file: str
    evidence_start_line: int = Field(ge=1)
    evidence_end_line: int = Field(ge=1)
    specifier: str | None = None
    target_name: str | None = None


class ParseResult(BaseModel):
    parser_name: str
    parser_version: str
    files: list[ParsedFile]
    symbols: list[ParsedSymbol]
    relationships: list[ParsedRelationship]


def run_parser(
    files: list[dict[str, str]],
    timeout_seconds: float,
    config: dict[str, str] | None = None,
) -> ParseResult:
    """Parse source texts without reading or executing a repository checkout.

    config is the text of one tsconfig.json or jsconfig.json. The parser reads
    only its baseUrl and paths, so aliases such as "@/lib/x" can resolve.
    """

    if not (ANALYZER_DIR / "parse.mjs").is_file():
        raise AnalyzerFailure("analyzer_unavailable", "The TypeScript parser is not installed.")
    try:
        completed = subprocess.run(
            ["node", "parse.mjs"],
            input=json.dumps({"files": files, "config": config}).encode(),
            cwd=ANALYZER_DIR,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AnalyzerFailure("analyzer_unavailable", "Node.js is required to parse TypeScript.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AnalyzerFailure("analyzer_timeout", "Analysis exceeded the time limit.") from exc
    if completed.returncode != 0:
        raise AnalyzerFailure("analyzer_failed", "The parser stopped before producing a graph.")
    try:
        result = ParseResult.model_validate_json(completed.stdout)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AnalyzerFailure("analyzer_failed", "The parser returned a graph RepoLens could not read.") from exc
    if len(result.symbols) > MAX_SYMBOLS or len(result.relationships) > MAX_RELATIONSHIPS:
        raise AnalyzerFailure("limit_exceeded", "The graph is larger than the analysis limit.")
    return result
