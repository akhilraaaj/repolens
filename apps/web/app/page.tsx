import { ArrowRight, Check } from "lucide-react";
import type { ReactNode } from "react";

import { Logo } from "../components/logo";
import { ApiStatus } from "@/features/ingest/api-status";
import { RepoInput } from "@/features/ingest/repo-input";
import { AskPreview, GuidePreview, MapPreview, OverviewPreview } from "@/features/landing/view-previews";
import { ClusterArt } from "@/features/map/cluster-art";
import { clusterColor } from "@/features/map/colors";

const PROMISES = ["Runs on your machine", "Never executes the repo", "Any model, or none"];

const STEPS = [
  { title: "Fetch", detail: "Download the archive for one commit, within size and file limits.", output: "commit sha" },
  { title: "Parse", detail: "Read imports and declarations with the TypeScript compiler.", output: "symbols, links" },
  { title: "Chunk", detail: "Split source into functions, classes, and blocks.", output: "chunks" },
  { title: "Embed", detail: "Turn each chunk into a vector with a local code model.", output: "768-d, pgvector" },
  { title: "Retrieve", detail: "Run keyword and vector search, then fuse the rankings.", output: "RRF, k = 60" },
  { title: "Answer", detail: "Keep only the paragraphs that cite retrieved lines.", output: "[1] [2] [3]" },
];

const VIEWS: Array<{ title: string; body: string; preview: ReactNode }> = [
  {
    title: "Overview",
    body: "The stack, the entry points, and the modules the rest of the code leans on, read from the files and the import graph.",
    preview: <OverviewPreview />,
  },
  {
    title: "Map",
    body: "One dot per file and one cluster per folder. Bands grow with the imports between folders. Covers TypeScript and JavaScript.",
    preview: <MapPreview />,
  },
  {
    title: "Guide",
    body: "A short written tour of the commit, with a link to every file it drew from.",
    preview: <GuidePreview />,
  },
  {
    title: "Ask",
    body: "Answers built from retrieved source. A citation opens the exact lines, and the pipeline shows why they ranked.",
    preview: <AskPreview />,
  },
];

const MODELS = [
  {
    title: "No model",
    body: "Overview, map, and search work fully. Ask quotes the matching lines instead of writing prose.",
    data: "Nothing leaves your machine",
    color: "var(--color-faint)",
  },
  {
    title: "Local, with Ollama",
    body: "Written answers and guides from a model on your own hardware. Compose can start Ollama for you.",
    data: "Source stays on your machine",
    color: clusterColor(0),
  },
  {
    title: "Hosted, OpenAI-compatible",
    body: "OpenAI, OpenRouter, or any compatible endpoint. Usually the best answers. The key stays on the server.",
    data: "Retrieved excerpts go to the provider",
    color: clusterColor(1),
  },
];

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-canvas">
      <header className="relative z-10 mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
        <Logo />
        <nav className="flex items-center gap-6 text-xs text-muted-foreground tracking-wide font-medium">
          <a href="#features" className="hidden transition-colors hover:text-fg sm:inline">
            Views
          </a>
          <a href="#how-it-works" className="hidden transition-colors hover:text-fg sm:inline">
            How it works
          </a>
          <a href="#models" className="hidden transition-colors hover:text-fg sm:inline">
            Models
          </a>
          <ApiStatus />
        </nav>
      </header>

      <section className="relative mx-auto grid max-w-6xl items-center gap-12 px-6 pt-14 pb-8 sm:pt-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.95fr)] lg:gap-8 lg:pt-28">
        <div className="relative z-10">
          <a
            href="#how-it-works"
            className="group inline-flex items-center gap-2.5 rounded-full border border-line bg-panel py-1 pr-3 pl-1 text-[12.5px] text-muted-foreground font-medium transition-colors hover:border-line-strong hover:text-fg"
          >
            <span className="inline-flex items-center gap-1.5 rounded-full bg-raised px-2 py-0.5 font-mono text-[10.5px] text-fg">
              <span className="size-1.5 rounded-full bg-brand" />
              Open source
            </span>
            For your first hour in a new codebase
            <ArrowRight size={13} className="text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
          </a>
          <h1 className="mt-5 text-[2.75rem] leading-[1.02] font-semibold tracking-[-0.045em] text-balance text-fg sm:text-[4.25rem]">
            See a codebase{" "}
            <span className="block text-muted-foreground">before you read it</span>
          </h1>
          <p className="mt-6 max-w-[30rem] text-[15px] leading-7 text-pretty text-muted-foreground font-medium tracking-wide">
            Drop in a GitHub repo. RepoLens draws how its folders lean on each other, writes you a guide, and answers questions with the{" "}
            <span className="text-fg">exact lines as proof</span>.
          </p>
          <div className="mt-9 max-w-xl">
            <RepoInput autoFocus />
          </div>
          <ul className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-[12px] text-faint">
            {PROMISES.map((promise) => (
              <li key={promise} className="inline-flex items-center gap-1.5 font-medium">
                <Check size={12} className="text-brand" />
                {promise}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative mx-auto w-full max-w-[560px]">
          <div className="relative">
            <ClusterArt />
          </div>
        </div>
      </section>

      <section id="features" aria-labelledby="features-title" className="relative mx-auto max-w-6xl scroll-mt-16 px-6 pt-32">
        <SectionHeading id="features-title" eyebrow="Four views" title="One commit, read four ways.">
          Start with the overview, follow the map into the folders that matter, read the guide, then ask about what is left.
        </SectionHeading>
        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {VIEWS.map((view) => (
            <article key={view.title} className="overflow-hidden rounded-xl border border-line bg-panel/40">
              <div className="flex h-48 items-center justify-center border-b border-line bg-canvas px-8 py-6">
                <div className="w-full max-w-[280px]">{view.preview}</div>
              </div>
              <div className="p-6">
                <h3 className="text-sm font-medium text-fg">{view.title}</h3>
                <p className="mt-1.5 max-w-md text-[13px] leading-6 text-muted-foreground">{view.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section id="how-it-works" aria-labelledby="how-it-works-title" className="relative mx-auto grid max-w-6xl scroll-mt-16 gap-10 px-6 pt-32 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
        <SectionHeading id="how-it-works-title" eyebrow="How it works" title="From a URL to a cited answer.">
          Every step runs on your machine against one pinned commit. The code is read and parsed, never run.
        </SectionHeading>
        <ol className="border-t border-line">
          {STEPS.map((step, index) => (
            <li key={step.title} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-4 border-b border-line py-4 sm:grid-cols-[2.5rem_7rem_minmax(0,1fr)_auto] sm:items-baseline">
              <span className="font-mono text-[11px] text-faint">{String(index + 1).padStart(2, "0")}</span>
              <span className="text-sm font-medium text-fg">{step.title}</span>
              <span className="col-start-2 text-[13px] text-muted-foreground sm:col-start-auto">{step.detail}</span>
              <span className="col-start-2 mt-1 font-mono text-[11px] text-faint sm:col-start-auto sm:mt-0">{step.output}</span>
            </li>
          ))}
        </ol>
      </section>

      <section id="models" aria-labelledby="models-title" className="relative mx-auto max-w-6xl scroll-mt-16 px-6 pt-32">
        <SectionHeading id="models-title" eyebrow="Models" title="Bring your own model, or none.">
          Search, the map, and the overview never need one. A chat model only writes the prose, and every paragraph still has to cite retrieved lines.
        </SectionHeading>
        <div className="mt-12 grid overflow-hidden rounded-xl border border-line sm:grid-cols-3">
          {MODELS.map((model, index) => (
            <div key={model.title} className={index > 0 ? "border-t border-line p-6 sm:border-t-0 sm:border-l" : "p-6"}>
              <span className="inline-block size-2 rounded-full" style={{ background: model.color }} />
              <h3 className="mt-4 text-sm font-medium text-fg">{model.title}</h3>
              <p className="mt-1.5 text-[13px] leading-6 text-muted-foreground">{model.body}</p>
              <p className="mt-4 font-mono text-[11px] text-faint">{model.data}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="relative mx-auto mt-32 max-w-6xl px-6">
        <div className="flex flex-col gap-4 border-t border-line py-8 text-xs text-faint sm:flex-row sm:items-center sm:justify-between">
          <Logo />
          <span>Repository code is never executed. Every analysis is pinned to one commit. MIT licensed.</span>
        </div>
      </footer>
    </main>
  );
}

function SectionHeading({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: string }) {
  return (
    <div className="max-w-xl">
      <p className="font-mono text-[11px] text-faint">{eyebrow}</p>
      <h2 id={id} className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-fg sm:text-[2rem] sm:leading-tight">
        {title}
      </h2>
      <p className="mt-4 text-[14px] leading-7 text-muted-foreground">{children}</p>
    </div>
  );
}
