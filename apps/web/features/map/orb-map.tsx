"use client";

import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { memo, useEffect, useMemo, useState } from "react";

import type { FileGraph } from "../../lib/api";
import { cn } from "../../lib/cn";
import type { OpenFile } from "../code/code-viewer";
import { buildClusters, dotFill, shortName, type Cluster, type Dot } from "./clusters";
import { MapInspector } from "./map-inspector";
import type { MapNodeData } from "./map-model";

type Selection = { kind: "cluster"; key: string } | { kind: "file"; path: string } | null;
type Mark = "selected" | "neighbor" | "cited" | "trace";

type ClusterData = {
  cluster: Cluster;
  dimmed: boolean;
  active: boolean;
  marks: Map<string, Mark>;
  onPick: (path: string) => void;
  onPickCluster: (key: string) => void;
};
type ClusterNode = Node<ClusterData, "cluster">;
type BandEdgeType = Edge<{ label: string; count: number; show: "full" | "count" | null }, "band">;

export type OrbTarget = { path: string; nonce: number } | null;

export function OrbMap({
  graph,
  cited,
  trace,
  target,
  onOpen,
}: {
  graph: FileGraph;
  cited: string[];
  trace: string[];
  target: OrbTarget;
  onOpen: (file: OpenFile) => void;
}) {
  const map = useMemo(() => buildClusters(graph), [graph]);
  const [selection, setSelection] = useState<Selection>(null);
  const [hoveredLink, setHoveredLink] = useState<string | null>(null);
  const { setCenter } = useReactFlow();

  const byKey = useMemo(() => new Map(map.clusters.map((cluster) => [cluster.key, cluster])), [map]);

  const activeKey = selection?.kind === "cluster" ? selection.key : selection?.kind === "file" ? (map.clusterOf.get(selection.path) ?? null) : null;

  const linked = useMemo(() => {
    if (activeKey === null) {
      return null;
    }
    const keys = new Set([activeKey]);
    for (const link of map.links) {
      if (link.source === activeKey) {
        keys.add(link.target);
      }
      if (link.target === activeKey) {
        keys.add(link.source);
      }
    }
    return keys;
  }, [activeKey, map.links]);

  const marks = useMemo(() => {
    const result = new Map<string, Mark>();
    for (const path of trace) {
      result.set(path, "trace");
    }
    for (const path of cited) {
      result.set(path, "cited");
    }
    if (selection?.kind === "file") {
      for (const edge of graph.edges) {
        if (edge.source === selection.path) {
          result.set(edge.target, "neighbor");
        }
        if (edge.target === selection.path) {
          result.set(edge.source, "neighbor");
        }
      }
      result.set(selection.path, "selected");
    }
    return result;
  }, [cited, trace, selection, graph.edges]);

  function focusFile(path: string) {
    const key = map.clusterOf.get(path);
    const cluster = key ? byKey.get(key) : undefined;
    const dot = cluster?.dots.find((item) => item.path === path);
    setSelection({ kind: "file", path });
    if (cluster && dot) {
      void setCenter(cluster.x + dot.x, cluster.y + dot.y, { zoom: 1.6, duration: 450 });
    }
  }

  useEffect(() => {
    if (target) {
      const timer = window.setTimeout(() => focusFile(target.path), 0);
      return () => window.clearTimeout(timer);
    }
    // Run only when a new target arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  const nodes: ClusterNode[] = useMemo(
    () =>
      map.clusters.map((cluster) => ({
        id: cluster.key,
        type: "cluster" as const,
        // The node's box covers the title too, so fitting the view never cuts a title off.
        position: { x: cluster.x - cluster.halfWidth, y: cluster.y - cluster.halfHeight },
        width: cluster.halfWidth * 2,
        height: cluster.halfHeight * 2,
        data: {
          cluster,
          dimmed: linked !== null && !linked.has(cluster.key),
          active: cluster.key === activeKey,
          marks,
          onPick: (path: string) => setSelection({ kind: "file", path }),
          onPickCluster: (key: string) => setSelection((current) => (current?.kind === "cluster" && current.key === key ? null : { kind: "cluster", key })),
        },
      })),
    [map.clusters, linked, activeKey, marks],
  );

  const edges: BandEdgeType[] = useMemo(
    () =>
      map.links.map((link) => {
        const touches = activeKey !== null && (link.source === activeKey || link.target === activeKey);
        const hovered = hoveredLink === link.id;
        const color = byKey.get(link.source)?.color ?? "var(--color-line-strong)";
        return {
          id: link.id,
          source: link.source,
          target: link.target,
          type: "band" as const,
          interactionWidth: 16,
          data: {
            label: `${shortName(link.source)} ↔ ${shortName(link.target)} · ${link.weight} import${link.weight === 1 ? "" : "s"}`,
            count: link.weight,
            show: hovered ? "full" : touches ? "count" : null,
          },
          style: {
            stroke: color,
            strokeWidth: Math.min(1.6 + Math.log2(link.weight + 1) * 1.7, 13),
            strokeLinecap: "round" as const,
            opacity: hovered ? 0.85 : activeKey === null ? 0.34 : touches ? 0.75 : 0.05,
            transition: "opacity 200ms",
          },
        };
      }),
    [map.links, activeKey, byKey, hoveredLink],
  );

  const inspected: { node: MapNodeData; members?: FileGraph["files"] } | null = useMemo(() => {
    if (selection?.kind === "cluster") {
      const cluster = byKey.get(selection.key);
      if (!cluster) {
        return null;
      }
      return {
        node: {
          kind: "folder",
          id: `cluster:${cluster.key}`,
          label: cluster.label,
          sublabel: cluster.key,
          fileCount: cluster.files.length,
          symbolCount: cluster.symbolCount,
        },
        members: cluster.files,
      };
    }
    if (selection?.kind === "file") {
      const file = graph.files.find((item) => item.path === selection.path);
      if (!file) {
        return null;
      }
      const parts = file.path.split("/");
      return {
        node: {
          kind: "file",
          id: `file:${file.path}`,
          label: parts.at(-1) ?? file.path,
          sublabel: parts.slice(0, -1).join("/") || "(root)",
          fileCount: 1,
          symbolCount: file.symbol_count,
          file,
        },
      };
    }
    return null;
  }, [selection, byKey, graph.files]);

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        key={map.clusters.map((cluster) => `${cluster.key}@${cluster.x},${cluster.y}`).join("|")}
        fitView
        fitViewOptions={{ padding: 0.06, maxZoom: 1.4 }}
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onPaneClick={() => setSelection(null)}
        onEdgeMouseEnter={(_, edge) => setHoveredLink(edge.id)}
        onEdgeMouseLeave={() => setHoveredLink(null)}
        nodesConnectable={false}
        nodesDraggable
        minZoom={0.1}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1} color="var(--color-line)" />
        <Controls showInteractive={false} position="bottom-left" className="!m-3 !overflow-hidden !rounded-xl !border !border-line !shadow-none" />
      </ReactFlow>

      <div className="pointer-events-none absolute top-3 left-3 font-mono text-[11px] text-faint">
        <p>
          <span className="text-muted-foreground">{map.clusters.length}</span> folders · <span className="text-muted-foreground">{graph.files.length}</span> files ·{" "}
          <span className="text-muted-foreground">{graph.edges.length}</span> imports
        </p>
        <p className="mt-0.5">click a folder or a dot · scroll to zoom</p>
      </div>

      {inspected === null ? (
        <div className="pointer-events-none absolute right-3 bottom-3 hidden items-center gap-4 rounded-lg border border-line bg-canvas px-3 py-2 text-[11px] text-muted-foreground sm:flex">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-fg/70" /> file
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-faint" /> other language
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1 w-5 rounded-full bg-fg/40" /> imports, wider is more
          </span>
        </div>
      ) : (
        <MapInspector
          node={inspected.node}
          members={inspected.members}
          graph={graph}
          onClose={() => setSelection(null)}
          onOpen={onOpen}
          onReveal={focusFile}
        />
      )}
    </div>
  );
}

function baseName(path: string): string {
  return path.split("/").at(-1) ?? path;
}

const CENTER_HANDLE = "!top-1/2 !left-1/2 !h-px !w-px !min-h-0 !min-w-0 !border-0 !bg-transparent !opacity-0";

const MARK_STROKE: Record<Mark, string> = {
  selected: "var(--color-fg)",
  neighbor: "color-mix(in oklab, var(--color-fg) 70%, transparent)",
  cited: "var(--color-brand)",
  trace: "var(--color-warn)",
};

const ClusterBlob = memo(function ClusterBlob({ data }: NodeProps<ClusterNode>) {
  const { cluster, marks } = data;
  const [hover, setHover] = useState<Dot | null>(null);
  const size = cluster.radius * 2;
  const shown = hover?.path ?? cluster.hub;
  // The hub label sits off the lower right edge, like a caption; a hovered file's label sits beside its dot.
  const anchor = hover
    ? { left: cluster.radius + hover.x + hover.r, top: cluster.radius + hover.y }
    : { left: cluster.radius * 1.62, top: cluster.radius * 1.72 };
  return (
    <div className={cn("pointer-events-none relative h-full w-full transition-opacity duration-300", data.dimmed && "opacity-20")}>
      <Handle type="target" position={Position.Top} className={CENTER_HANDLE} isConnectable={false} />
      <Handle type="source" position={Position.Bottom} className={CENTER_HANDLE} isConnectable={false} />
      <div
        className="pointer-events-auto absolute"
        style={{ left: cluster.halfWidth - cluster.radius, top: cluster.halfHeight - cluster.radius, width: size, height: size }}
      >

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          data.onPickCluster(cluster.key);
        }}
        className="absolute bottom-full left-1/2 mb-2.5 inline-flex -translate-x-1/2 items-center gap-1.5 whitespace-nowrap rounded-md px-1.5 py-0.5 font-mono text-[12.5px] transition-colors hover:bg-hover"
      >
        <span className="size-2 rounded-full" style={{ background: cluster.color }} />
        <span className={cn("font-semibold", data.active ? "text-fg" : "text-fg/90")}>{shortName(cluster.label)}</span>
        <span className="text-faint">{cluster.files.length}</span>
      </button>

      <svg
        width={size}
        height={size}
        viewBox={`${-cluster.radius} ${-cluster.radius} ${size} ${size}`}
        className="overflow-visible"
        onClick={() => data.onPickCluster(cluster.key)}
      >
        {data.active ? (
          <circle r={cluster.radius + 7} fill="none" strokeDasharray="2 4" style={{ stroke: cluster.color, strokeOpacity: 0.7 }} className="pointer-events-none" />
        ) : null}
        {cluster.dots.map((dot) => {
          const mark = marks.get(dot.path);
          return (
            <circle
              key={dot.path}
              cx={dot.x}
              cy={dot.y}
              r={hover?.path === dot.path ? dot.r * 1.5 : dot.r}
              style={{
                fill: dotFill(cluster.color, dot.tone),
                stroke: mark ? MARK_STROKE[mark] : "var(--color-canvas)",
                strokeWidth: mark ? 1.8 : 0.7,
                strokeOpacity: mark ? 1 : 0.55,
                transition: "r 120ms",
              }}
              className="cursor-pointer"
              onMouseEnter={() => setHover(dot)}
              onMouseLeave={() => setHover((current) => (current?.path === dot.path ? null : current))}
              onClick={(event) => {
                event.stopPropagation();
                data.onPick(dot.path);
              }}
            />
          );
        })}
      </svg>

      {shown ? (
        <span
          className={cn(
            "pointer-events-none absolute z-10 -translate-y-1/2 whitespace-nowrap rounded-md border border-line bg-canvas px-1.5 py-0.5 font-mono text-[11px]",
            hover ? "translate-x-2 text-fg" : "text-muted-foreground",
          )}
          style={anchor}
        >
          {hover ? hover.path : baseName(shown)}
        </span>
      ) : null}
      </div>
    </div>
  );
});

/** A gentle bend, always to the same side for a pair. Shows its import count when its folder is selected, and both folder names on hover. */
function BandEdge({ id, sourceX, sourceY, targetX, targetY, style, data }: EdgeProps<BandEdgeType>) {
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const qx = (sourceX + targetX) / 2 - dy * 0.14;
  const qy = (sourceY + targetY) / 2 + dx * 0.14;
  // The middle of a quadratic curve: a quarter of each end plus half the control point.
  const midX = sourceX / 4 + qx / 2 + targetX / 4;
  const midY = sourceY / 4 + qy / 2 + targetY / 4;
  return (
    <>
      <BaseEdge id={id} path={`M ${sourceX} ${sourceY} Q ${qx} ${qy} ${targetX} ${targetY}`} style={style} />
      {data?.show ? (
        <EdgeLabelRenderer>
          <span
            className={cn(
              "pointer-events-none absolute rounded-md border border-line bg-canvas font-mono text-[10.5px] whitespace-nowrap",
              data.show === "full" ? "z-30 px-1.5 py-0.5 text-fg" : "z-20 min-w-5 px-1 text-center text-muted-foreground",
            )}
            style={{ transform: `translate(-50%, -50%) translate(${midX}px, ${midY}px)` }}
          >
            {data.show === "full" ? data.label : data.count}
          </span>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const NODE_TYPES = { cluster: ClusterBlob };
const EDGE_TYPES = { band: BandEdge };
