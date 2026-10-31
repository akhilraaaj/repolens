import { clusterColor } from "../map/colors";
import { dotFill, type Dot } from "../map/clusters";

/**
 * Small drawings of each workspace view for the landing page. The names in them
 * are made up; each shows what the view looks like, not a real repository.
 */

export function OverviewPreview() {
  const rows = [
    ["Framework", "Next.js"],
    ["Language", "TypeScript"],
    ["Data", "SWR"],
  ];
  return (
    <div className="space-y-3 text-[11px]">
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center gap-3">
          <span className="w-16 text-faint">{label}</span>
          <span className="rounded border border-line bg-raised px-1.5 py-0.5 text-fg">{value}</span>
        </div>
      ))}
      <div className="flex h-1 gap-px overflow-hidden rounded-full pt-0">
        <span className="w-[78%]" style={{ background: clusterColor(0) }} />
        <span className="w-[16%]" style={{ background: clusterColor(1) }} />
        <span className="w-[6%]" style={{ background: clusterColor(2) }} />
      </div>
      <div className="flex items-center gap-2 font-mono">
        <span className="rounded bg-raised px-1.5 py-0.5 text-[10px] text-muted-foreground">entry</span>
        <span className="text-fg">src/index.ts</span>
      </div>
    </div>
  );
}

const MINI = [
  { count: 26, x: 70, y: 70, color: 0 },
  { count: 13, x: 200, y: 44, color: 1 },
  { count: 9, x: 190, y: 120, color: 3 },
];
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
const TONES: Dot["tone"][] = ["main", "light", "main", "dark", "other"];

export function MapPreview() {
  return (
    <svg viewBox="0 0 260 160" className="h-full w-full" aria-hidden>
      <path d="M 70 70 Q 130 30 200 44" fill="none" strokeWidth={7} strokeLinecap="round" style={{ stroke: clusterColor(0), strokeOpacity: 0.32 }} />
      <path d="M 70 70 Q 120 120 190 120" fill="none" strokeWidth={4} strokeLinecap="round" style={{ stroke: clusterColor(0), strokeOpacity: 0.32 }} />
      <path d="M 200 44 Q 210 82 190 120" fill="none" strokeWidth={2.5} strokeLinecap="round" style={{ stroke: clusterColor(1), strokeOpacity: 0.32 }} />
      {MINI.map((cluster, index) =>
        Array.from({ length: cluster.count }, (_, member) => {
          const distance = 4.6 * Math.sqrt(member + 0.5);
          return (
            <circle
              key={`${index}-${member}`}
              cx={cluster.x + Math.cos(member * GOLDEN) * distance}
              cy={cluster.y + Math.sin(member * GOLDEN) * distance}
              r={3.6}
              style={{ fill: dotFill(clusterColor(cluster.color), TONES[(member + index) % TONES.length] ?? "main"), stroke: "var(--color-canvas)", strokeWidth: 0.6 }}
            />
          );
        }),
      )}
    </svg>
  );
}

export function GuidePreview() {
  return (
    <div className="space-y-3">
      <p className="text-[12px] font-medium text-fg">How a request is cached</p>
      <div className="space-y-1.5">
        <span className="block h-1.5 w-full rounded-full bg-line-strong" />
        <span className="block h-1.5 w-[92%] rounded-full bg-line-strong" />
        <span className="block h-1.5 w-[64%] rounded-full bg-line-strong" />
      </div>
      <div className="flex flex-wrap gap-1.5 font-mono text-[10px]">
        {["src/cache.ts", "src/hooks/use-swr.ts"].map((path) => (
          <span key={path} className="rounded border border-line bg-raised px-1.5 py-0.5 text-muted-foreground">
            {path}
          </span>
        ))}
      </div>
    </div>
  );
}

export function AskPreview() {
  return (
    <div className="space-y-3 text-[11.5px]">
      <p className="ml-auto w-fit rounded-lg bg-raised px-2.5 py-1.5 text-fg">Where is the cache cleared?</p>
      <p className="leading-5 text-muted-foreground">
        <span className="font-mono text-fg">mutate</span> drops the key from the cache before revalidating
        <span className="mx-1 inline-flex h-4 min-w-4 items-center justify-center rounded bg-brand/15 px-1 align-text-top font-mono text-[10px] text-brand">1</span>
      </p>
      <pre className="overflow-hidden rounded-md border border-line bg-canvas py-1.5 font-mono text-[10.5px] leading-5">
        <span className="block px-2 text-faint">41  const state = cache.get(key)</span>
        <span className="block border-l-2 border-brand bg-brand/10 px-2 text-fg">42  cache.delete(key)</span>
        <span className="block px-2 text-faint">43  return revalidate()</span>
      </pre>
    </div>
  );
}
