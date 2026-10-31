import Link from "next/link";

import { clusterColor } from "../features/map/colors";

/** Three folders and the imports between them, the Map view in miniature. */
export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <rect x="0.5" y="0.5" width="23" height="23" rx="7" fill="var(--color-raised)" stroke="var(--color-line-strong)" />
      <path d="M8 9 L16 8 M8 9 L12 16.5 M16 8 L12 16.5" stroke="var(--color-muted-foreground)" strokeOpacity="0.45" strokeWidth="1.2" strokeLinecap="round" />
      <circle cx="8" cy="9" r="2.6" style={{ fill: clusterColor(0) }} />
      <circle cx="16" cy="8" r="2" style={{ fill: clusterColor(1) }} />
      <circle cx="12" cy="16.5" r="2.2" style={{ fill: clusterColor(2) }} />
    </svg>
  );
}

export function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 text-[14px] font-semibold tracking-wide text-fg">
      <LogoMark />
      RepoLens
    </Link>
  );
}
