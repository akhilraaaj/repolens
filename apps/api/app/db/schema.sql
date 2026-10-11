CREATE TABLE IF NOT EXISTS repositories (
    id UUID PRIMARY KEY,
    host TEXT NOT NULL,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    default_branch TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (host, owner, name)
);

CREATE TABLE IF NOT EXISTS repository_versions (
    id UUID PRIMARY KEY,
    repository_id UUID NOT NULL REFERENCES repositories (id),
    commit_sha TEXT NOT NULL,
    requested_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    analysis_status TEXT NOT NULL DEFAULT 'not_started',
    phase TEXT,
    progress_completed INTEGER NOT NULL DEFAULT 0,
    progress_total INTEGER,
    stored_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    parser_name TEXT,
    parser_version TEXT,
    symbol_count INTEGER NOT NULL DEFAULT 0,
    relationship_count INTEGER NOT NULL DEFAULT 0,
    unresolved_count INTEGER NOT NULL DEFAULT 0,
    analysis_error_code TEXT,
    analysis_error_message TEXT,
    analysis_started_at TIMESTAMPTZ,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    embedding_status TEXT,
    embedding_error TEXT,
    UNIQUE (repository_id, commit_sha)
);

CREATE TABLE IF NOT EXISTS files (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    disposition TEXT NOT NULL,
    reason TEXT,
    size_bytes INTEGER,
    content_sha256 TEXT,
    content TEXT,
    parse_status TEXT,
    parse_error TEXT,
    UNIQUE (repository_version_id, path)
);

CREATE TABLE IF NOT EXISTS symbols (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files (id) ON DELETE CASCADE,
    local_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    exported BOOLEAN NOT NULL,
    UNIQUE (repository_version_id, local_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    source_symbol_id UUID NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    target_symbol_id UUID REFERENCES symbols (id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    evidence_file TEXT NOT NULL,
    evidence_start_line INTEGER NOT NULL,
    evidence_end_line INTEGER NOT NULL,
    specifier TEXT,
    target_name TEXT
);

CREATE INDEX IF NOT EXISTS symbols_version_idx ON symbols (repository_version_id);

CREATE INDEX IF NOT EXISTS relationships_version_idx ON relationships (repository_version_id);

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS parser_name TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS parser_version TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS symbol_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS relationship_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS unresolved_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS analysis_error_code TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS analysis_error_message TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS analysis_started_at TIMESTAMPTZ;

ALTER TABLE files ADD COLUMN IF NOT EXISTS parse_status TEXT;

ALTER TABLE files ADD COLUMN IF NOT EXISTS parse_error TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS embedding_status TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS embedding_error TEXT;

CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES files (id) ON DELETE CASCADE,
    symbol_id UUID REFERENCES symbols (id) ON DELETE SET NULL,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    chunk_type TEXT NOT NULL,
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);

CREATE INDEX IF NOT EXISTS code_chunks_version_idx ON code_chunks (repository_version_id);

CREATE INDEX IF NOT EXISTS code_chunks_tsv_idx ON code_chunks USING GIN (content_tsv);

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id UUID PRIMARY KEY REFERENCES code_chunks (id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding vector(768) NOT NULL
);

ALTER TABLE code_chunks ADD COLUMN IF NOT EXISTS header TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS embedding_model TEXT;

ALTER TABLE repository_versions ADD COLUMN IF NOT EXISTS documentation JSONB;

CREATE TABLE IF NOT EXISTS question_runs (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    abstained BOOLEAN NOT NULL,
    commit_sha TEXT NOT NULL,
    citations JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL,
    base_url TEXT,
    model TEXT,
    api_key TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_threads (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES chat_threads (id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY,
    repository_version_id UUID NOT NULL REFERENCES repository_versions (id) ON DELETE CASCADE,
    dataset_name TEXT NOT NULL,
    k INTEGER NOT NULL,
    results JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
