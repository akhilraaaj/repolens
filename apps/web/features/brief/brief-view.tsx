"use client";

import { DoorOpen, FolderTree, Layers, Network, Sparkles, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import type { Ingestion, Overview, StackItem } from "../../lib/api";
import { cn } from "../../lib/cn";
import type { OpenFile } from "../code/code-viewer";

const CATEGORY_LABELS: Record<string, string> = {
  framework: "Framework",
  language: "Language",
  ui: "UI",
  routing: "Routing",
  state: "State",
  data: "Data fetching",
  server: "Server",
  database: "Database",
  platform: "Platform",
  styling: "Styling",
  ai: "AI",
  validation: "Validation",
  build: "Build",
  testing: "Testing",
  tooling: "Tooling",
};

const LANGUAGE_COLORS = ["bg-brand", "bg-info", "bg-warn", "bg-fg/60", "bg-danger/80", "bg-muted-foreground", "bg-faint", "bg-line-strong"];

const ENTRY_LABELS: Record<string, string> = {
  package: "manifest",
  bin: "command",
  html: "html",
  script: "script",
  route: "route",
  convention: "convention",
};

type Props = {
  record: Ingestion;
  overview: Overview | null;
  error: string | null;
  onOpen: (file: OpenFile) => void;
  onShowMap: () => void;
};

export function BriefView({ record, overview, error, onOpen, onShowMap }: Props) {
  if (error) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }
  if (overview === null) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <Spinner /> Reading the repository
      </div>
    );
  }

  const { summary } = overview;
  const groups = groupStack(overview.stack);

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-4xl space-y-10 px-6 py-8">
        <header className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="font-mono">{record.commit_sha.slice(0, 7)}</Badge>
            <span>{summary.files.toLocaleString()} files</span>
            <span className="text-faint">·</span>
            <span>
              {summary.graph_files.toLocaleString()} parsed, {summary.graph_edges.toLocaleString()} file links
            </span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              {record.owner}/{record.name}
            </h1>
            {overview.description ? <p className="mt-1.5 max-w-2xl text-sm leading-6 text-muted-foreground">{overview.description}</p> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="lg" onClick={onShowMap}>
              <Network /> Open the architecture
            </Button>
          </div>
          {summary.languages.length > 0 ? <LanguageBar languages={summary.languages} /> : null}
        </header>

        {overview.notes.length > 0 ? (
          <ul className="space-y-1.5">
            {overview.notes.map((note) => (
              <li key={note} className="flex items-start gap-2 text-xs leading-5 text-warn">
                <TriangleAlert size={13} className="mt-0.5 shrink-0" /> {note}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
          <Section icon={<Layers size={14} />} title="Stack" hint="From dependencies and marker files">
            {groups.length === 0 ? (
              <p className="text-sm text-faint">No known packages or marker files.</p>
            ) : (
              <dl className="space-y-2.5">
                {groups.map(([category, items]) => (
                  <div key={category} className="grid grid-cols-[96px_minmax(0,1fr)] items-start gap-3">
                    <dt className="pt-0.5 text-xs text-faint">{CATEGORY_LABELS[category] ?? category}</dt>
                    <dd className="flex flex-wrap gap-1.5">
                      {items.map((item) => (
                        <button
                          key={item.name}
                          type="button"
                          title={`${item.package ?? item.name}${item.version ? ` ${item.version}` : ""} in ${item.evidence}`}
                          onClick={() => onOpen({ path: item.evidence })}
                          className={cn(
                            "inline-flex h-6 items-center gap-1.5 rounded-md border border-line bg-raised px-2 text-xs transition-colors hover:border-line-strong",
                            item.dev ? "text-muted-foreground" : "text-fg",
                          )}
                        >
                          {item.name}
                          {item.version ? <span className="font-mono text-[10px] text-faint">{item.version.replace(/^[\^~]/, "")}</span> : null}
                        </button>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </Section>

          <Section icon={<DoorOpen size={14} />} title="Entry points" hint="Where execution starts">
            {overview.entry_points.length === 0 ? (
              <p className="text-sm text-faint">None declared or conventionally named.</p>
            ) : (
              <ul className="-mx-2 space-y-0.5">
                {overview.entry_points.map((entry) => (
                  <li key={entry.path}>
                    <button
                      type="button"
                      onClick={() => onOpen({ path: entry.path })}
                      className="group flex w-full items-start gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-hover"
                    >
                      <Badge variant="outline" className="mt-0.5 shrink-0">{ENTRY_LABELS[entry.kind] ?? entry.kind}</Badge>
                      <span className="min-w-0">
                        <span className="block truncate font-mono text-xs text-fg">{entry.path}</span>
                        <span className="block text-xs leading-5 text-muted-foreground">{entry.reason}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>

        <Section icon={<Sparkles size={14} />} title="Core modules" hint="PageRank over the dependency graph: what the most code relies on">
          {overview.core_modules.length === 0 ? (
            <Empty className="border-0">
              <EmptyHeader>
                <EmptyTitle>No dependency graph to rank</EmptyTitle>
                <EmptyDescription>Core modules appear once JavaScript or TypeScript files import each other.</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <div className="overflow-hidden rounded-xl border border-line">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-line bg-panel text-faint">
                  <tr>
                    <th className="w-10 px-3 py-2 font-medium">#</th>
                    <th className="px-3 py-2 font-medium">File</th>
                    <th className="hidden w-40 px-3 py-2 font-medium sm:table-cell">Rank</th>
                    <th className="w-20 px-3 py-2 text-right font-medium">Used by</th>
                    <th className="w-16 px-3 py-2 text-right font-medium">Uses</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.core_modules.map((row) => (
                    <tr
                      key={row.path}
                      onClick={() =>
                        onOpen(row.symbol ? { path: row.path, start: row.symbol.start_line, end: row.symbol.end_line } : { path: row.path })
                      }
                      className="cursor-pointer border-b border-line last:border-0 hover:bg-hover"
                    >
                      <td className="px-3 py-2 font-mono text-faint">{row.position}</td>
                      <td className="max-w-0 px-3 py-2">
                        <span className="block truncate font-mono text-fg">{row.path}</span>
                        {row.symbol ? (
                          <span className="block truncate text-faint">
                            {row.symbol.entity_type} {row.symbol.name}
                          </span>
                        ) : null}
                      </td>
                      <td className="hidden px-3 py-2 sm:table-cell">
                        <span className="block h-1.5 overflow-hidden rounded-full bg-raised">
                          <span className="block h-full rounded-full bg-brand/70" style={{ width: `${Math.max(row.score * 100, 4)}%` }} />
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-fg">{row.used_by}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{row.uses}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <Section icon={<FolderTree size={14} />} title="Folders" hint="Role from the folder name or its contents">
          <div className="grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2">
            {overview.folders.map((folder) => (
              <div key={folder.path} className="bg-canvas p-3.5">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate font-mono text-xs text-fg">{folder.path}/</p>
                  <span className="shrink-0 text-[11px] text-faint">{folder.files} files</span>
                </div>
                <p className={cn("mt-1 text-xs", folder.role ? "text-muted-foreground" : "text-faint")}>
                  {folder.role ?? "No role inferred"}
                  {folder.basis === "contents" ? <span className="text-faint"> (by contents)</span> : null}
                </p>
                {folder.used_by + folder.depends_on > 0 ? (
                  <p className="mt-1.5 text-[11px] text-faint">
                    used by {folder.used_by} · depends on {folder.depends_on} links
                  </p>
                ) : null}
                {folder.key_files.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {folder.key_files.map((path) => (
                      <button
                        key={path}
                        type="button"
                        onClick={() => onOpen({ path })}
                        className="max-w-full truncate rounded border border-line px-1.5 py-px font-mono text-[10px] text-muted-foreground hover:border-line-strong hover:text-fg"
                      >
                        {path.split("/").pop()}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Section>

        <p className="border-t border-line pt-4 text-[11px] text-faint">
          Computed from manifests and the parsed dependency graph at this commit. No language model was used.
        </p>
      </div>
    </div>
  );
}

function Section({ icon, title, hint, children }: { icon: ReactNode; title: string; hint?: string; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex items-baseline gap-2">
        <span className="translate-y-0.5 text-muted-foreground">{icon}</span>
        <h2 className="text-sm font-medium">{title}</h2>
        {hint ? <span className="ml-auto min-w-0 truncate text-[11px] text-faint">{hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

function LanguageBar({ languages }: { languages: Overview["summary"]["languages"] }) {
  return (
    <div className="space-y-2">
      <div className="flex h-1.5 gap-px overflow-hidden rounded-full bg-raised">
        {languages.map((item, index) => (
          <span key={item.language} className={LANGUAGE_COLORS[index % LANGUAGE_COLORS.length]} style={{ width: `${item.share * 100}%` }} />
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        {languages.map((item, index) => (
          <li key={item.language} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2 w-2 rounded-full", LANGUAGE_COLORS[index % LANGUAGE_COLORS.length])} />
            {item.language}
            <span className="text-faint">{(item.share * 100).toFixed(item.share < 0.1 ? 1 : 0)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function groupStack(stack: StackItem[]): [string, StackItem[]][] {
  const groups = new Map<string, StackItem[]>();
  for (const item of stack) {
    const bucket = groups.get(item.category) ?? [];
    bucket.push(item);
    groups.set(item.category, bucket);
  }
  return [...groups.entries()];
}
