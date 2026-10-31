"use client";

import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { api, type Documentation } from "../../lib/api";
import type { OpenFile } from "../code/code-viewer";

type Props = {
  versionId: string;
  onOpen: (file: OpenFile) => void;
};

// The first guide can take a minute when a chat model writes it. The view
// unmounts on every tab switch, so share one request per version instead of
// asking the model again each time the tab is opened. Once it settles, the
// API's stored copy answers the next request.
const pending = new Map<string, Promise<Documentation>>();

function loadDocumentation(versionId: string): Promise<Documentation> {
  let request = pending.get(versionId);
  if (!request) {
    request = api<Documentation>(`/ingestions/${versionId}/documentation`);
    pending.set(versionId, request);
    request.then(
      () => pending.delete(versionId),
      () => pending.delete(versionId),
    );
  }
  return request;
}

export function DocsView({ versionId, onOpen }: Props) {
  const [doc, setDoc] = useState<Documentation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadDocumentation(versionId)
      .then((next) => {
        if (!cancelled) {
          setDoc(next);
          setError(null);
        }
      })
      .catch((exc: Error) => {
        if (!cancelled) {
          setError(exc.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  if (error) {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }
  if (doc === null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-1.5 text-sm text-muted-foreground">
        <span className="flex items-center gap-2">
          <Spinner /> Writing the guide
        </span>
        <span className="text-xs text-faint">With a chat model, the first guide can take a minute.</span>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <article className="mx-auto max-w-2xl px-6 py-10">
        <p className="text-xs font-medium tracking-wide text-muted-foreground">Documentation</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{doc.title}</h1>
        {doc.model ? <p className="mt-2 text-xs text-faint">{doc.model}</p> : null}
        <div className="mt-8 space-y-10">
          {doc.sections.map((section) => (
            <section key={section.id}>
              <h2 className="text-sm font-medium text-fg">{section.heading}</h2>
              <div className="mt-3 space-y-3">
                {section.paragraphs.map((paragraph) => (
                  <p key={paragraph} className="text-sm leading-7 text-muted-foreground">
                    {paragraph}
                  </p>
                ))}
              </div>
              {section.sources.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {section.sources.map((source) => (
                    <button
                      key={`${section.id}-${source.path}`}
                      type="button"
                      onClick={() => onOpen({ path: source.path })}
                      className="rounded-md border border-line bg-panel px-2 py-1 font-mono text-[11px] text-muted-foreground hover:border-brand/40 hover:text-fg"
                    >
                      {source.path}
                    </button>
                  ))}
                </div>
              ) : null}
            </section>
          ))}
        </div>
        <p className="mt-12 border-t border-line pt-4 text-[11px] text-faint">
          {doc.model
            ? `Written by ${doc.model} from the stored files. The repository was not executed.`
            : "Written from the stored README, the package manifest, folder names, and import counts. No language model was used."}
        </p>
      </article>
    </div>
  );
}
