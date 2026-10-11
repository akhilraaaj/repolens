"use client";

import { ArrowRight, GitBranch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { postJson, type Ingestion } from "../../lib/api";

export function RepoInput({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [showRef, setShowRef] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(value: string, event?: FormEvent) {
    event?.preventDefault();
    if (value.trim() === "") {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const record = await postJson<Ingestion>("/ingestions", {
        url: normalize(value),
        ref: ref.trim() === "" ? null : ref.trim(),
      });
      router.push(`/workspace/${record.id}`);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "The repository could not be opened.");
      setBusy(false);
    }
  }

  return (
    <div className="w-full">
      <form onSubmit={(event) => void submit(url, event)}>
        <InputGroup className="h-14 rounded-xl bg-card pr-2">
          <InputGroupAddon>
            <InputGroupText className="font-mono">github.com/</InputGroupText>
          </InputGroupAddon>
          <InputGroupInput
            aria-label="GitHub repository"
            autoFocus={autoFocus}
            className="font-mono"
            placeholder="owner/repository"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            disabled={busy}
          />
          <InputGroupAddon align="inline-end" className="gap-2 pr-0">
            <InputGroupButton type="button" className="hidden sm:inline-flex" onClick={() => setShowRef((value) => !value)}>
              <GitBranch />
              {ref.trim() || "default branch"}
            </InputGroupButton>
            <Button type="submit" size="lg" disabled={busy || url.trim() === ""}>
              {busy ? <Spinner /> : null}
              {busy ? "Opening" : "Explore"}
              {busy ? null : <ArrowRight />}
            </Button>
          </InputGroupAddon>
        </InputGroup>
      </form>
      {showRef ? (
        <Input
          aria-label="Branch, tag, or commit"
          className="mt-2 font-mono text-xs"
          placeholder="Branch, tag, or commit. Leave empty for the default branch."
          value={ref}
          onChange={(event) => setRef(event.target.value)}
        />
      ) : null}
      {error ? (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>Try</span>
        {EXAMPLES.map((example) => (
          <Button
            key={example}
            type="button"
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              setUrl(example);
              void submit(example);
            }}
            className="font-mono"
          >
            {example}
          </Button>
        ))}
      </div>
    </div>
  );
}

const EXAMPLES = ["total-typescript/ts-reset", "pmndrs/zustand", "sindresorhus/ky", "vercel/swr"];

export function normalize(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (trimmed.startsWith("https://")) {
    return trimmed;
  }
  const withoutHost = trimmed.replace(/^(http:\/\/)?(www\.)?github\.com\//, "");
  return `https://github.com/${withoutHost}`;
}
