/** One lightness and chroma, eight hues. The clusters read as a set instead of a rainbow. */
export const GRAPH_COLORS = [
  "oklch(0.80 0.11 230)",
  "oklch(0.78 0.12 350)",
  "oklch(0.84 0.12 90)",
  "oklch(0.76 0.12 290)",
  "oklch(0.79 0.12 50)",
  "oklch(0.82 0.11 170)",
  "oklch(0.74 0.13 20)",
  "oklch(0.84 0.13 130)",
];

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
