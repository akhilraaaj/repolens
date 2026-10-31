"use client";

import { CornerDownLeft, FolderGit2, GitBranch } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { postJson, type Ingestion } from "../../lib/api";
import { clusterColor } from "../map/colors";

export function RepoInput({ autoFocus = false }: { autoFocus?: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [ref, setRef] = useState("");
  const [showRef, setShowRef] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hint = useTypedHint(url === "" && !busy);

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
        <InputGroup className="h-14 rounded-xl border-line-strong bg-panel pr-2 pl-1 transition-colors has-[input:focus]:border-fg/35 has-[input:focus]:bg-raised">
          <InputGroupAddon>
            <FolderGit2 className="text-faint" />
            <InputGroupText className="font-mono text-faint">github.com/</InputGroupText>
          </InputGroupAddon>
          <InputGroupInput
            aria-label="GitHub repository"
            autoFocus={autoFocus}
            className="font-mono text-[14px] text-fg placeholder:text-faint"
            placeholder={hint}
            spellCheck={false}
            autoComplete="off"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            disabled={busy}
          />
          <InputGroupAddon align="inline-end" className="gap-1.5 pr-0">
            <InputGroupButton
              type="button"
              aria-expanded={showRef}
              className="hidden h-8 rounded-md px-2 font-mono text-[11px] text-muted-foreground hover:text-fg sm:inline-flex"
              onClick={() => setShowRef((value) => !value)}
              title="Pick a branch, tag, or commit"
            >
              <GitBranch />
              {ref.trim() || "default"}
            </InputGroupButton>
            <Button type="submit" className="h-9 rounded-lg px-3.5 text-[13px]" disabled={busy || url.trim() === ""}>
              {busy ? <Spinner /> : null}
              {busy ? "Opening" : "Explore"}
              {busy ? null : <CornerDownLeft className="opacity-60" />}
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
      <div className="mt-4 flex flex-wrap items-center gap-2 font-medium">
        <span className="mr-0.5 text-xs text-faint">Try</span>
        {EXAMPLES.map((example, index) => {
          const [owner, name] = example.split("/");
          return (
            <button
              key={example}
              type="button"
              disabled={busy}
              onClick={() => {
                setUrl(example);
                void submit(example);
              }}
              className="inline-flex h-7 items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 font-mono text-[11px] transition-colors hover:border-line-strong hover:bg-raised disabled:opacity-50"
            >
              <span className="size-1.5 rounded-full" style={{ background: clusterColor(index) }} />
              <span className="text-faint">{owner}/</span>
              <span className="text-fg">{name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const EXAMPLES = ["vercel/swr", "pmndrs/zustand", "sindresorhus/ky"];

const RESTING_HINT = "owner/repository";

/**
 * Types the example repositories into the empty field's placeholder, one
 * character at a time, so the field shows what it takes. Stays still when the
 * field has text or the viewer asked for reduced motion.
 */
function useTypedHint(active: boolean): string {
  const [hint, setHint] = useState(RESTING_HINT);
  useEffect(() => {
    if (!active || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    let example = 0;
    let length = 0;
    let deleting = false;
    let pause = 14;
    const timer = window.setInterval(() => {
      if (pause > 0) {
        pause -= 1;
        return;
      }
      const target = EXAMPLES[example] ?? RESTING_HINT;
      length += deleting ? -1 : 1;
      setHint(target.slice(0, Math.max(length, 0)));
      if (!deleting && length >= target.length) {
        deleting = true;
        pause = 22;
      } else if (deleting && length <= 0) {
        deleting = false;
        example = (example + 1) % EXAMPLES.length;
        pause = 6;
      }
    }, 70);
    return () => window.clearInterval(timer);
  }, [active]);
  return active ? hint : RESTING_HINT;
}

export function normalize(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (trimmed.startsWith("https://")) {
    return trimmed;
  }
  const withoutHost = trimmed.replace(/^(http:\/\/)?(www\.)?github\.com\//, "");
  return `https://github.com/${withoutHost}`;
}
