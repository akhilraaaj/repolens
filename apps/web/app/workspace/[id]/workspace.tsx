"use client";

import { FileText, LayoutDashboard, MessageSquare, Network, RefreshCw, Search, Settings2, Sparkles, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { Logo } from "../../../components/logo";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ChatPanel } from "../../../features/chat/chat-panel";
import { CodeViewer, type OpenFile } from "../../../features/code/code-viewer";
import { CommandPalette } from "../../../features/command/command-palette";
import { IndexingStepper } from "../../../features/ingest/indexing-stepper";
import { GRAPH_COLORS } from "../../../features/map/colors";
import { RepoMap } from "../../../features/map/repo-map";
import { BriefView } from "../../../features/brief/brief-view";
import { DocsView } from "../../../features/docs/docs-view";
import { ProviderDialog } from "../../../features/settings/provider-dialog";
import { analysisDone, api, snapshotStored, type FileGraph, type Graph, type Ingestion, type Overview, type ProviderSettings } from "../../../lib/api";
import { cn } from "../../../lib/cn";

type ViewId = "overview" | "guide" | "map" | "ask";

const VIEWS: { id: ViewId; label: string; hint: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", hint: "Stack, entry points, and core modules", icon: LayoutDashboard },
  { id: "guide", label: "Guide", hint: "A written tour of this commit", icon: FileText },
  { id: "map", label: "Map", hint: "Files and the imports between them", icon: Network },
  { id: "ask", label: "Ask", hint: "Questions answered with cited lines", icon: MessageSquare },
];

const EMPTY_GRAPH: Graph = { symbols: [], relationships: [], truncated: false };

export function Workspace({ id, initialView = null }: { id: string; initialView?: string | null }) {
  const [record, setRecord] = useState<Ingestion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<Graph>(EMPTY_GRAPH);
  const [view, setView] = useState<ViewId>(() => VIEWS.find((item) => item.id === initialView)?.id ?? "overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [featureTrace, setFeatureTrace] = useState<string[]>([]);
  const [provider, setProvider] = useState<ProviderSettings | null>(null);
  const [providerOpen, setProviderOpen] = useState(false);
  const [serverChat, setServerChat] = useState(false);
  const [openFile, setOpenFile] = useState<OpenFile | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [highlighted, setHighlighted] = useState<string[]>([]);
  const [fileGraph, setFileGraph] = useState<FileGraph | null>(null);
  const analysisRequested = useRef(false);

  const refresh = useCallback(
    () =>
      api<Ingestion>(`/ingestions/${id}`)
        .then((next) => {
          setRecord(next);
          setError(null);
        })
        .catch((exc: Error) => setError(exc.message)),
    [id],
  );

  const analyze = useCallback(async () => {
    try {
      setRecord(await api<Ingestion>(`/ingestions/${id}/analysis`, { method: "POST" }));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Analysis could not start.");
    }
  }, [id]);

  useEffect(() => {
    void refresh();
    api<ProviderSettings>("/provider")
      .then((settings) => {
        setProvider(settings);
        setProviderOpen(!settings.configured);
      })
      .catch(() => undefined);
    // A model set in the API's environment is not a saved provider, so /provider does not show it.
    api<{ chat_configured: boolean }>("/config")
      .then((config) => setServerChat(config.chat_configured))
      .catch(() => undefined);
  }, [refresh]);

  const indexing = record !== null && (record.status === "running" || record.analysis_status === "running");
  const embedding = record !== null && record.embedding_status === "running";
  const busy = indexing || embedding;

  useEffect(() => {
    if (!busy) {
      return;
    }
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => window.clearInterval(timer);
  }, [busy, refresh]);

  useEffect(() => {
    if (record && snapshotStored(record) && record.analysis_status === "not_started" && !analysisRequested.current) {
      analysisRequested.current = true;
      void analyze();
    }
  }, [record, analyze]);

  const ready = record !== null && analysisDone(record);

  useEffect(() => {
    if (!ready) {
      return;
    }
    api<Graph>(`/ingestions/${id}/graph?limit=500`)
      .then(setGraph)
      .catch((exc: Error) => setError(exc.message));
    api<FileGraph>(`/ingestions/${id}/graph/files`)
      .then(setFileGraph)
      .catch((exc: Error) => setError(exc.message));
    api<Overview>(`/ingestions/${id}/overview`)
      .then((next) => {
        setOverview(next);
        setOverviewError(null);
      })
      .catch((exc: Error) => setOverviewError(exc.message));
  }, [id, ready, record?.symbol_count, record?.relationship_count]);

  const storedPaths = useMemo(
    () => (record?.files ?? []).filter((file) => file.disposition === "stored").map((file) => file.path),
    [record?.files],
  );

  const open = useCallback((file: OpenFile) => setOpenFile(file), []);
  const chatLabel = provider?.provider && provider.provider !== "none" ? provider.model : serverChat ? "Model from server settings" : null;

  // The address follows the open view, so ?view=map can be shared and reopened.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("view") !== view) {
      url.searchParams.set("view", view);
      window.history.replaceState(null, "", url);
    }
  }, [view]);

  // 1 to 4 switch views, unless the key is typed into a field.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) {
        return;
      }
      const next = VIEWS[Number(event.key) - 1];
      if (next) {
        setView(next.id);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (record === null) {
    return (
      <div className="flex flex-1 items-center justify-center">
        {error ? (
          <div className="max-w-md">
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          </div>
        ) : (
          <Spinner />
        )}
      </div>
    );
  }

  return (
    <>
      <TopBar
        record={record}
        indexing={indexing}
        onRebuild={() => void analyze()}
        onPalette={() => setPaletteOpen(true)}
        onSettings={() => setProviderOpen(true)}
        chatLabel={chatLabel}
      />
      {error ? (
        <div className="border-b border-line px-4 py-2">
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </div>
      ) : null}
      {!ready ? (
        <div className="flex flex-1 items-center justify-center px-6">
          <IndexingStepper record={record} />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <Sidebar
            view={view}
            onView={setView}
            cited={highlighted.length}
            record={record}
            overview={overview}
            chatLabel={chatLabel}
            onSettings={() => setProviderOpen(true)}
          />
          <Group orientation="horizontal" className="min-h-0 flex-1">
            <Panel id="main" minSize={340} className="relative flex min-h-0 flex-col">
              {view !== "ask" ? (
                <div key={view} className="min-h-0 flex-1 animate-in fade-in slide-in-from-bottom-1 duration-200">
                  {view === "overview" ? (
                    <BriefView record={record} overview={overview} error={overviewError} onOpen={open} onShowMap={() => setView("map")} />
                  ) : null}
                  {view === "guide" ? <DocsView versionId={id} onOpen={open} /> : null}
                  {view === "map" ? (
                    <RepoMap graph={fileGraph} cited={highlighted} trace={featureTrace} focusPath={openFile?.path ?? null} onOpen={open} />
                  ) : null}
                </div>
              ) : null}
              <div className={cn("min-h-0 flex-1", view !== "ask" && "hidden")}>
                <ChatPanel
                  versionId={id}
                  ready={ready}
                  pendingQuestion={pendingQuestion}
                  onQuestionConsumed={() => setPendingQuestion(null)}
                  onOpen={open}
                  onCitations={setHighlighted}
                  onTrace={setFeatureTrace}
                />
              </div>
            </Panel>
            {openFile ? (
              <>
                <Separator className="w-px bg-line transition-colors hover:bg-brand data-[separator=active]:bg-brand" />
                <Panel id="source" defaultSize="42" minSize={300} maxSize="70" className="flex min-h-0 flex-col border-l border-line bg-panel">
                  <CodeViewer versionId={id} file={openFile} graph={fileGraph} onOpen={open} onClose={() => setOpenFile(null)} />
                </Panel>
              </>
            ) : null}
          </Group>
        </div>
      )}
      {providerOpen ? (
        <ProviderDialog
          open
          current={provider}
          record={ready ? record : null}
          onSaved={(settings) => {
            setProvider(settings);
            setProviderOpen(false);
          }}
          onClose={provider?.configured ? () => setProviderOpen(false) : undefined}
        />
      ) : null}
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        files={storedPaths}
        symbols={graph.symbols}
        views={VIEWS}
        onFile={(path) => open({ path })}
        onSymbol={(symbol) => open({ path: symbol.path, start: symbol.start_line, end: symbol.end_line })}
        onView={(next) => setView(next as ViewId)}
        onAsk={(question) => {
          setView("ask");
          setPendingQuestion(question);
        }}
      />
    </>
  );
}

function Sidebar({
  view,
  onView,
  cited,
  record,
  overview,
  chatLabel,
  onSettings,
}: {
  view: ViewId;
  onView: (view: ViewId) => void;
  cited: number;
  record: Ingestion;
  overview: Overview | null;
  chatLabel: string | null;
  onSettings: () => void;
}) {
  const languages = overview?.summary.languages ?? [];
  const search =
    record.embedding_status === "running"
      ? { tone: "bg-warn animate-pulse", text: record.progress_total ? `Indexing ${record.progress_completed ?? 0}/${record.progress_total}` : "Indexing" }
      : record.embedding_status === "failed"
        ? { tone: "bg-danger", text: "Vector search off" }
        : { tone: "bg-brand", text: "Search ready" };
  return (
    <aside className="flex w-16 shrink-0 flex-col border-r border-line bg-canvas lg:w-60">
      <nav role="tablist" aria-label="Views" aria-orientation="vertical" className="flex flex-col gap-0.5 p-2 pt-3 lg:px-3">
        <p className="hidden px-2.5 pb-2 text-[10px] font-medium tracking-[0.16em] text-faint uppercase lg:block">Explore</p>
        {VIEWS.map((item, index) => {
          const active = view === item.id;
          return (
            <Tooltip key={item.id}>
              <TooltipTrigger
                render={
                  <button
                    type="button"
                    role="tab"
                    aria-selected={active}
                    aria-label={item.label}
                    onClick={() => onView(item.id)}
                    className={cn(
                      "group relative flex h-10 items-center justify-center gap-3 rounded-lg px-2.5 text-[13px] transition-colors lg:h-9 lg:justify-start",
                      active ? "bg-hover text-fg" : "text-muted-foreground hover:bg-hover/50 hover:text-fg",
                    )}
                  />
                }
              >
                <item.icon size={16} className={cn("shrink-0 transition-colors", active ? "text-brand" : "text-faint group-hover:text-muted-foreground")} />
                <span className="hidden lg:inline">{item.label}</span>
                {item.id === "ask" && cited > 0 ? <span className="absolute top-2 right-2 size-1.5 rounded-full bg-brand lg:static lg:ml-1" /> : null}
                <Kbd className="ml-auto hidden lg:inline-flex">{index + 1}</Kbd>
              </TooltipTrigger>
              <TooltipContent side="right">{item.hint}</TooltipContent>
            </Tooltip>
          );
        })}
      </nav>

      <div className="mt-auto hidden space-y-2 p-3 lg:block">
        <div className="rounded-xl border border-line bg-panel/60 p-3">
          <p className="text-[10px] font-medium tracking-[0.16em] text-faint uppercase">This commit</p>
          <p className="mt-2 truncate text-[13px] font-medium text-fg">
            {record.owner}/{record.name}
          </p>
          <p className="font-mono text-[11px] text-faint">{record.commit_sha.slice(0, 12)}</p>
          {languages.length > 0 ? (
            <div className="mt-3 flex h-1 gap-px overflow-hidden rounded-full bg-raised" title={languages.map((item) => `${item.language} ${(item.share * 100).toFixed(0)}%`).join(" · ")}>
              {languages.map((item, index) => (
                <span key={item.language} style={{ width: `${item.share * 100}%`, background: GRAPH_COLORS[index % GRAPH_COLORS.length] }} />
              ))}
            </div>
          ) : null}
          <dl className="mt-3 grid grid-cols-3 gap-2">
            <Stat label="files" value={record.stored_count} />
            <Stat label="symbols" value={record.symbol_count ?? 0} />
            <Stat label="links" value={record.relationship_count ?? 0} />
          </dl>
          <p className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground" title={record.embedding_error ?? undefined}>
            <span className={cn("size-1.5 rounded-full", search.tone)} />
            {search.text}
          </p>
        </div>
        <button
          type="button"
          onClick={onSettings}
          className="flex h-9 w-full items-center gap-2 rounded-lg border border-line px-2.5 text-left text-xs text-muted-foreground transition-colors hover:border-line-strong hover:text-fg"
        >
          <Sparkles size={13} className={chatLabel ? "text-brand" : "text-faint"} />
          <span className="min-w-0 flex-1 truncate">{chatLabel ?? "No chat model"}</span>
          <Settings2 size={13} className="shrink-0 text-faint" />
        </button>
      </div>
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dd className="font-mono text-[13px] text-fg tabular-nums">{compact(value)}</dd>
      <dt className="text-[10px] text-faint">{label}</dt>
    </div>
  );
}

function compact(value: number): string {
  return value >= 10_000 ? `${Math.round(value / 1000)}k` : value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
}

function TopBar({
  record,
  indexing,
  chatLabel,
  onRebuild,
  onPalette,
  onSettings,
}: {
  record: Ingestion;
  indexing: boolean;
  chatLabel: string | null;
  onRebuild: () => void;
  onPalette: () => void;
  onSettings: () => void;
}) {
  const embedding =
    record.embedding_status === "running"
      ? record.phase === "embedding" && record.progress_total
        ? `embedding ${record.progress_completed ?? 0}/${record.progress_total}`
        : "embedding"
      : null;
  return (
    <header className="relative z-10 flex h-12 shrink-0 items-center gap-3 border-b border-line bg-canvas/80 px-4 backdrop-blur">
      <Logo />
      <span className="text-faint">/</span>
      <a
        href={record.canonical_url ?? `https://github.com/${record.owner}/${record.name}`}
        target="_blank"
        rel="noreferrer"
        className="truncate text-sm font-medium hover:underline"
      >
        {record.owner}/{record.name}
      </a>
      <Badge variant="outline" className="font-mono">{record.commit_sha.slice(0, 7)}</Badge>
      {embedding ? (
        <span className="hidden items-center gap-1.5 text-xs text-muted-foreground md:inline-flex">
          <Spinner className="size-3" /> {embedding}
        </span>
      ) : record.embedding_status === "failed" ? (
        <span className="hidden text-xs text-muted-foreground md:inline" title={record.embedding_error ?? undefined}>
          embeddings stopped
        </span>
      ) : null}
      <div className="ml-auto flex items-center gap-2">
        <Button type="button" variant="outline" onClick={onPalette} className="hidden w-64 justify-start bg-panel/60 px-2.5 text-xs text-muted-foreground md:inline-flex">
          <Search />
          Jump to file, symbol, or ask
          <span className="ml-auto flex gap-0.5">
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </span>
        </Button>
        <Button type="button" variant="ghost" size="icon" onClick={onSettings} title={chatLabel ? `Answer model: ${chatLabel}` : "Answer model and snapshot details"}>
          <Settings2 />
        </Button>
        {snapshotStored(record) ? (
          <Button type="button" variant="ghost" size="icon" onClick={onRebuild} disabled={indexing || embedding !== null} title="Rebuild the graph and embeddings for this commit">
            <RefreshCw className={indexing ? "animate-spin" : undefined} />
          </Button>
        ) : null}
      </div>
    </header>
  );
}
