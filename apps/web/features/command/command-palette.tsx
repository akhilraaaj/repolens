"use client";

import { Box, FileCode2, LayoutDashboard, MessageSquare, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";
import type { SymbolRow } from "../../lib/api";

export type PaletteView = { id: string; label: string; icon: LucideIcon };

const MAX_FILES = 1500;
const MAX_SYMBOLS = 1500;

export function CommandPalette({
  open,
  onOpenChange,
  files,
  symbols,
  views,
  onFile,
  onSymbol,
  onView,
  onAsk,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  files: string[];
  symbols: SymbolRow[];
  views: PaletteView[];
  onFile: (path: string) => void;
  onSymbol: (symbol: SymbolRow) => void;
  onView: (id: string) => void;
  onAsk: (question: string) => void;
}) {
  const [query, setQuery] = useState("");
  const namedSymbols = useMemo(
    () => symbols.filter((symbol) => symbol.entity_type !== "module").slice(0, MAX_SYMBOLS),
    [symbols],
  );

  useEffect(() => {
    const down = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", down);
    return () => window.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  function run(action: () => void) {
    action();
    setQuery("");
    onOpenChange(false);
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command menu"
      description="Jump to a file or symbol, or ask a question"
      className="top-[14vh] sm:max-w-xl"
    >
      <Command>
        <CommandInput value={query} onValueChange={setQuery} placeholder="Jump to a file or symbol, or ask a question" />
        <CommandList className="max-h-[52vh]">
          <CommandEmpty>No match.</CommandEmpty>
          {query.trim().length > 2 ? (
            <CommandGroup heading="Ask">
              <CommandItem value={`ask ${query}`} onSelect={() => run(() => onAsk(query.trim()))}>
                <MessageSquare className="text-brand" />
                <span className="truncate">Ask: {query.trim()}</span>
              </CommandItem>
            </CommandGroup>
          ) : null}
          <CommandGroup heading="Views">
            {views.map((view) => (
              <CommandItem key={view.id} value={`view ${view.label}`} onSelect={() => run(() => onView(view.id))}>
                <view.icon className="text-faint" />
                {view.label}
              </CommandItem>
            ))}
          </CommandGroup>
          {query.trim() !== "" ? (
            <>
              <CommandGroup heading="Symbols">
                {namedSymbols.map((symbol) => (
                  <CommandItem
                    key={symbol.id}
                    value={`symbol ${symbol.qualified_name}`}
                    onSelect={() => run(() => onSymbol(symbol))}
                  >
                    <Box className="text-info" />
                    <span className="truncate">{symbol.name}</span>
                    <span className="ml-auto truncate font-mono text-[11px] text-faint">{symbol.path}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
              <CommandGroup heading="Files">
                {files.slice(0, MAX_FILES).map((path) => (
                  <CommandItem key={path} value={`file ${path}`} onSelect={() => run(() => onFile(path))}>
                    <FileCode2 className="text-faint" />
                    <span className="truncate font-mono text-xs">{path}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </>
          ) : null}
        </CommandList>
        <div className="flex items-center gap-3 border-t px-3 py-2 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Kbd>↵</Kbd> open
          </span>
          <span className="inline-flex items-center gap-1">
            <Kbd>esc</Kbd> close
          </span>
          <span className="ml-auto inline-flex items-center gap-1">
            <LayoutDashboard className="size-3" /> RepoLens
          </span>
        </div>
      </Command>
    </CommandDialog>
  );
}
