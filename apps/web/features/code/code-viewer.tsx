"use client";

import { ArrowDownLeft, ArrowUpRight, FileCode2, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { api, type FileContent, type FileGraph } from "../../lib/api";

export type OpenFile = { path: string; start?: number; end?: number };

const HIGHLIGHT_LIMIT = 200_000;

export function CodeViewer({
  versionId,
  file,
  graph,
  onOpen,
  onClose,
}: {
  versionId: string;
  file: OpenFile | null;
  graph: FileGraph | null;
  onOpen: (file: OpenFile) => void;
  onClose?: () => void;
}) {
  const [loaded, setLoaded] = useState<{ key: string; content: FileContent | null; error: string | null }>({
    key: "",
    content: null,
    error: null,
  });
  const [html, setHtml] = useState<{ key: string; value: string } | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const path = file?.path ?? null;
  const rangeKey = `${path}:${file?.start ?? ""}-${file?.end ?? ""}`;

  useEffect(() => {
    if (path === null) {
      return;
    }
    let cancelled = false;
    api<FileContent>(`/ingestions/${versionId}/files?${new URLSearchParams({ path })}`)
      .then((content) => !cancelled && setLoaded({ key: path, content, error: null }))
      .catch((exc: Error) => !cancelled && setLoaded({ key: path, content: null, error: exc.message }));
    return () => {
      cancelled = true;
    };
  }, [versionId, path]);

  const content = loaded.key === path ? loaded.content : null;

  useEffect(() => {
    if (!content || content.content.length > HIGHLIGHT_LIMIT) {
      return;
    }
    let cancelled = false;
    const start = file?.start ?? 0;
    const end = file?.end ?? 0;
    void import("shiki").then(async ({ codeToHtml }) => {
      const value = await codeToHtml(content.content, {
        lang: languageFor(content.path),
        theme: "github-dark-default",
        transformers: [
          {
            line(node, line) {
              if (start > 0 && line >= start && line <= Math.max(start, end)) {
                this.addClassToHast(node, "cited");
              }
            },
          },
        ],
      }).catch(() => null);
      if (!cancelled && value) {
        setHtml({ key: rangeKey, value });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [content, file?.start, file?.end, rangeKey]);

  const rendered = html?.key === rangeKey ? html.value : null;

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    const target = container.querySelector(".line.cited");
    if (target instanceof HTMLElement) {
      target.scrollIntoView({ block: "center" });
    } else {
      container.scrollTop = 0;
    }
  }, [rendered, content]);

  const links = useMemo(() => (path ? fileLinks(graph, path) : { imports: [], importedBy: [] }), [graph, path]);

  if (file === null) {
    return (
      <Empty className="h-full border-0">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileCode2 />
          </EmptyMedia>
          <EmptyTitle>No file open</EmptyTitle>
          <EmptyDescription>Pick a node on the map, a citation in Ask, or a file from ⌘K.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5">
        <p className="min-w-0 truncate font-mono text-xs text-fg">{file.path}</p>
        {file.start ? (
          <Badge variant="brand">
            L{file.start}
            {file.end && file.end !== file.start ? `–${file.end}` : ""}
          </Badge>
        ) : null}
        {content?.truncated ? <Badge variant="warn">truncated</Badge> : null}
        {onClose ? (
          <button type="button" onClick={onClose} aria-label="Close source" className="ml-auto rounded p-1 text-muted-foreground hover:bg-hover hover:text-fg">
            <X size={14} />
          </button>
        ) : null}
      </div>
      {links.imports.length + links.importedBy.length > 0 ? (
        <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-b border-line px-4 py-2">
          {links.imports.slice(0, 8).map((target) => (
            <button
              key={`i-${target}`}
              type="button"
              onClick={() => onOpen({ path: target })}
              className="inline-flex items-center gap-1 rounded border border-line bg-panel px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-line-strong hover:text-fg"
              title="This file imports it"
            >
              <ArrowUpRight size={11} className="text-info" />
              {shortName(target)}
            </button>
          ))}
          {links.importedBy.slice(0, 8).map((source) => (
            <button
              key={`b-${source}`}
              type="button"
              onClick={() => onOpen({ path: source })}
              className="inline-flex items-center gap-1 rounded border border-line bg-panel px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground hover:border-line-strong hover:text-fg"
              title="It imports this file"
            >
              <ArrowDownLeft size={11} className="text-brand" />
              {shortName(source)}
            </button>
          ))}
        </div>
      ) : null}
      <div ref={scrollRef} className="code-view min-h-0 flex-1 overflow-auto">
        {loaded.key === path && loaded.error ? (
          <div className="p-4">
            <Alert variant="destructive">
              <AlertDescription>{loaded.error}</AlertDescription>
            </Alert>
          </div>
        ) : content === null ? (
          <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Spinner /> Loading source
          </div>
        ) : rendered ? (
          <div dangerouslySetInnerHTML={{ __html: rendered }} />
        ) : (
          <PlainCode text={content.content} start={file.start} end={file.end} />
        )}
      </div>
    </div>
  );
}

function PlainCode({ text, start, end }: { text: string; start?: number; end?: number }) {
  const lines = text.split("\n");
  return (
    <pre>
      <code>
        {lines.map((line, index) => {
          const number = index + 1;
          const cited = start !== undefined && number >= start && number <= Math.max(start, end ?? start);
          return (
            <span key={number} className={cited ? "line cited" : "line"}>
              {line}
              {"\n"}
            </span>
          );
        })}
      </code>
    </pre>
  );
}

function fileLinks(graph: FileGraph | null, path: string): { imports: string[]; importedBy: string[] } {
  const edges = graph?.edges ?? [];
  return {
    imports: edges.filter((edge) => edge.source === path).map((edge) => edge.target),
    importedBy: edges.filter((edge) => edge.target === path).map((edge) => edge.source),
  };
}

function shortName(path: string): string {
  return path.split("/").slice(-2).join("/");
}

const LANGUAGES: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  json: "json",
  md: "markdown",
  mdx: "mdx",
  py: "python",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  rb: "ruby",
  php: "php",
  css: "css",
  scss: "scss",
  html: "html",
  yml: "yaml",
  yaml: "yaml",
  toml: "toml",
  sh: "bash",
  sql: "sql",
  vue: "vue",
  svelte: "svelte",
  c: "c",
  h: "c",
  cpp: "cpp",
  cs: "csharp",
};

function languageFor(path: string): string {
  const name = path.split("/").at(-1)?.toLowerCase() ?? "";
  if (name === "dockerfile") {
    return "docker";
  }
  const extension = name.includes(".") ? name.split(".").at(-1) ?? "" : "";
  return LANGUAGES[extension] ?? "text";
}
