"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useStore,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Box, ChevronsDownUp, CircleDot, Folder, Network, Package, Search } from "lucide-react";
import { memo, useEffect, useMemo, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import type { FileGraph } from "../../lib/api";
import { cn } from "../../lib/cn";
import type { OpenFile } from "../code/code-viewer";
import { colorsByCluster } from "./colors";
import { MapInspector } from "./map-inspector";
import { buildModel, folderChain, initialExpansion, neighborhood, nodeSize, type MapNodeData } from "./map-model";
import { layoutModel, type Positions } from "./layout";
import { orbitLayout, orbBox, clusterKey, type Halo } from "./orbit";

type NodeData = MapNodeData & { dimmed: boolean; selected: boolean; cited: boolean; onTrace: boolean; color: string };
type FlowNode = Node<NodeData>;
type HaloNode = Node<{ label: string; color: string }, "halo">;
type MapMode = "orbs" | "graph";

export type MapProps = {
  graph: FileGraph | null;
  cited: string[];
  trace?: string[];
  focusPath?: string | null;
  onOpen: (file: OpenFile) => void;
};

export function RepoMap(props: MapProps) {
  return (
    <ReactFlowProvider>
      <MapCanvas {...props} />
    </ReactFlowProvider>
  );
}

function MapCanvas({ graph, cited, trace = [], focusPath = null, onOpen }: MapProps) {
  const paths = useMemo(() => graph?.files.map((file) => file.path) ?? [], [graph]);
  const [expanded, setExpanded] = useState<{ key: string; set: Set<string> }>({ key: "", set: new Set() });
  const [showPackages, setShowPackages] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [layout, setLayout] = useState<{ key: string; positions: Positions } | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<MapMode>("orbs");
  const { setCenter } = useReactFlow();

  const pathsKey = paths.join("|");
  const expandedSet = useMemo(
    () => (expanded.key === pathsKey ? expanded.set : initialExpansion(paths)),
    [expanded, pathsKey, paths],
  );

  const model = useMemo(
    () => (graph ? buildModel(graph, expandedSet, showPackages) : { nodes: [], edges: [], hidden: 0 }),
    [graph, expandedSet, showPackages],
  );
  const modelKey = useMemo(
    () => `${model.nodes.map((node) => node.id).join(",")}#${model.edges.length}`,
    [model],
  );

  const orbit = useMemo(() => orbitLayout(model.nodes), [model.nodes]);

  useEffect(() => {
    if (mode !== "graph" || model.nodes.length === 0) {
      return;
    }
    let cancelled = false;
    layoutModel(model)
      .then((positions) => {
        if (!cancelled) {
          setLayout({ key: modelKey, positions });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [mode, model, modelKey]);

  const positions = mode === "orbs" ? orbit.positions : layout?.key === modelKey ? layout.positions : null;

  function setExpandedSet(next: Set<string>) {
    setExpanded({ key: pathsKey, set: next });
  }

  function reveal(path: string) {
    const next = new Set(expandedSet);
    for (const folder of folderChain(path)) {
      next.add(folder);
    }
    setExpandedSet(next);
    setSelected(`file:${path}`);
  }

  useEffect(() => {
    if (focusPath && paths.includes(focusPath)) {
      const timer = window.setTimeout(() => reveal(focusPath), 0);
      return () => window.clearTimeout(timer);
    }
    // reveal reads the current expansion; re-run only when the focus target changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusPath]);

  const focus = useMemo(() => (selected ? neighborhood(model, selected) : null), [model, selected]);
  const citedNodes = useMemo(() => new Set(cited.map((path) => ownerId(path, model.nodes))), [cited, model.nodes]);
  const traceNodes = useMemo(() => trace.map((path) => ownerId(path, model.nodes)), [trace, model.nodes]);
  const traceEdges = useMemo(() => {
    const ids = new Set<string>();
    for (let index = 0; index < traceNodes.length - 1; index += 1) {
      ids.add(`${traceNodes[index]}->${traceNodes[index + 1]}`);
      ids.add(`${traceNodes[index + 1]}->${traceNodes[index]}`);
    }
    return ids;
  }, [traceNodes]);

  const colorOf = useMemo(() => {
    const palette = colorsByCluster(model.nodes.map((node) => clusterKey(node)));
    return new Map(model.nodes.map((node) => [node.id, palette.get(clusterKey(node)) ?? GRAPH_FALLBACK]));
  }, [model.nodes]);
  const nodes: Array<FlowNode | HaloNode> = useMemo(() => {
    if (!positions) {
      return [];
    }
    const onTrace = new Set(traceNodes);
    const drawn: Array<FlowNode | HaloNode> = model.nodes.map((node) => {
      const box = mode === "orbs" ? orbBox(node.kind, node.fileCount) : nodeSize(node.kind);
      const point = positions[node.id] ?? { x: 0, y: 0 };
      return {
        id: node.id,
        type: mode === "orbs" ? "orb" : node.kind,
        position: mode === "orbs" ? { x: point.x - box.width / 2, y: point.y - box.height / 2 } : point,
        ...box,
        zIndex: 1,
        data: {
          ...node,
          dimmed: focus !== null && !focus.has(node.id),
          selected: node.id === selected,
          cited: citedNodes.has(node.id),
          onTrace: onTrace.has(node.id),
          color: colorOf.get(node.id) ?? GRAPH_FALLBACK,
        },
      };
    });
    if (mode === "orbs") {
      drawn.unshift(...haloNodes(orbit.halos));
    }
    return drawn;
  }, [model.nodes, positions, focus, selected, citedNodes, traceNodes, colorOf, mode, orbit.halos]);

  const edges: Edge[] = useMemo(
    () =>
      model.edges.map((edge) => {
        const touches = selected !== null && (edge.source === selected || edge.target === selected);
        const traced = traceEdges.has(edge.id);
        const color = traced
          ? "var(--color-warn)"
          : touches
            ? edge.source === selected
              ? "var(--color-info)"
              : "var(--color-brand)"
            : edge.status === "unresolved"
              ? "var(--color-faint)"
              : (colorOf.get(edge.source) ?? "var(--color-line-strong)");
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          animated: touches || traced,
          style: {
            stroke: color,
            strokeWidth: mode === "orbs" ? (touches || traced ? 1.7 : 1.1) : Math.min(1 + Math.log2(edge.weight + 1) * 0.6, 3.5) + (touches || traced ? 0.6 : 0),
            strokeDasharray: edge.status === "unresolved" ? "4 4" : edge.status === "resolved" ? "1 0" : undefined,
            opacity: focus !== null && !touches && !traced ? 0.08 : mode === "orbs" ? 0.55 : 0.9,
          },
        };
      }),
    [model.edges, selected, focus, traceEdges, colorOf, mode],
  );

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const needle = query.trim().toLowerCase();
    if (needle === "") {
      return;
    }
    const match = paths.find((path) => path.toLowerCase().endsWith(needle)) ?? paths.find((path) => path.toLowerCase().includes(needle));
    if (match) {
      reveal(match);
      window.setTimeout(() => {
        const position = layoutPoint(mode, layout, orbit.positions, match);
        if (position) {
          void setCenter(position.x, position.y, { zoom: mode === "orbs" ? 1.35 : 1, duration: 400 });
        }
      }, mode === "orbs" ? 40 : 450);
    }
  }

  if (graph === null) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <Spinner /> Loading the graph
      </div>
    );
  }
  if (graph.files.length === 0) {
    return (
      <Empty className="h-full border-0">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Network />
          </EmptyMedia>
          <EmptyTitle>No JavaScript or TypeScript files to draw</EmptyTitle>
          <EmptyDescription>The architecture map is built by the TypeScript compiler. Other languages are still searchable and answerable.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const selectedNode = model.nodes.find((node) => node.id === selected) ?? null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-col gap-2 border-b border-line px-3 py-2">
        <form onSubmit={onSearch} className="relative">
          <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input
            aria-label="Find a file on the map"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a file"
            className="h-8 w-full rounded-lg border border-line bg-panel pl-8 pr-2 text-xs text-fg outline-none placeholder:text-faint focus:border-line-strong"
          />
        </form>
        <div className="flex h-8 items-center gap-0.5 self-start rounded-lg border border-line bg-panel p-0.5">
          <ToolbarButton active={mode === "orbs"} onClick={() => setMode("orbs")} title="Dotted orbs, one cluster per folder">
            <CircleDot size={13} /> Orbs
          </ToolbarButton>
          <ToolbarButton active={mode === "graph"} onClick={() => setMode("graph")} title="Labeled cards in a layered graph">
            <Network size={13} /> Graph
          </ToolbarButton>
          <ToolbarButton active={showPackages} onClick={() => setShowPackages((value) => !value)} title="Show external packages" aria-label="Show external packages">
            <Package size={13} />
          </ToolbarButton>
          <ToolbarButton onClick={() => setExpandedSet(initialExpansion(paths))} title="Reset folders to the overview" aria-label="Reset folders to the overview">
            <ChevronsDownUp size={13} />
          </ToolbarButton>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
      <ReactFlow
        key={`${mode}:${positions ? modelKey : "pending"}`}
        fitView
        fitViewOptions={mode === "orbs" ? ORB_FIT : FIT_VIEW}
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        defaultEdgeOptions={{ type: mode === "orbs" ? "default" : "smoothstep" }}
        onNodeClick={(_, node) => {
          if (node.type === "halo") {
            return;
          }
          setSelected(node.id === selected ? null : node.id);
        }}
        onNodeDoubleClick={(_, node) => {
          if (node.type === "halo") {
            return;
          }
          const data = node.data as NodeData;
          if (data.kind === "folder") {
            const next = new Set(expandedSet);
            next.add(data.sublabel);
            setExpandedSet(next);
          } else if (data.kind === "file" && data.file) {
            onOpen({ path: data.file.path });
          }
        }}
        onPaneClick={() => setSelected(null)}
        nodesConnectable={false}
        nodesDraggable
        minZoom={0.15}
        maxZoom={2.4}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background variant={BackgroundVariant.Dots} gap={mode === "orbs" ? 28 : 22} size={mode === "orbs" ? 1.2 : 1} color="var(--color-line)" />
        <Controls showInteractive={false} position="bottom-left" className="!m-3 !overflow-hidden !rounded-xl !border !border-line !shadow-none" />
      </ReactFlow>

      {model.hidden > 0 || graph.truncated ? (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
          <Badge variant="warn">
            {model.hidden > 0 ? `${model.hidden} nodes hidden. Collapse folders to see them.` : "Graph response truncated at the server limit."}
          </Badge>
        </div>
      ) : null}

      {!positions && mode === "graph" ? (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Spinner /> Laying out {model.nodes.length} nodes
        </div>
      ) : null}

      {selectedNode ? (
        <MapInspector
          node={selectedNode}
          graph={graph}
          onClose={() => setSelected(null)}
          onOpen={onOpen}
          onExpand={(folder) => {
            const next = new Set(expandedSet);
            next.add(folder);
            setExpandedSet(next);
            setSelected(null);
          }}
          onCollapse={(folder) => {
            const next = new Set([...expandedSet].filter((item) => item !== folder && !item.startsWith(`${folder}/`)));
            setExpandedSet(next);
            setSelected(`folder:${folder}`);
          }}
          onReveal={reveal}
        />
      ) : null}
      </div>
    </div>
  );
}

const GRAPH_FALLBACK = "#38bdf8";

function ownerId(path: string, nodes: MapNodeData[]): string {
  const direct = `file:${path}`;
  if (nodes.some((node) => node.id === direct)) {
    return direct;
  }
  const folders = folderChain(path).reverse();
  for (const folder of folders) {
    const id = `folder:${folder}`;
    if (nodes.some((node) => node.id === id)) {
      return id;
    }
  }
  return direct;
}

function ToolbarButton({
  active = false,
  children,
  ...rest
}: { active?: boolean; children: React.ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs transition-colors",
        active ? "bg-hover text-fg" : "text-muted-foreground hover:bg-hover hover:text-fg",
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

function layoutPoint(mode: MapMode, elk: { positions: Positions } | null, orbitPositions: Positions, path: string): { x: number; y: number } | null {
  const id = `file:${path}`;
  if (mode === "orbs") {
    return orbitPositions[id] ?? null;
  }
  const point = elk?.positions[id];
  return point ? { x: point.x + 110, y: point.y + 36 } : null;
}

function haloNodes(halos: Halo[]): HaloNode[] {
  return halos.map((halo) => ({
    id: halo.id,
    type: "halo" as const,
    position: { x: halo.cx - halo.radius, y: halo.cy - halo.radius },
    width: halo.radius * 2,
    height: halo.radius * 2,
    data: { label: halo.label === "(root)" || halo.label === "packages" ? halo.label : (halo.label.split("/").at(-1) ?? halo.label), color: halo.color },
    draggable: false,
    selectable: false,
    connectable: false,
    zIndex: 0,
  }));
}

const zoomedIn = (state: { transform: [number, number, number] }) => state.transform[2] >= 0.75;

function frame(data: NodeData) {
  return cn(
    "h-full w-full rounded-2xl border transition-[opacity,border-color,box-shadow] duration-200",
    data.dimmed && "opacity-25",
  );
}

function nodeStyle(data: NodeData): { borderColor: string; background: string; boxShadow: string } {
  const border = data.selected ? data.color : data.onTrace ? "#fbbf24" : `color-mix(in oklab, ${data.color} 55%, #232329)`;
  return {
    borderColor: border,
    background: data.selected ? `color-mix(in oklab, ${data.color} 14%, #101014)` : "#101014",
    boxShadow: data.selected
      ? `0 0 0 1px ${data.color}, 0 0 28px color-mix(in oklab, ${data.color} 45%, transparent)`
      : "0 12px 32px rgba(0,0,0,0.35)",
  };
}

const FolderNode = memo(function FolderNode({ data }: NodeProps<FlowNode>) {
  const detailed = useStore(zoomedIn);
  return (
    <div className={cn(frame(data), "bg-panel")} style={nodeStyle(data)}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0" style={{ background: data.color }} />
      <div className="flex h-full items-center gap-3 px-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-950" style={{ background: data.color, boxShadow: `0 0 16px ${data.color}` }}>
          <Folder size={15} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-fg">{data.label}/</p>
          <p className="truncate text-[11px] text-muted-foreground">
            {data.fileCount} files{detailed ? ` · ${data.symbolCount} symbols` : ""}
          </p>
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0" style={{ background: data.color }} />
    </div>
  );
});

const FileNode = memo(function FileNode({ data }: NodeProps<FlowNode>) {
  const detailed = useStore(zoomedIn);
  const symbols = data.file?.top_symbols ?? [];
  return (
    <div className={frame(data)} style={nodeStyle(data)}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0" style={{ background: data.color }} />
      <div className="flex h-full flex-col justify-center gap-1 px-3">
        <div className="flex items-center gap-2">
          <span className="size-2.5 shrink-0 rounded-full" style={{ background: data.color }} />
          <p className="truncate font-mono text-[12px] text-fg">{data.label}</p>
          {data.file?.parse_status === "failed" ? <Badge variant="destructive">parse error</Badge> : null}
        </div>
        {detailed ? (
          <div className="flex flex-wrap gap-1 overflow-hidden" style={{ maxHeight: 34 }}>
            {symbols.slice(0, 4).map((symbol) => (
              <span key={`${symbol.name}-${symbol.start_line}`} className="inline-flex items-center gap-1 rounded bg-panel px-1 font-mono text-[10px] text-muted-foreground">
                <Box size={9} className={symbol.exported ? "text-brand" : "text-faint"} />
                {symbol.name}
              </span>
            ))}
            {symbols.length === 0 ? <span className="text-[10px] text-faint">no declarations</span> : null}
          </div>
        ) : (
          <p className="truncate text-[11px] text-faint">{data.sublabel}</p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0" style={{ background: data.color }} />
    </div>
  );
});

const PackageNode = memo(function PackageNode({ data }: NodeProps<FlowNode>) {
  return (
    <div className={cn(frame(data), "border-dashed")} style={nodeStyle(data)}>
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0" style={{ background: data.color }} />
      <div className="flex h-full items-center gap-2 px-3">
        <Package size={13} className="shrink-0 text-faint" />
        <p className="truncate font-mono text-[11px] text-muted-foreground">{data.label}</p>
      </div>
    </div>
  );
});

const OrbNode = memo(function OrbNode({ data }: NodeProps<FlowNode>) {
  return (
    <div className={cn("group relative h-full w-full", data.dimmed && "opacity-25")} title={data.kind === "file" ? data.file?.path : data.sublabel}>
      <Handle type="target" position={Position.Left} className="!h-px !w-px !border-0 !bg-transparent !opacity-0" />
      <span
        className={cn("block h-full w-full rounded-full transition-transform duration-200 group-hover:scale-125", data.kind === "package" && "border border-dashed bg-transparent")}
        style={{
          background: data.kind === "package" ? "transparent" : data.color,
          borderColor: data.color,
          boxShadow: data.selected ? `0 0 0 3px ${data.color}` : undefined,
        }}
      />
      {data.kind === "folder" ? null : (
        <span
          className={cn(
            "pointer-events-none absolute left-1/2 top-full mt-1 -translate-x-1/2 whitespace-nowrap font-mono text-[10px]",
            data.selected ? "text-fg" : "text-muted-foreground opacity-0 group-hover:opacity-100",
          )}
        >
          {data.label}
        </span>
      )}
      <Handle type="source" position={Position.Right} className="!h-px !w-px !border-0 !bg-transparent !opacity-0" />
    </div>
  );
});

function HaloRing({ data }: NodeProps<HaloNode>) {
  return (
    <div className="relative h-full w-full rounded-full border border-dashed" style={{ borderColor: `color-mix(in oklab, ${data.color} 45%, transparent)` }}>
      <span className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 rounded-full bg-background/80 px-2 font-mono text-[10px] text-muted-foreground">
        {data.label}
      </span>
    </div>
  );
}

const NODE_TYPES = { folder: FolderNode, file: FileNode, package: PackageNode, orb: OrbNode, halo: HaloRing };
const FIT_VIEW = { padding: 0.16, maxZoom: 1.05 };
const ORB_FIT = { padding: 0.2, minZoom: 0.68, maxZoom: 1.35 };
