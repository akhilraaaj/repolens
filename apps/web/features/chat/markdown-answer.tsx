"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { OpenFile } from "../code/code-viewer";

type Citation = { path: string; start_line: number; end_line: number };

export function MarkdownAnswer({
  text,
  citations,
  onOpen,
}: {
  text: string;
  citations: Citation[];
  onOpen: (file: OpenFile) => void;
}) {
  const linked = text.replace(/\[(\d+)\]/g, "[$1](#cite-$1)");
  return (
    <div className="markdown text-fg/90">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Image URLs come from repository text. Show the alt text and never fetch them.
          img: ({ alt }) => (alt ? <span>{alt}</span> : null),
          a: ({ href, children }) => {
            const match = href?.match(/^#cite-(\d+)$/);
            if (!match) {
              return <span>{children}</span>;
            }
            const citation = citations[Number(match[1]) - 1];
            if (!citation) {
              return <span>{children}</span>;
            }
            return (
              <button
                type="button"
                onClick={() => onOpen({ path: citation.path, start: citation.start_line, end: citation.end_line })}
                className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-brand/15 px-1 align-text-top font-mono text-[10px] text-brand hover:bg-brand/25"
              >
                {match[1]}
              </button>
            );
          },
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}
