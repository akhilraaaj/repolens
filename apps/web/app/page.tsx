import { Binary, Blend, Boxes, FileCode2, GitBranch, Layers, MessageSquareQuote, Network, ScissorsLineDashed } from "lucide-react";
import type { ReactNode } from "react";

import { Logo } from "../components/logo";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiStatus } from "@/features/ingest/api-status";
import { RepoInput } from "@/features/ingest/repo-input";

const PIPELINE = [
  { icon: GitBranch, title: "Fetch", detail: "Public GitHub tarball, pinned to one commit SHA" },
  { icon: FileCode2, title: "Parse", detail: "TypeScript compiler API: symbols, imports, calls" },
  { icon: ScissorsLineDashed, title: "Chunk", detail: "One chunk per function, class, or block" },
  { icon: Binary, title: "Embed", detail: "jina-embeddings-v2-base-code, 768-d, stored in pgvector" },
  { icon: Blend, title: "Retrieve", detail: "Full-text + cosine, merged with reciprocal rank fusion" },
  { icon: MessageSquareQuote, title: "Answer", detail: "Grounded in numbered evidence, citations checked" },
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-canvas">
      <header className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Logo />
        <div className="text-muted-foreground">
          <ApiStatus />
        </div>
      </header>

      <section className="relative mx-auto flex max-w-3xl flex-col items-center px-6 pb-16 pt-20 text-center sm:pt-28">
        <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-line bg-panel px-3 py-1 text-xs text-muted-foreground">
          Open source · local embeddings · no code leaves your machine by default
        </p>
        <h1 className="text-balance text-4xl font-semibold tracking-[-0.03em] sm:text-6xl">
          Understand any repository
          <span className="mt-2 block">in minutes, not days.</span>
        </h1>
        <p className="mt-6 max-w-xl text-pretty text-base leading-7 text-muted-foreground">
          Paste a GitHub repository. RepoLens maps how the files connect, writes a guide, and answers questions with hybrid RAG over pgvector. Every answer cites exact lines, and you
          can open the retrieval pipeline behind it.
        </p>
        <div className="mt-10 w-full max-w-2xl text-left">
          <RepoInput autoFocus />
        </div>
      </section>

      <section aria-labelledby="how-it-works" className="relative mx-auto max-w-6xl px-6 pb-16">
        <h2 id="how-it-works" className="mb-4 text-center text-[11px] font-medium tracking-[0.2em] text-muted-foreground uppercase">
          How it works
        </h2>
        <ol className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {PIPELINE.map((step, index) => (
            <li
              key={step.title}
              className="rounded-xl border border-line bg-panel p-3"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-faint">{String(index + 1).padStart(2, "0")}</span>
                <step.icon size={14} className="text-brand" />
                <span className="text-sm font-medium">{step.title}</span>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{step.detail}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="relative mx-auto grid max-w-6xl gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-3">
        <Feature icon={<Layers size={16} />} title="Overview and guide">
          Stack, entry points, and the modules everything else depends on, read from the files and the import graph. Then a written guide with links to its sources.
        </Feature>
        <Feature icon={<Network size={16} />} title="Architecture map">
          Folders and files colored by where they live. Every edge comes from the parser and is labeled verified, resolved, or unresolved.
        </Feature>
        <Feature icon={<Boxes size={16} />} title="Hybrid RAG on pgvector">
          Keyword and vector search merged with RRF, plus an optional cross-encoder. Open any answer to see each stage&apos;s hits, scores, and timings.
        </Feature>
      </section>

      <footer className="relative mx-auto max-w-6xl px-6 py-12 text-xs text-faint">
        RepoLens never executes repository code. Every analysis is tied to one commit SHA.
      </footer>
    </main>
  );
}

function Feature({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card className="rounded-none bg-background py-0 ring-0 transition-colors hover:bg-panel">
      <CardHeader className="p-6">
        <div className="mb-2 inline-flex size-8 items-center justify-center rounded-lg border bg-card text-brand">{icon}</div>
        <CardTitle className="text-sm">{title}</CardTitle>
        <CardDescription className="text-sm leading-6">{children}</CardDescription>
      </CardHeader>
    </Card>
  );
}
