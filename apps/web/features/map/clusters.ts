import type { FileGraph, MapFile } from "../../lib/api";
import { colorsByCluster } from "./colors";

/** Golden angle. Successive dots turn by this much, so they fill a disc instead of lining up. */
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

/** At most this many folders on screen. Smaller folders fold into their parent until it fits. */
const MAX_CLUSTERS = 16;
/** A folder with fewer files than this joins its parent. */
const MIN_FILES = 3;

const DOT = 5;
const SPACING = 6.2;
/** Room between blobs for the folder title above and the file label beside. */
const GAP = 36;
/** Width of one 12.5px mono character in the folder title. */
const TITLE_CHAR = 7.6;

export type Dot = {
  path: string;
  x: number;
  y: number;
  r: number;
  /** "main" for the folder's most common extension, "other" for the rest. */
  tone: "main" | "light" | "dark" | "other";
};

export type Cluster = {
  key: string;
  label: string;
  color: string;
  files: MapFile[];
  symbolCount: number;
  /** Center in flow coordinates. */
  x: number;
  y: number;
  radius: number;
  /** Half the width and half the height of the blob with its title and caption. Layout keeps these boxes apart. */
  halfWidth: number;
  halfHeight: number;
  /** Dot positions relative to the center. */
  dots: Dot[];
  /** The file the rest of the code imports most, shown beside the blob. */
  hub: string | null;
};

export type ClusterLink = {
  id: string;
  source: string;
  target: string;
  weight: number;
};

export type ClusterMap = {
  clusters: Cluster[];
  links: ClusterLink[];
  clusterOf: Map<string, string>;
};

export function buildClusters(graph: FileGraph): ClusterMap {
  const paths = graph.files.map((file) => file.path);
  const keyOf = groupPaths(paths);
  const indegree = new Map<string, number>();
  for (const edge of graph.edges) {
    if (edge.source !== edge.target) {
      indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1);
    }
  }

  const members = new Map<string, MapFile[]>();
  for (const file of graph.files) {
    const key = keyOf.get(file.path) ?? ROOT;
    const list = members.get(key) ?? [];
    list.push(file);
    members.set(key, list);
  }
  const keys = [...members.keys()].sort();
  const palette = colorsByCluster(keys);

  const clusters: Cluster[] = keys.map((key) => {
    const files = (members.get(key) ?? []).slice().sort((left, right) => {
      const byDegree = (indegree.get(right.path) ?? 0) - (indegree.get(left.path) ?? 0);
      return byDegree !== 0 ? byDegree : left.path.localeCompare(right.path);
    });
    const main = commonExtension(files);
    const dots = files.map((file, index): Dot => {
      const distance = SPACING * Math.sqrt(index + 0.5);
      const theta = index * GOLDEN;
      return {
        path: file.path,
        x: round(Math.cos(theta) * distance),
        y: round(Math.sin(theta) * distance),
        r: DOT + Math.min(indegree.get(file.path) ?? 0, 8) * 0.22,
        tone: extension(file.path) !== main ? "other" : TONES[hash(file.path) % TONES.length],
      };
    });
    const top = files[0];
    const radius = SPACING * Math.sqrt(files.length) + DOT + 4;
    const title = (shortName(key).length + String(files.length).length + 2) * TITLE_CHAR + 28;
    return {
      key,
      label: key,
      color: palette.get(key) ?? "#38bdf8",
      files,
      symbolCount: files.reduce((sum, file) => sum + file.symbol_count, 0),
      x: 0,
      y: 0,
      radius,
      halfWidth: Math.max(radius + 40, title / 2),
      // The title sits above the blob and the caption below its right edge.
      halfHeight: radius + 30,
      dots,
      hub: top && (indegree.get(top.path) ?? 0) > 0 ? top.path : null,
    };
  });

  const weights = new Map<string, ClusterLink>();
  for (const edge of graph.edges) {
    const source = keyOf.get(edge.source);
    const target = keyOf.get(edge.target);
    if (!source || !target || source === target) {
      continue;
    }
    // One band per pair. The width is what matters, not the direction.
    const [left, right] = source < target ? [source, target] : [target, source];
    const id = `${left}~${right}`;
    const current = weights.get(id);
    if (current) {
      current.weight += 1;
    } else {
      weights.set(id, { id, source: left, target: right, weight: 1 });
    }
  }
  const links = [...weights.values()];
  place(clusters, links);
  return { clusters, links, clusterOf: keyOf };
}

const ROOT = "(root)";
const TONES: Dot["tone"][] = ["main", "main", "light", "dark"];

/**
 * Start with each file's own folder. Fold the smallest folders into their parent
 * until there are few enough to read, so 30 tiny example folders become one.
 */
export function groupPaths(paths: string[]): Map<string, string> {
  const keyOf = new Map(paths.map((path) => [path, parentOf(path)]));
  for (let guard = 0; guard < 400; guard += 1) {
    const counts = new Map<string, number>();
    for (const key of keyOf.values()) {
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const foldable = [...counts.entries()].filter(([key]) => key !== ROOT);
    const tiny = foldable.filter(([, count]) => count < MIN_FILES);
    // Past the limit, fold only nested folders. Folding a top-level folder would
    // pour it into the root and leave one huge blob.
    const nested = foldable.filter(([key]) => depth(key) >= 2);
    const pool = tiny.length > 0 ? tiny : counts.size > MAX_CLUSTERS ? nested : [];
    if (pool.length === 0) {
      break;
    }
    // Fold the deepest, then smallest, folder first, so siblings meet in their parent.
    pool.sort((left, right) => depth(right[0]) - depth(left[0]) || left[1] - right[1] || left[0].localeCompare(right[0]));
    const [victim] = pool[0] ?? [];
    if (victim === undefined) {
      break;
    }
    const parent = parentOf(victim);
    for (const [path, key] of keyOf) {
      if (key === victim) {
        keyOf.set(path, parent);
      }
    }
  }
  return keyOf;
}

/** Two segments are enough to tell "ui/zoom" from "server/zoom". */
export function shortName(key: string): string {
  return key.split("/").slice(-2).join("/");
}

function parentOf(path: string): string {
  const index = path.lastIndexOf("/");
  return index <= 0 ? ROOT : path.slice(0, index);
}

function depth(key: string): number {
  return key === ROOT ? 0 : key.split("/").length;
}

/**
 * A small force layout: linked folders pull together, every folder pushes the
 * others away, and a weak pull keeps the whole thing centered. It starts from a
 * ring and uses no randomness, so the same commit always draws the same map.
 */
function place(clusters: Cluster[], links: ClusterLink[]): void {
  const count = clusters.length;
  if (count === 0) {
    return;
  }
  const index = new Map(clusters.map((cluster, position) => [cluster.key, position]));
  const ring = clusters.reduce((sum, cluster) => sum + cluster.halfHeight * 2 + GAP, 0) / (Math.PI * 2);
  clusters.forEach((cluster, position) => {
    const angle = -Math.PI / 2 + (position / count) * Math.PI * 2;
    cluster.x = count === 1 ? 0 : Math.cos(angle) * ring;
    cluster.y = count === 1 ? 0 : Math.sin(angle) * ring;
  });

  for (let step = 0; step < 360; step += 1) {
    const heat = 1 - step / 360;
    for (const link of links) {
      const a = clusters[index.get(link.source) ?? -1];
      const b = clusters[index.get(link.target) ?? -1];
      if (!a || !b) {
        continue;
      }
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.hypot(dx, dy) || 1;
      const rest = a.halfHeight + b.halfHeight + GAP * 2;
      const pull = ((distance - rest) / distance) * 0.03 * Math.min(1 + Math.log2(link.weight), 4) * heat;
      a.x += dx * pull;
      a.y += dy * pull;
      b.x -= dx * pull;
      b.y -= dy * pull;
    }
    for (let i = 0; i < count; i += 1) {
      const a = clusters[i]!;
      for (let j = i + 1; j < count; j += 1) {
        const b = clusters[j]!;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 0.01) {
          dx = j - i;
          dy = i - j;
          distance = Math.hypot(dx, dy);
        }
        if (separate(a, b)) {
          continue;
        }
        const push = (160 * heat) / distance;
        const ux = (dx / distance) * push;
        const uy = (dy / distance) * push;
        a.x -= ux;
        a.y -= uy;
        b.x += ux;
        b.y += uy;
      }
    }
    // Pull harder vertically, so the map comes out wide like the screen.
    for (const cluster of clusters) {
      cluster.x -= cluster.x * 0.02;
      cluster.y -= cluster.y * 0.05;
    }
  }
  // A last pass with no heat: nothing may overlap once the pulls stop.
  for (let pass = 0; pass < 40; pass += 1) {
    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        const a = clusters[i]!;
        const b = clusters[j]!;
        separate(a, b);
      }
    }
  }
  for (const cluster of clusters) {
    cluster.x = round(cluster.x);
    cluster.y = round(cluster.y);
  }
}

/** Push two overlapping boxes apart, sideways unless moving up or down is much shorter. Returns whether they overlapped. */
function separate(a: Cluster, b: Cluster): boolean {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const overlapX = a.halfWidth + b.halfWidth + GAP - Math.abs(dx);
  const overlapY = a.halfHeight + b.halfHeight + GAP - Math.abs(dy);
  if (overlapX <= 0 || overlapY <= 0) {
    return false;
  }
  // Prefer a sideways move even when it is up to twice as long, so titles sit in rows, not one tall column.
  if (overlapX * 0.5 < overlapY) {
    const shift = (overlapX / 2) * (dx < 0 ? -1 : 1);
    a.x -= shift;
    b.x += shift;
  } else {
    const shift = (overlapY / 2) * (dy < 0 ? -1 : 1);
    a.y -= shift;
    b.y += shift;
  }
  return true;
}

function commonExtension(files: MapFile[]): string {
  const counts = new Map<string, number>();
  for (const file of files) {
    const ext = extension(file.path);
    counts.set(ext, (counts.get(ext) ?? 0) + 1);
  }
  return [...counts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? "";
}

function extension(path: string): string {
  const name = path.split("/").at(-1) ?? path;
  return name.includes(".") ? (name.split(".").at(-1) ?? "") : "";
}

function hash(value: string): number {
  let result = 0;
  for (let index = 0; index < value.length; index += 1) {
    result = (result * 31 + value.charCodeAt(index)) >>> 0;
  }
  return result;
}

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/** Fill for a dot: the folder color, a lighter or darker shade of it, or a muted one for another language. */
export function dotFill(color: string, tone: Dot["tone"]): string {
  if (tone === "light") {
    return `color-mix(in oklab, ${color} 78%, white)`;
  }
  if (tone === "dark") {
    return `color-mix(in oklab, ${color} 72%, black)`;
  }
  if (tone === "other") {
    return `color-mix(in oklab, ${color} 45%, #8b8b96)`;
  }
  return color;
}
