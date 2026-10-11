"use client";

import { ArrowDownLeft, ArrowUpRight, Box, ChevronsDownUp, ChevronsUpDown, Code2, X } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { FileGraph } from "../../lib/api";
import type { OpenFile } from "../code/code-viewer";
import type { MapNodeData } from "./map-model";

export function MapInspector({
  node,
  graph,
  onClose,
  onOpen,
  onExpand,
  onCollapse,
  onReveal,
}: {
  node: MapNodeData;
  graph: FileGraph;
  onClose: () => void;
  onOpen: (file: OpenFile) => void;
  onExpand: (folder: string) => void;
  onCollapse: (folder: string) => void;
  onReveal: (path: string) => void;
}) {
  const links = useMemo(() => {
    if (node.kind !== "file" || !node.file) {
      return { out: [], in: [] };
    }
    const path = node.file.path;
    return {
      out: graph.edges.filter((edge) => edge.source === path),
      in: graph.edges.filter((edge) => edge.target === path),
    };
  }, [graph.edges, node]);

  const folderFiles = useMemo(() => {
    if (node.kind !== "folder") {
      return [];
    }
    return graph.files
      .filter((file) => file.path.startsWith(`${node.sublabel}/`))
      .sort((left, right) => right.symbol_count - left.symbol_count)
      .slice(0, 12);
  }, [graph.files, node]);

  return (
    <aside className="absolute bottom-3 right-3 top-14 flex w-80 flex-col overflow-hidden rounded-xl border border-line-strong bg-panel">
      <div className="flex items-start gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className={EYEBROW}>{node.kind}</p>
          <p className="mt-1 truncate font-mono text-[13px] text-fg">{node.kind === "folder" ? `${node.sublabel}/` : node.label}</p>
          {node.kind === "file" ? <p className="truncate font-mono text-[11px] text-faint">{node.sublabel}</p> : null}
        </div>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Close" onClick={onClose}>
          <X />
        </Button>
      </div>
      <div className="min-h-0 flex-1 space-y-5 overflow-auto px-4 py-4 text-sm">
        {node.kind === "folder" ? (
          <>
            <div className="flex gap-2">
              <Badge variant="outline">{node.fileCount} files</Badge>
              <Badge variant="outline">{node.symbolCount} symbols</Badge>
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => onExpand(node.sublabel)}>
                <ChevronsUpDown /> Expand
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => onCollapse(node.sublabel.split("/").slice(0, -1).join("/") || node.sublabel)}>
                <ChevronsDownUp /> Collapse parent
              </Button>
            </div>
            <div>
              <p className={EYEBROW}>Largest files</p>
              <ul className="mt-2 space-y-0.5">
                {folderFiles.map((file) => (
                  <li key={file.path}>
                    <button type="button" onClick={() => onReveal(file.path)} className={ROW}>
                      <span className="truncate">{file.path.slice(node.sublabel.length + 1)}</span>
                      <span className="ml-auto text-faint">{file.symbol_count}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </>
        ) : null}
        {node.kind === "file" && node.file ? (
          <>
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => onOpen({ path: node.file!.path })}>
                <Code2 /> Open code
              </Button>
            </div>
            <div>
              <p className={EYEBROW}>Declarations</p>
              {node.file.top_symbols.length === 0 ? <p className="mt-2 text-xs text-faint">No functions, classes, or exported values.</p> : null}
              <ul className="mt-2 space-y-0.5">
                {node.file.top_symbols.map((symbol) => (
                  <li key={`${symbol.name}-${symbol.start_line}`} className="group flex items-center">
                    <button
                      type="button"
                      onClick={() => onOpen({ path: node.file!.path, start: symbol.start_line, end: symbol.end_line })}
                      className={ROW}
                    >
                      <Box size={11} className={symbol.exported ? "text-brand" : "text-faint"} />
                      <span className="truncate">{symbol.name}</span>
                      <span className="ml-auto text-faint">{symbol.entity_type}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {node.file.symbol_count > node.file.top_symbols.length ? (
                <p className="mt-1 text-[11px] text-faint">and {node.file.symbol_count - node.file.top_symbols.length} more</p>
              ) : null}
            </div>
            <LinkList title="Depends on" icon={<ArrowUpRight size={11} className="text-info" />} items={links.out.map((edge) => ({ path: edge.target, kinds: edge.kinds, status: edge.status }))} onReveal={onReveal} />
            <LinkList title="Used by" icon={<ArrowDownLeft size={11} className="text-brand" />} items={links.in.map((edge) => ({ path: edge.source, kinds: edge.kinds, status: edge.status }))} onReveal={onReveal} />
          </>
        ) : null}
        {node.kind === "package" ? (
          <div>
            <p className="text-xs leading-5 text-muted-foreground">
              An external import. Its source is not in the snapshot, so these edges are labelled unresolved.
            </p>
            <p className={cnEyebrow("mt-4")}>Imported by</p>
            <ul className="mt-2 space-y-0.5">
              {(node.importers ?? []).slice(0, 30).map((path) => (
                <li key={path}>
                  <button type="button" onClick={() => onReveal(path)} className={ROW}>
                    <span className="truncate">{path}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function LinkList({
  title,
  icon,
  items,
  onReveal,
}: {
  title: string;
  icon: React.ReactNode;
  items: { path: string; kinds: Record<string, number>; status: string }[];
  onReveal: (path: string) => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <p className={EYEBROW}>
        {title} · {items.length}
      </p>
      <ul className="mt-2 space-y-0.5">
        {items.slice(0, 20).map((item) => (
          <li key={item.path}>
            <button type="button" onClick={() => onReveal(item.path)} className={ROW} title={`${item.status}: ${Object.entries(item.kinds).map(([kind, count]) => `${count} ${kind}`).join(", ")}`}>
              {icon}
              <span className="truncate">{item.path}</span>
              <span className="ml-auto shrink-0 text-faint">{Object.keys(item.kinds).join(" ")}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

const EYEBROW = "text-[11px] font-medium tracking-wider text-muted-foreground uppercase";

function cnEyebrow(extra: string) {
  return `${EYEBROW} ${extra}`;
}

const ROW = "flex w-full items-center gap-2 rounded px-1.5 py-1 text-left font-mono text-[11.5px] text-muted-foreground hover:bg-hover hover:text-fg";
