"use client";

import { Binary, Blend, ChevronRight, FileText, ListOrdered, MessageSquareText, TextSearch, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import type { Pipeline, StageHit } from "../../lib/api";
import { cn } from "../../lib/cn";
import type { OpenFile } from "../code/code-viewer";

type StageId = "keyword" | "vector" | "fuse" | "rerank" | "prompt" | "answer";

type Citation = { path: string; start_line: number; end_line: number };

const GENERATOR_LABELS: Record<NonNullable<Pipeline["generator"]>, string> = {
  model: "LLM, grounded",
  extractive: "Extractive, no LLM",
  abstain: "Abstained",
};

export function PipelineInspector({
  pipeline,
  citations,
  pending,
  onOpen,
}: {
  pipeline: Pipeline;
  citations: Citation[];
  pending: boolean;
  onOpen: (file: OpenFile) => void;
}) {
  const [selected, setSelected] = useState<StageId>("fuse");
  const { stages, timings_ms: timings } = pipeline;
  const keyword = stages.keyword ?? [];
  const vector = stages.vector ?? [];
  const hybrid = stages.hybrid ?? [];
  const reranked = stages.reranked;

  const cards: { id: StageId; title: string; icon: LucideIcon; metric: string; ms?: number; off?: boolean; live?: boolean }[] = [
    { id: "keyword", title: "Keyword", icon: TextSearch, metric: `${keyword.length} hits`, ms: timings.keyword },
    { id: "vector", title: "Vector", icon: Binary, metric: `${vector.length} hits`, ms: timings.vector },
    { id: "fuse", title: "RRF fusion", icon: Blend, metric: `${hybrid.length} ranked`, ms: timings.fuse },
    { id: "rerank", title: "Rerank", icon: ListOrdered, metric: reranked ? `${reranked.length} rescored` : "off", ms: timings.rerank, off: !reranked },
    {
      id: "prompt",
      title: "Context",
      icon: FileText,
      metric: pipeline.context ? `${pipeline.context.chunks} chunks · ~${pipeline.context.approx_tokens} tok` : "…",
    },
    {
      id: "answer",
      title: "Answer",
      icon: MessageSquareText,
      metric: pending ? "writing" : pipeline.generator ? GENERATOR_LABELS[pipeline.generator] : "…",
      ms: timings.generate,
      live: pending,
    },
  ];

  return (
    <div className="rounded-xl border border-line bg-canvas/70 p-3">
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="font-medium text-fg">How this answer was built</span>
        <span className="text-faint">·</span>
        <span className="truncate font-mono">{pipeline.embedding_model}</span>
        {pipeline.chat_model ? (
          <>
            <span className="text-faint">·</span>
            <span className="truncate">{pipeline.chat_model}</span>
          </>
        ) : null}
      </div>
      <ol className="mt-3 flex flex-wrap items-stretch gap-1 pb-1">
        {cards.map((card, index) => (
          <li
            key={card.id}
            style={{ animationDelay: `${index * 60}ms` }}
            className="flex shrink-0 animate-in items-stretch gap-1 fade-in slide-in-from-bottom-1 fill-mode-both duration-300"
          >
            {index > 0 ? <ChevronRight size={12} className={cn("shrink-0 self-center text-faint", index === 2 && "text-brand/70")} /> : null}
            <button
              type="button"
              onClick={() => setSelected(card.id)}
              aria-pressed={selected === card.id}
              className={cn(
                "flex min-w-[104px] flex-col items-start rounded-lg border px-2.5 py-2 text-left transition-colors",
                selected === card.id ? "border-brand/40 bg-brand/10" : "border-line bg-panel hover:border-line-strong",
                card.off && "opacity-60",
              )}
            >
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-fg">
                {card.live ? <Spinner className="size-3" /> : <card.icon size={12} className="text-brand" />}
                {card.title}
              </span>
              <span className="mt-0.5 text-[10px] text-muted-foreground">{card.metric}</span>
              <span className="font-mono text-[10px] text-faint">{card.ms !== undefined ? formatMs(card.ms) : "\u00a0"}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="mt-2">
        {selected === "keyword" ? (
          <StageTable
            note="PostgreSQL full-text search: websearch_to_tsquery over a tsvector column, ordered by ts_rank, plus path and substring matches. Finds exact identifiers."
            hits={keyword}
            columns={["rank"]}
            onOpen={onOpen}
          />
        ) : null}
        {selected === "vector" ? (
          <StageTable
            note="The question is embedded with the same model as the chunks, then pgvector orders chunks by cosine distance (<=>) on an HNSW index. Lower is closer. Finds paraphrases."
            hits={vector}
            columns={["rank", "distance"]}
            onOpen={onOpen}
          />
        ) : null}
        {selected === "fuse" ? (
          <StageTable
            note={`Reciprocal rank fusion: score = Σ 1 / (${pipeline.rrf_k} + rank) over the keyword and vector lists. It only uses positions, so ts_rank and cosine distance never have to share a scale.`}
            hits={hybrid}
            columns={["rank", "keyword_rank", "vector_rank", "rrf_score"]}
            onOpen={onOpen}
          />
        ) : null}
        {selected === "rerank" ? (
          reranked ? (
            <StageTable
              note={`A cross-encoder (${pipeline.reranker}) reads the question and each fused chunk together and rescores the top 20.`}
              hits={reranked}
              columns={["rank", "rrf_score", "score"]}
              onOpen={onOpen}
            />
          ) : (
            <p className="text-xs leading-5 text-muted-foreground">
              The reranker is off, so the fused order is used directly. Set <code className="font-mono">REPOLENS_RERANKER=1</code> on the API to add a cross-encoder pass.
            </p>
          )
        ) : null}
        {selected === "prompt" ? (
          <div className="space-y-2 text-xs leading-5 text-muted-foreground">
            <p>
              The top chunks are numbered <span className="font-mono text-fg">[1]</span>, <span className="font-mono text-fg">[2]</span>… and sent as evidence, capped at
              1,200 characters each. Source comments and READMEs go in as data, not instructions.
            </p>
            {pipeline.context ? (
              <p className="font-mono text-[11px]">
                {pipeline.context.chunks} chunks · {pipeline.context.chars.toLocaleString()} chars · ~{pipeline.context.approx_tokens.toLocaleString()} tokens (chars ÷ 4,
                an estimate)
              </p>
            ) : null}
          </div>
        ) : null}
        {selected === "answer" ? (
          <div className="space-y-2 text-xs leading-5 text-muted-foreground">
            <p>{answerNote(pipeline, pending)}</p>
            {!pending && pipeline.cited !== undefined ? (
              <p className="font-mono text-[11px]">
                {pipeline.cited} of {pipeline.context?.chunks ?? 0} evidence chunks cited
              </p>
            ) : null}
            <div className="flex flex-wrap gap-1.5">
              {citations.map((citation, index) => (
                <button
                  key={`${citation.path}-${citation.start_line}`}
                  type="button"
                  onClick={() => onOpen({ path: citation.path, start: citation.start_line, end: citation.end_line })}
                  className="rounded border border-line bg-panel px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-brand/40 hover:text-fg"
                >
                  <span className="text-brand">{index + 1}</span> {citation.path}:{citation.start_line}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <p className="mt-3 text-[10px] text-faint">Timings include model loading on the first question after the API starts.</p>
    </div>
  );
}

type Column = "rank" | "distance" | "keyword_rank" | "vector_rank" | "rrf_score" | "score";

const COLUMN_LABELS: Record<Column, string> = {
  rank: "#",
  distance: "cosine",
  keyword_rank: "kw #",
  vector_rank: "vec #",
  rrf_score: "RRF",
  score: "rerank",
};

function StageTable({ note, hits, columns, onOpen }: { note: string; hits: StageHit[]; columns: Column[]; onOpen: (file: OpenFile) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-xs leading-5 text-muted-foreground">{note}</p>
      {hits.length === 0 ? (
        <p className="text-xs text-faint">No hits in this stage.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-left text-[11px]">
            <thead className="bg-panel text-faint">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="px-2 py-1 font-normal">
                    {COLUMN_LABELS[column]}
                  </th>
                ))}
                <th className="px-2 py-1 font-normal">chunk</th>
                <th className="px-2 py-1 font-normal">found by</th>
              </tr>
            </thead>
            <tbody>
              {hits.map((hit) => (
                <tr key={`${hit.path}-${hit.start_line}-${hit.end_line}`} className="border-t border-line">
                  {columns.map((column) => (
                    <td key={column} className="px-2 py-1 font-mono text-muted-foreground tabular-nums">
                      {formatCell(hit[column])}
                    </td>
                  ))}
                  <td className="px-2 py-1">
                    {/* A table cell does not enforce max-width, so the button carries it. */}
                    <button
                      type="button"
                      onClick={() => onOpen({ path: hit.path, start: hit.start_line, end: hit.end_line })}
                      className="flex max-w-[260px] min-w-0 font-mono text-fg hover:text-brand"
                      title={`${hit.path}:${hit.start_line}-${hit.end_line}`}
                    >
                      <span className="truncate">{hit.path}</span>
                      <span className="shrink-0">
                        :{hit.start_line}-{hit.end_line}
                      </span>
                    </button>
                  </td>
                  <td className="px-2 py-1">
                    <span className="flex shrink-0 gap-1">
                      {hit.methods.map((method) => (
                        <Badge key={method} variant={method === "vector" ? "info" : method === "reranked" ? "warn" : "brand"} className="h-4 px-1.5 text-[9px]">
                          {method}
                        </Badge>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function answerNote(pipeline: Pipeline, pending: boolean): string {
  if (pending) {
    return "Writing the answer from the numbered evidence.";
  }
  if (pipeline.generator === "abstain") {
    return "No retrieved chunk resolved to a stored file and line range, so RepoLens said the evidence was insufficient instead of guessing.";
  }
  if (pipeline.generator === "extractive") {
    return "No chat model is configured, so the answer is assembled from the cited source directly. Retrieval is identical either way.";
  }
  return "The model wrote the answer from the evidence and had to cite it as [n]. Citations to evidence that was not offered are dropped. If no valid citation remains, RepoLens quotes the source directly.";
}

function formatCell(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "–";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(value < 0.1 ? 4 : 3);
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`;
}
