export const GRAPH_COLORS = ["#38bdf8", "#f472b6", "#facc15", "#a78bfa", "#fb923c", "#2dd4bf", "#f87171", "#a3e635"];

/** Palette slot for a cluster on the ring. A stride of 3 keeps neighboring clusters far apart in hue. */
export function clusterColor(index: number): string {
  return GRAPH_COLORS[(index * 3) % GRAPH_COLORS.length] ?? GRAPH_COLORS[0];
}

export function colorsByCluster(keys: string[]): Map<string, string> {
  const ordered = [...new Set(keys)].sort((left, right) => {
    if (left === "packages") {
      return 1;
    }
    if (right === "packages") {
      return -1;
    }
    return left.localeCompare(right);
  });
  return new Map(ordered.map((key, index) => [key, clusterColor(index)]));
}
