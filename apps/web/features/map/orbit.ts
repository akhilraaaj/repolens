import type { Positions } from "./layout";
import { colorsByCluster } from "./colors";
import type { MapNodeData } from "./map-model";

/** Golden angle. Successive dots turn by this much, so they fill a disc instead of lining up. */
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

export type Halo = {
  id: string;
  label: string;
  color: string;
  cx: number;
  cy: number;
  radius: number;
};

export type OrbitLayout = {
  positions: Positions;
  halos: Halo[];
};

/** Place each folder's files in a spiral, then place those spirals on one ring. */
export function orbitLayout(nodes: MapNodeData[]): OrbitLayout {
  const groups = new Map<string, MapNodeData[]>();
  for (const node of nodes) {
    const key = clusterKey(node);
    const list = groups.get(key) ?? [];
    list.push(node);
    groups.set(key, list);
  }
  for (const list of groups.values()) {
    list.sort((left, right) => left.label.localeCompare(right.label));
  }

  const keys = [...groups.keys()].sort((left, right) => {
    if (left === "packages") {
      return 1;
    }
    if (right === "packages") {
      return -1;
    }
    return left.localeCompare(right);
  });
  const radii = keys.map((key) => clusterRadius(groups.get(key)?.length ?? 1));
  const ring = keys.length <= 1 ? 0 : ringRadius(keys, radii);
  const positions: Positions = {};
  const halos: Halo[] = [];
  const palette = colorsByCluster(keys);

  keys.forEach((key, groupIndex) => {
    const members = groups.get(key) ?? [];
    const localRadius = radii[groupIndex] ?? 36;
    const angle = -Math.PI / 2 + (groupIndex / keys.length) * Math.PI * 2;
    const cx = Math.cos(angle) * ring;
    const cy = Math.sin(angle) * ring;
    halos.push({
      id: `halo:${key}`,
      label: key,
      color: palette.get(key) ?? "#38bdf8",
      cx,
      cy,
      radius: localRadius,
    });
    members.forEach((node, index) => {
      if (members.length === 1) {
        positions[node.id] = { x: cx, y: cy };
        return;
      }
      const radius = 16 + Math.sqrt(index) * 14;
      const theta = index * GOLDEN;
      positions[node.id] = {
        x: cx + Math.cos(theta) * radius,
        y: cy + Math.sin(theta) * radius,
      };
    });
  });

  return { positions, halos };
}

export function clusterKey(node: Pick<MapNodeData, "kind" | "label" | "sublabel">): string {
  if (node.kind === "package") {
    return "packages";
  }
  if (node.kind === "folder") {
    return node.sublabel;
  }
  return node.sublabel === "(root)" ? "(root)" : node.sublabel;
}

function clusterRadius(count: number): number {
  if (count <= 1) {
    return 32;
  }
  return 16 + Math.sqrt(count - 1) * 14 + 26;
}

/** Halo labels are 10px mono with 8px padding each side. */
const LABEL_CHAR = 6.2;
const LABEL_PAD = 16;
const HALO_GAP = 18;

/**
 * Large enough that each cluster's arc holds its halo and its label.
 * The old average-based radius packed 20+ folders into overlapping circles.
 */
function ringRadius(keys: string[], radii: number[]): number {
  const arc = keys.reduce((sum, key, index) => {
    const halo = (radii[index] ?? 32) * 2 + HALO_GAP;
    const label = haloLabel(key).length * LABEL_CHAR + LABEL_PAD + HALO_GAP;
    return sum + Math.max(halo, label);
  }, 0);
  const average = radii.reduce((sum, value) => sum + value, 0) / radii.length;
  return Math.max(average + 64, arc / (Math.PI * 2));
}

/** The text a halo shows: the last folder segment, except for the two fixed groups. */
export function haloLabel(key: string): string {
  return key === "(root)" || key === "packages" ? key : (key.split("/").at(-1) ?? key);
}

export function orbBox(kind: MapNodeData["kind"], fileCount: number): { width: number; height: number } {
  if (kind === "folder") {
    const diameter = 22 + Math.min(fileCount, 8) * 2;
    return { width: diameter, height: diameter };
  }
  if (kind === "package") {
    return { width: 16, height: 16 };
  }
  return { width: 18, height: 18 };
}
