import { apiBaseUrl } from "./api-base";

export type FileRecord = {
  path: string;
  disposition: string;
  reason: string | null;
  size_bytes: number | null;
  parse_status?: string | null;
  parse_error?: string | null;
};

export type Ingestion = {
  id: string;
  status: string;
  analysis_status: string;
  phase: string | null;
  owner: string;
  name: string;
  canonical_url?: string;
  commit_sha: string;
  requested_ref: string;
  stored_count: number;
  skipped_count: number;
  failed_count: number;
  total_bytes: number;
  error_message: string | null;
  symbol_count?: number;
  relationship_count?: number;
  unresolved_count?: number;
  chunk_count?: number;
  progress_completed?: number;
  progress_total?: number | null;
  embedding_status?: string | null;
  embedding_error?: string | null;
  analysis_error_message?: string | null;
  files: FileRecord[];
};

export type SymbolRow = {
  id: string;
  name: string;
  qualified_name: string;
  entity_type: string;
  path: string;
  start_line: number;
  end_line: number;
  exported: boolean;
};

export type RelationshipRow = {
  relationship_type: string;
  resolution_status: string;
  evidence_file: string;
  evidence_start_line: number;
  evidence_end_line: number;
  source_qualified_name: string;
  target_qualified_name: string | null;
  specifier: string | null;
  target_name: string | null;
};

export type Graph = {
  symbols: SymbolRow[];
  relationships: RelationshipRow[];
  truncated: boolean;
};

export type MapSymbol = { name: string; entity_type: string; start_line: number; end_line: number; exported: boolean };

export type MapFile = { path: string; parse_status: string; symbol_count: number; top_symbols: MapSymbol[] };

export type MapEdge = { source: string; target: string; kinds: Record<string, number>; status: string; line: number };

export type FileGraph = {
  truncated: boolean;
  files: MapFile[];
  edges: MapEdge[];
  packages: { name: string; importers: string[] }[];
};

export type SearchHit = {
  path: string;
  start_line: number;
  end_line: number;
  chunk_type: string;
  snippet: string;
  methods: string[];
  distance?: number | null;
  rank?: number;
  keyword_rank?: number | null;
  vector_rank?: number | null;
  rrf_score?: number;
  score?: number | null;
};

export type StageHit = Omit<SearchHit, "snippet">;

export type PipelineStage = "keyword" | "vector" | "hybrid" | "reranked";

export type Pipeline = {
  query: string;
  embedding_model: string;
  reranker: string | null;
  rrf_k: number;
  stages: Record<PipelineStage, StageHit[] | null>;
  timings_ms: Partial<Record<"keyword" | "vector" | "fuse" | "rerank" | "generate", number>>;
  context?: { chunks: number; chars: number; approx_tokens: number };
  chat_model?: string | null;
  generator?: "abstain" | "extractive" | "model";
  cited?: number;
  abstained?: boolean;
};

export type ImpactItem = {
  id: string;
  name: string;
  qualified_name: string;
  entity_type: string;
  path: string;
  start_line: number;
  end_line: number;
  distance: number;
  relationship_type: string;
  resolution_status: string;
  via?: string | null;
};

export type Impact = {
  symbol: { id: string; name: string; path: string; qualified_name: string; start_line: number; end_line: number } | null;
  affected: ImpactItem[];
  related_tests: { path: string; name: string }[];
  uncertainties: string[];
};

export type FileContent = {
  path: string;
  start_line: number;
  end_line: number;
  content: string;
  truncated?: boolean;
};

export type StackItem = {
  name: string;
  category: string;
  package: string | null;
  version: string | null;
  evidence: string;
  dev: boolean;
};

export type EntryPoint = { path: string; kind: string; reason: string; evidence: string | null };

export type CoreModule = {
  path: string;
  position: number;
  score: number;
  used_by: number;
  uses: number;
  symbol: { name: string; entity_type: string; start_line: number; end_line: number } | null;
};

export type FolderRole = {
  path: string;
  role: string | null;
  basis: string | null;
  files: number;
  depends_on: number;
  used_by: number;
  key_files: string[];
};

export type Overview = {
  analysis_status: string;
  name: string | null;
  description: string | null;
  summary: {
    files: number;
    bytes: number;
    graph_files: number;
    graph_edges: number;
    languages: { language: string; files: number; bytes: number; share: number }[];
  };
  stack: StackItem[];
  entry_points: EntryPoint[];
  core_modules: CoreModule[];
  folders: FolderRole[];
  notes: string[];
};

export type Documentation = {
  title: string;
  model: string | null;
  sections: {
    id: string;
    heading: string;
    paragraphs: string[];
    sources: { path: string }[];
  }[];
};

export type ProviderSettings = {
  configured: boolean;
  provider: "ollama" | "openai_compatible" | "none" | null;
  base_url: string | null;
  model: string | null;
  has_api_key: boolean;
};

export type ModelConfig = {
  embedding_model: string;
  embedding_dimensions?: number;
  embedding_endpoint_configured: boolean;
  chat_configured: boolean;
  reranker_enabled?: boolean;
  reranker_model?: string | null;
};

export class ApiError extends Error {}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, init);
  } catch {
    throw new ApiError("The API is not reachable. Start it on port 8000 and try again.");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok && response.status !== 202) {
    throw new ApiError(messageFrom(body, response.status));
  }
  return body as T;
}

export function postJson<T>(path: string, payload: unknown): Promise<T> {
  return api<T>(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function messageFrom(body: unknown, status?: number): string {
  if (typeof body === "object" && body !== null && "message" in body && typeof body.message === "string") {
    return body.message;
  }
  return status ? `The API returned HTTP ${status}.` : "The API returned an unexpected response.";
}

export function snapshotStored(record: Ingestion): boolean {
  return record.status === "completed" || record.status === "completed_with_skips";
}

export function analysisDone(record: Ingestion): boolean {
  return record.analysis_status === "completed" || record.analysis_status === "completed_with_errors";
}
