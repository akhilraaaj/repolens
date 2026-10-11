"use client";

import { Check, X } from "lucide-react";

import { Spinner } from "@/components/ui/spinner";
import { analysisDone, snapshotStored, type Ingestion } from "../../lib/api";
import { cn } from "../../lib/cn";

type StepState = "waiting" | "running" | "done" | "failed";

type Step = { title: string; state: StepState; detail: string };

export function steps(record: Ingestion): Step[] {
  const fetchState: StepState = record.status === "failed" ? "failed" : record.status === "running" ? "running" : "done";
  const parseState: StepState = !snapshotStored(record)
    ? "waiting"
    : record.analysis_status === "failed"
      ? "failed"
      : analysisDone(record)
        ? "done"
        : "running";
  const embedState: StepState =
    parseState !== "done"
      ? "waiting"
      : record.embedding_status === "failed"
        ? "failed"
        : record.embedding_status === "completed"
          ? "done"
          : "running";
  return [
    {
      title: "Fetch snapshot",
      state: fetchState,
      detail:
        fetchState === "failed"
          ? record.error_message ?? "The snapshot could not be stored."
          : fetchState === "running"
            ? `Downloading and filtering the tarball${record.phase ? ` (${record.phase})` : ""}`
            : `${record.stored_count.toLocaleString()} files stored, ${record.skipped_count.toLocaleString()} skipped`,
    },
    {
      title: "Parse and build the graph",
      state: parseState,
      detail:
        parseState === "failed"
          ? record.analysis_error_message ?? "Analysis failed."
          : parseState === "done"
            ? `${(record.symbol_count ?? 0).toLocaleString()} symbols, ${(record.relationship_count ?? 0).toLocaleString()} relationships`
            : "TypeScript compiler API reads symbols, imports, and calls",
    },
    {
      title: "Chunk and embed",
      state: embedState,
      detail:
        embedState === "failed"
          ? record.embedding_error ?? "Embeddings failed. Keyword search still works."
          : embedState === "done"
            ? `${(record.chunk_count ?? 0).toLocaleString()} searchable chunks`
            : "Syntax-aware chunks, full-text index, and local code embeddings",
    },
  ];
}

export function IndexingStepper({ record }: { record: Ingestion }) {
  return (
    <div className="mx-auto w-full max-w-md">
      <p className="text-sm font-medium">
        Preparing {record.owner}/{record.name}
      </p>
      <p className="mt-1 font-mono text-xs text-faint">{record.commit_sha.slice(0, 12)}</p>
      <ol className="mt-6 space-y-1">
        {steps(record).map((step, index) => (
          <li key={step.title} className="relative flex gap-3 pb-5 last:pb-0">
            {index < 2 ? <span aria-hidden className="absolute left-[11px] top-7 h-[calc(100%-24px)] w-px bg-line" /> : null}
            <StepIcon state={step.state} />
            <div className="min-w-0 pt-0.5">
              <p className={cn("text-sm", step.state === "waiting" ? "text-faint" : "text-fg")}>{step.title}</p>
              <p className={cn("mt-0.5 text-xs leading-5", step.state === "failed" ? "text-danger" : "text-muted-foreground")}>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StepIcon({ state }: { state: StepState }) {
  const base = "relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border";
  if (state === "done") {
    return (
      <span className={cn(base, "border-brand/30 bg-brand/10 text-brand")}>
        <Check size={13} strokeWidth={2.5} />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className={cn(base, "border-danger/30 bg-danger/10 text-danger")}>
        <X size={13} strokeWidth={2.5} />
      </span>
    );
  }
  if (state === "running") {
    return (
      <span className={cn(base, "border-line-strong bg-panel")}>
        <Spinner className="size-3" />
      </span>
    );
  }
  return <span className={cn(base, "border-line bg-panel")} />;
}
