import type { ELK, ElkNode } from "elkjs/lib/elk-api";

import { nodeSize, type MapModel } from "./map-model";

export type Positions = Record<string, { x: number; y: number }>;

const LAYOUT_OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.layered.spacing.nodeNodeBetweenLayers": "120",
  "elk.spacing.nodeNode": "36",
  "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.separateConnectedComponents": "true",
  "elk.spacing.componentComponent": "60",
};

const WORKER_TIMEOUT_MS = 8000;

let workerElk: Promise<ELK | null> | null = null;

function whenReady(worker: Worker): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      worker.terminate();
      reject(new Error("worker did not start"));
    }, WORKER_TIMEOUT_MS);
    worker.onmessage = (event: MessageEvent<{ ready?: boolean }>) => {
      if (event.data?.ready) {
        window.clearTimeout(timer);
        resolve();
      }
    };
    worker.onerror = () => {
      window.clearTimeout(timer);
      worker.terminate();
      reject(new Error("worker failed"));
    };
  });
}

function getWorkerElk(): Promise<ELK | null> {
  if (workerElk === null) {
    workerElk = (async () => {
      if (typeof Worker === "undefined") {
        return null;
      }
      try {
        const worker = new Worker(new URL("./elk.worker.ts", import.meta.url));
        await whenReady(worker);
        const { default: ElkApi } = await import("elkjs/lib/elk-api.js");
        return new ElkApi({ workerFactory: () => worker });
      } catch {
        return null;
      }
    })();
  }
  return workerElk;
}

async function runLayout(graph: ElkNode): Promise<ElkNode> {
  const elk = await getWorkerElk();
  if (elk) {
    try {
      return await Promise.race([
        elk.layout(graph),
        new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("timeout")), WORKER_TIMEOUT_MS)),
      ]);
    } catch {
      workerElk = Promise.resolve(null);
    }
  }
  const { default: ElkBundled } = await import("elkjs/lib/elk.bundled.js");
  return new ElkBundled().layout(graph);
}

/** Layered left-to-right layout: an importer sits to the left of what it imports. */
export async function layoutModel(model: MapModel): Promise<Positions> {
  const graph: ElkNode = {
    id: "root",
    layoutOptions: LAYOUT_OPTIONS,
    children: model.nodes.map((node) => ({ id: node.id, ...nodeSize(node.kind) })),
    edges: model.edges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };
  const result = await runLayout(graph);
  const positions: Positions = {};
  for (const child of result.children ?? []) {
    positions[child.id] = { x: child.x ?? 0, y: child.y ?? 0 };
  }
  return positions;
}
