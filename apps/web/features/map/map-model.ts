import type { FileGraph, MapFile } from "../../lib/api";

export type MapNodeKind = "folder" | "file" | "package";

export type MapNodeData = {
  kind: MapNodeKind;
  id: string;
  label: string;
  sublabel: string;
  fileCount: number;
  symbolCount: number;
  file?: MapFile;
  importers?: string[];
};

export type MapEdgeData = {
  id: string;
  source: string;
  target: string;
  weight: number;
  status: string;
  kinds: Record<string, number>;
};

export type MapModel = {
  nodes: MapNodeData[];
  edges: MapEdgeData[];
  hidden: number;
};

export const MAX_NODES = 140;
const TARGET_NODES = 18;

export function folderChain(path: string): string[] {
  const parts = path.split("/");
  return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
}

/** The node a file is drawn inside: its first collapsed ancestor folder, or itself. */
export function visibleNodeFor(path: string, expanded: Set<string>): string {
  for (const folder of folderChain(path)) {
    if (!expanded.has(folder)) {
      return `folder:${folder}`;
    }
  }
  return `file:${path}`;
}

/** Expand the biggest folders first until the overview has a readable number of nodes. */
export function initialExpansion(paths: string[]): Set<string> {
  const expanded = new Set<string>();
  for (let guard = 0; guard < 64; guard += 1) {
    const counts = new Map<string, number>();
    for (const path of paths) {
      const id = visibleNodeFor(path, expanded);
      counts.set(id, (counts.get(id) ?? 0) + 1);
    }
    if (counts.size >= TARGET_NODES) {
      break;
    }
    const candidates = [...counts.entries()]
      .filter(([id]) => id.startsWith("folder:"))
      .sort((left, right) => right[1] - left[1]);
    const next = candidates.find(([id, count]) => counts.size - 1 + childCount(id.slice(7), paths, expanded) <= 40 || count === paths.length);
    if (!next) {
      break;
    }
    expanded.add(next[0].slice(7));
  }
  return expanded;
}

function childCount(folder: string, paths: string[], expanded: Set<string>): number {
  const next = new Set(expanded);
  next.add(folder);
  const children = new Set<string>();
  for (const path of paths) {
    if (path.startsWith(`${folder}/`)) {
      children.add(visibleNodeFor(path, next));
    }
  }
  return children.size;
}

export function buildModel(graph: FileGraph, expanded: Set<string>, showPackages: boolean): MapModel {
  const nodes = new Map<string, MapNodeData>();
  const owner = new Map<string, string>();
  for (const file of graph.files) {
    const id = visibleNodeFor(file.path, expanded);
    owner.set(file.path, id);
    const existing = nodes.get(id);
    if (existing) {
      existing.fileCount += 1;
      existing.symbolCount += file.symbol_count;
      continue;
    }
    if (id.startsWith("file:")) {
      const parts = file.path.split("/");
      nodes.set(id, {
        kind: "file",
        id,
        label: parts.at(-1) ?? file.path,
        sublabel: parts.slice(0, -1).join("/") || "(root)",
        fileCount: 1,
        symbolCount: file.symbol_count,
        file,
      });
    } else {
      const folder = id.slice(7);
      nodes.set(id, {
        kind: "folder",
        id,
        label: folder.split("/").at(-1) ?? folder,
        sublabel: folder,
        fileCount: 1,
        symbolCount: file.symbol_count,
      });
    }
  }

  const edges = new Map<string, MapEdgeData>();
  for (const edge of graph.edges) {
    const source = owner.get(edge.source);
    const target = owner.get(edge.target);
    if (!source || !target || source === target) {
      continue;
    }
    addEdge(edges, source, target, edge.status, edge.kinds);
  }

  if (showPackages) {
    for (const pkg of graph.packages.slice(0, 16)) {
      const id = `package:${pkg.name}`;
      nodes.set(id, {
        kind: "package",
        id,
        label: pkg.name,
        sublabel: `${pkg.importers.length} importing file${pkg.importers.length === 1 ? "" : "s"}`,
        fileCount: 0,
        symbolCount: 0,
        importers: pkg.importers,
      });
      for (const importer of pkg.importers) {
        const source = owner.get(importer);
        if (source) {
          addEdge(edges, source, id, "unresolved", { imports: 1 });
        }
      }
    }
  }

  const ordered = [...nodes.values()];
  const kept = ordered.slice(0, MAX_NODES);
  const keptIds = new Set(kept.map((node) => node.id));
  return {
    nodes: kept,
    edges: [...edges.values()].filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target)),
    hidden: ordered.length - kept.length,
  };
}

function addEdge(edges: Map<string, MapEdgeData>, source: string, target: string, status: string, kinds: Record<string, number>) {
  const id = `${source}->${target}`;
  const current = edges.get(id);
  const total = Object.values(kinds).reduce((sum, value) => sum + value, 0);
  if (current) {
    current.weight += total;
    if (status === "verified" || (status === "resolved" && current.status === "unresolved")) {
      current.status = status;
    }
    for (const [kind, count] of Object.entries(kinds)) {
      current.kinds[kind] = (current.kinds[kind] ?? 0) + count;
    }
    return;
  }
  edges.set(id, { id, source, target, weight: total, status, kinds: { ...kinds } });
}

export function nodeSize(kind: MapNodeKind): { width: number; height: number } {
  if (kind === "folder") {
    return { width: 210, height: 64 };
  }
  if (kind === "package") {
    return { width: 170, height: 44 };
  }
  return { width: 220, height: 72 };
}

/** Neighbors of a node in the drawn graph, used for focus mode. */
export function neighborhood(model: MapModel, id: string): Set<string> {
  const ids = new Set([id]);
  for (const edge of model.edges) {
    if (edge.source === id) {
      ids.add(edge.target);
    }
    if (edge.target === id) {
      ids.add(edge.source);
    }
  }
  return ids;
}
