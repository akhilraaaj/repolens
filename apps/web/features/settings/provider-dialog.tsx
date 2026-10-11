"use client";

import { useEffect, useState, type ReactNode } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { api, postJson, type Ingestion, type ModelConfig, type ProviderSettings } from "../../lib/api";

const CHOICES = [
  { id: "ollama", title: "Local", detail: "Ollama on this machine. Source stays here." },
  { id: "openai_compatible", title: "Hosted", detail: "An OpenAI-compatible endpoint. Source is sent only after you save this." },
  { id: "none", title: "None", detail: "Quoted answers from retrieved source, with no model." },
] as const;

type Choice = (typeof CHOICES)[number]["id"];

export function ProviderDialog({
  open,
  current = null,
  record = null,
  onSaved,
  onClose,
}: {
  open: boolean;
  current?: ProviderSettings | null;
  record?: Ingestion | null;
  onSaved: (settings: ProviderSettings) => void;
  onClose?: () => void;
}) {
  const [choice, setChoice] = useState<Choice>(current?.provider ?? "none");
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "http://127.0.0.1:11434");
  const [model, setModel] = useState(current?.model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [config, setConfig] = useState<ModelConfig | null>(null);

  useEffect(() => {
    if (!open || record === null) {
      return;
    }
    api<ModelConfig>("/config")
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [open, record]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = { provider: choice };
      if (choice !== "none") {
        body.base_url = baseUrl.trim();
        body.model = model.trim();
        if (choice === "openai_compatible" && apiKey.trim() !== "") {
          body.api_key = apiKey.trim();
        }
      }
      onSaved(await postJson<ProviderSettings>("/provider", body));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The provider could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} disablePointerDismissal={!onClose} onOpenChange={(next) => (!next ? onClose?.() : undefined)}>
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-lg" showCloseButton={Boolean(onClose)}>
        <DialogHeader>
          <DialogTitle>How should RepoLens answer?</DialogTitle>
          <DialogDescription>
            Retrieval always runs locally on pgvector. This only picks who writes the final sentence. The choice is stored on the server, and an API key is never sent back to the
            browser.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {CHOICES.map((item) => (
            <Button
              key={item.id}
              type="button"
              variant="outline"
              onClick={() => {
                setChoice(item.id);
                if (item.id !== current?.provider) {
                  setBaseUrl(item.id === "ollama" ? "http://127.0.0.1:11434" : "https://api.openai.com/v1");
                }
              }}
              className={cn("h-auto flex-col items-start px-3 py-2.5", choice === item.id && "border-brand/50 bg-brand/10")}
            >
              <span className="text-sm font-medium">{item.title}</span>
              <span className="text-xs font-normal text-muted-foreground">{item.detail}</span>
            </Button>
          ))}
        </div>
        {choice !== "none" ? (
          <div className="space-y-2">
            <Label htmlFor="provider-base-url">Base URL</Label>
            <Input id="provider-base-url" aria-label="Base URL" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="font-mono text-xs" />
            <Label htmlFor="provider-model">Model</Label>
            <Input
              id="provider-model"
              aria-label="Model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder={choice === "ollama" ? "qwen2.5-coder:7b" : "gpt-4.1-mini"}
            />
            {choice === "openai_compatible" ? (
              <>
                <Label htmlFor="provider-api-key">API key</Label>
                <Input
                  id="provider-api-key"
                  aria-label="API key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={current?.has_api_key ? "A key is stored. Leave empty to keep it." : "API key, stored on the server"}
                />
              </>
            ) : null}
          </div>
        ) : null}
        {record ? (
          <section className="rounded-lg border border-line bg-canvas/60 p-3">
            <p className="text-[11px] font-medium tracking-wider text-muted-foreground uppercase">This snapshot</p>
            <dl className="mt-2 grid grid-cols-[130px_1fr] gap-y-1.5 text-xs">
              <Row label="Commit" value={<span className="font-mono">{record.commit_sha.slice(0, 12)}</span>} />
              <Row label="Files · symbols" value={`${record.stored_count.toLocaleString()} · ${(record.symbol_count ?? 0).toLocaleString()}`} />
              <Row label="Relationships" value={`${(record.relationship_count ?? 0).toLocaleString()} (${(record.unresolved_count ?? 0).toLocaleString()} unresolved)`} />
              <Row label="Chunks" value={(record.chunk_count ?? 0).toLocaleString()} />
              <Row
                label="Embeddings"
                value={<Badge variant={record.embedding_status === "completed" ? "brand" : "outline"}>{record.embedding_status ?? "not started"}</Badge>}
              />
              {config ? (
                <>
                  <Row label="Embedding model" value={<span className="font-mono">{config.embedding_model} · {config.embedding_dimensions}d</span>} />
                  <Row label="Reranker" value={config.reranker_enabled ? (config.reranker_model ?? "on") : "off (set REPOLENS_RERANKER)"} />
                </>
              ) : null}
            </dl>
          </section>
        ) : null}
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <Button type="button" disabled={busy || (choice !== "none" && (baseUrl.trim() === "" || model.trim() === ""))} onClick={() => void save()}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 truncate text-fg">{value}</dd>
    </>
  );
}
