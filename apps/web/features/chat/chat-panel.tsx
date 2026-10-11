"use client";

import { ArrowUp, Plus, Sparkles, Workflow } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { apiBaseUrl } from "../../lib/api-base";
import { messageFrom, type Pipeline } from "../../lib/api";
import type { OpenFile } from "../code/code-viewer";
import { PipelineInspector } from "../rag/pipeline-inspector";
import { MarkdownAnswer } from "./markdown-answer";

type Citation = { path: string; start_line: number; end_line: number; snippet: string };
type ToolStep = { name: string; summary: string; paths?: string[] };

type Message =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      citations: Citation[];
      abstained: boolean;
      pending: boolean;
      status?: string;
      error?: string;
      suggestions?: string[];
      pipeline?: Pipeline;
      tools?: ToolStep[];
      model?: string | null;
    };

const SUGGESTIONS = ["What does this repository do?", "Where does the program start?", "How is configuration loaded?", "How are errors handled?"];

export function ChatPanel({
  versionId,
  ready,
  pendingQuestion,
  onQuestionConsumed,
  onOpen,
  onCitations,
  onTrace,
}: {
  versionId: string;
  ready: boolean;
  pendingQuestion: string | null;
  onQuestionConsumed: () => void;
  onOpen: (file: OpenFile) => void;
  onCitations: (paths: string[]) => void;
  onTrace: (paths: string[]) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [inspectorFor, setInspectorFor] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (pendingQuestion && ready && !busy) {
      onQuestionConsumed();
      void ask(pendingQuestion);
    }
    // ask is stable enough for this one-shot handoff from the command palette.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingQuestion, ready]);

  async function ask(question: string) {
    const text = question.trim();
    if (text === "" || busy) {
      return;
    }
    setBusy(true);
    setDraft("");
    setMessages((current) => [
      ...current,
      { role: "user", text },
      { role: "assistant", text: "", citations: [], abstained: false, pending: true, status: "Retrieving evidence" },
    ]);
    try {
      const response = await fetch(`${apiBaseUrl()}/ingestions/${versionId}/questions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: text, thread_id: threadId }),
      });
      if (!response.ok || response.body === null) {
        let body: unknown = null;
        try {
          body = await response.json();
        } catch {
          body = null;
        }
        throw new Error(messageFrom(body, response.status));
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let answer = "";
      for (;;) {
        const step = await reader.read();
        if (step.done) {
          break;
        }
        buffer += decoder.decode(step.value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const parsed = parseEvent(block);
          if (parsed === null) {
            continue;
          }
          if (parsed.event === "token") {
            answer += String(parsed.data.text ?? "");
            patchLast({ text: answer, pending: true });
          } else if (parsed.event === "status") {
            patchLast({ status: String(parsed.data.text ?? ""), pending: true });
          } else if (parsed.event === "retrieval") {
            patchLast({ pipeline: parsed.data as Pipeline, pending: true });
          } else if (parsed.event === "tool") {
            const tool = parsed.data as ToolStep;
            setMessages((current) => {
              const last = current[current.length - 1];
              if (last?.role !== "assistant") {
                return current;
              }
              return [...current.slice(0, -1), { ...last, tools: [...(last.tools ?? []), tool] }];
            });
          } else if (parsed.event === "done") {
            const citations = (parsed.data.citations as Citation[]) ?? [];
            setThreadId(typeof parsed.data.thread_id === "string" ? parsed.data.thread_id : threadId);
            replaceLast({
              role: "assistant",
              text: String(parsed.data.answer ?? answer),
              citations,
              abstained: Boolean(parsed.data.abstained),
              pending: false,
              suggestions: (parsed.data.suggestions as string[]) ?? [],
              pipeline: (parsed.data.pipeline as Pipeline | null) ?? undefined,
              tools: (parsed.data.tools as ToolStep[]) ?? [],
              model: (parsed.data.model as string | null) ?? null,
            });
            onCitations(citations.map((citation) => citation.path));
            onTrace((parsed.data.trace as string[]) ?? []);
          } else if (parsed.event === "error") {
            throw new Error(String(parsed.data.message ?? "The question failed."));
          }
        }
      }
    } catch (exc) {
      replaceLast({
        role: "assistant",
        text: "",
        citations: [],
        abstained: true,
        pending: false,
        error: exc instanceof Error ? exc.message : "The question failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  function patchLast(patch: Partial<Extract<Message, { role: "assistant" }>>) {
    setMessages((current) => {
      const last = current[current.length - 1];
      if (last?.role !== "assistant") {
        return current;
      }
      return [...current.slice(0, -1), { ...last, ...patch }];
    });
  }

  function replaceLast(message: Message) {
    setMessages((current) => [...current.slice(0, -1), message]);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8">
          {messages.length === 0 ? (
            <div className="pt-10 text-center">
              <div className="mx-auto mb-4 inline-flex size-11 items-center justify-center rounded-xl border border-line bg-panel text-brand">
                <Sparkles size={18} />
              </div>
              <h2 className="text-xl font-semibold tracking-tight">Ask about this commit</h2>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                Hybrid retrieval over pgvector and PostgreSQL full-text search finds the evidence. Every answer cites exact lines, and you can open the pipeline that produced it.
              </p>
              <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    disabled={!ready}
                    onClick={() => void ask(suggestion)}
                    className="rounded-xl border border-line bg-panel/70 px-3 py-2.5 text-left text-sm text-muted-foreground transition-colors hover:border-brand/30 hover:text-fg disabled:opacity-50"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) =>
              message.role === "user" ? (
                <div key={index} className="flex justify-end">
                  <p className="max-w-[85%] rounded-2xl rounded-br-sm border border-line bg-raised px-4 py-2 text-sm text-fg">{message.text}</p>
                </div>
              ) : (
                <div key={index} className="text-sm leading-6">
                  {message.pending && message.text === "" ? (
                    <div className="space-y-3">
                      <p className="flex items-center gap-2 text-muted-foreground">
                        <Spinner /> {message.status ?? "Retrieving evidence"}
                      </p>
                      {message.pipeline ? <PipelineInspector pipeline={message.pipeline} citations={[]} pending onOpen={onOpen} /> : null}
                    </div>
                  ) : message.error ? (
                    <p className="text-danger">{message.error}</p>
                  ) : (
                    <>
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        {message.model ? <span className="text-[11px] text-faint">{message.model}</span> : null}
                        {message.abstained ? <Badge variant="warn">insufficient evidence</Badge> : null}
                      </div>
                      {message.tools && message.tools.length > 0 ? (
                        <ul className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
                          {message.tools.map((tool, toolIndex) => (
                            <li key={`${tool.name}-${toolIndex}`} className="font-mono text-[10px] text-faint">
                              {tool.name} · {tool.summary}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <MarkdownAnswer text={message.text} citations={message.citations} onOpen={onOpen} />
                      {message.pending ? <Spinner className="mt-2" /> : null}
                      {message.citations.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {message.citations.map((citation, number) => (
                            <button
                              key={`${citation.path}-${citation.start_line}`}
                              type="button"
                              onClick={() => onOpen({ path: citation.path, start: citation.start_line, end: citation.end_line })}
                              className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-line bg-panel px-2 py-1 font-mono text-[11px] text-muted-foreground hover:border-brand/40 hover:text-fg"
                            >
                              <span className="text-brand">{number + 1}</span>
                              <span className="truncate">
                                {citation.path}:{citation.start_line}
                              </span>
                            </button>
                          ))}
                        </div>
                      ) : null}
                      {!message.pending && message.pipeline ? (
                        <button
                          type="button"
                          aria-expanded={inspectorFor === index}
                          onClick={() => setInspectorFor(inspectorFor === index ? null : index)}
                          className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-line bg-panel/60 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-brand/30 hover:text-fg"
                        >
                          <Workflow size={12} className="text-brand" />
                          {inspectorFor === index ? "Hide the RAG pipeline" : "How this answer was built"}
                        </button>
                      ) : null}
                      {inspectorFor === index && message.pipeline ? (
                        <div className="mt-2">
                          <PipelineInspector pipeline={message.pipeline} citations={message.citations} pending={false} onOpen={onOpen} />
                        </div>
                      ) : null}
                      {!message.pending && message.suggestions && message.suggestions.length > 0 ? (
                        <div className="mt-3 flex flex-wrap gap-1.5">
                          {message.suggestions.map((suggestion) => (
                            <button
                              key={suggestion}
                              type="button"
                              onClick={() => void ask(suggestion)}
                              className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted-foreground hover:border-line-strong hover:text-fg"
                            >
                              {suggestion}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              ),
            )
          )}
        </div>
      </div>
      <form onSubmit={submit} className="shrink-0 px-6 pb-5">
        <div className="mx-auto w-full max-w-3xl">
          <div className="flex items-end gap-2 rounded-xl border border-line bg-panel p-2 focus-within:border-line-strong">
            <Textarea
              aria-label="Question"
              rows={1}
              value={draft}
              disabled={!ready}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
              placeholder={ready ? "Ask how something works, where it lives, or what uses it" : "Waiting for analysis"}
              className="max-h-36 min-h-7 flex-1 resize-none border-0 bg-transparent px-1.5 py-1 shadow-none focus-visible:ring-0"
            />
            {messages.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="New chat"
                title="New chat"
                onClick={() => {
                  setThreadId(null);
                  setMessages([]);
                  setInspectorFor(null);
                  onTrace([]);
                  onCitations([]);
                }}
                className="text-muted-foreground"
              >
                <Plus />
              </Button>
            ) : null}
            <Button type="submit" size="icon-sm" aria-label="Send" disabled={!ready || busy || draft.trim() === ""}>
              <ArrowUp />
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}

function parseEvent(block: string): { event: string; data: Record<string, unknown> } | null {
  const event = block.split("\n").find((line) => line.startsWith("event: "))?.slice(7);
  const data = block.split("\n").find((line) => line.startsWith("data: "))?.slice(6);
  if (!event || !data) {
    return null;
  }
  try {
    return { event, data: JSON.parse(data) as Record<string, unknown> };
  } catch {
    return null;
  }
}
