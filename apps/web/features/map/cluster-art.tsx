import { clusterColor } from "./colors";
import { dotFill, type Dot } from "./clusters";

/**
 * The Orbs view drawn for the landing page: one dot per file, one blob per
 * folder, and a band per pair of folders that import each other. The folders
 * are made up; the picture shows the shape of the view, not a real repository.
 */
const CLUSTERS = [
  { label: "core", count: 62, x: 300, y: 262 },
  { label: "hooks", count: 30, x: 150, y: 138 },
  { label: "cache", count: 17, x: 452, y: 120 },
  { label: "utils", count: 38, x: 124, y: 392 },
  { label: "server", count: 26, x: 470, y: 372 },
  { label: "types", count: 9, x: 312, y: 470 },
  { label: "tests", count: 21, x: 318, y: 70 },
];

const LINKS: Array<[number, number, number]> = [
  [0, 1, 14],
  [0, 3, 10],
  [0, 2, 6],
  [0, 4, 9],
  [1, 2, 3],
  [3, 4, 3],
  [5, 0, 5],
  [6, 0, 7],
  [6, 1, 3],
];

const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const TONES: Dot["tone"][] = ["main", "main", "light", "dark", "main", "other", "light", "main"];

const placed = CLUSTERS.map((cluster, index) => {
  const color = clusterColor(index);
  const dots = Array.from({ length: cluster.count }, (_, member) => {
    const distance = 5.6 * Math.sqrt(member + 0.5);
    const theta = member * GOLDEN;
    return {
      x: round(cluster.x + Math.cos(theta) * distance),
      y: round(cluster.y + Math.sin(theta) * distance),
      tone: TONES[(member * 7 + index) % TONES.length] ?? "main",
    };
  });
  return { ...cluster, color, dots, radius: 5.6 * Math.sqrt(cluster.count) + 6 };
});

function round(value: number): number {
  return Math.round(value * 10) / 10;
}

function band(from: (typeof placed)[number], to: (typeof placed)[number]): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const qx = round((from.x + to.x) / 2 - dy * 0.14);
  const qy = round((from.y + to.y) / 2 + dx * 0.14);
  return `M ${from.x} ${from.y} Q ${qx} ${qy} ${to.x} ${to.y}`;
}

export function ClusterArt() {
  return (
    <svg viewBox="40 20 520 500" className="h-auto w-full overflow-visible" aria-hidden>

      {LINKS.map(([from, to, weight]) => {
        const source = placed[from];
        const target = placed[to];
        if (!source || !target) {
          return null;
        }
        const path = band(source, target);
        const width = 1.6 + Math.log2(weight + 1) * 1.9;
        return (
          <g key={`${from}-${to}`}>
            <path d={path} fill="none" stroke={source.color} strokeOpacity={0.3} strokeWidth={width} strokeLinecap="round" />
            {weight >= 7 ? (
              <path d={path} fill="none" stroke="white" strokeOpacity={0.5} strokeWidth={1.2} strokeLinecap="round" className="edge-flow" />
            ) : null}
          </g>
        );
      })}

      {placed.map((cluster, index) => (
        <g key={cluster.label} className="art-float" style={{ animationDelay: `${index * -1.3}s` }}>
          {cluster.dots.map((dot, member) => (
            <circle
              key={member}
              cx={dot.x}
              cy={dot.y}
              r={4.4}
              style={{ fill: dotFill(cluster.color, dot.tone), stroke: "var(--color-canvas)", strokeWidth: 0.7, strokeOpacity: 0.55 }}
            />
          ))}
          <g transform={`translate(${cluster.x} ${cluster.y - cluster.radius - 12})`}>
            <text textAnchor="middle" x={0} y={0} fontSize={12.5} className="font-mono">
              <tspan fontSize={10} style={{ fill: cluster.color }}>
                ●
              </tspan>
              <tspan dx={5} className="fill-fg" fontWeight={600}>
                {cluster.label}
              </tspan>
              <tspan dx={6} className="fill-faint">
                {cluster.count}
              </tspan>
            </text>
          </g>
        </g>
      ))}
    </svg>
  );
}
