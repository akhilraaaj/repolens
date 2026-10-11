"use client";

import { useEffect, useState } from "react";

import { apiBaseUrl } from "../../lib/api-base";
import { cn } from "../../lib/cn";

type Status = "checking" | "ok" | "down";

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch(`${apiBaseUrl()}/health`)
      .then((response) => response.json())
      .then((body: unknown) => {
        const ok = typeof body === "object" && body !== null && "status" in body && body.status === "ok";
        if (!cancelled) {
          setStatus(ok ? "ok" : "down");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("down");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const label = status === "ok" ? "API online" : status === "down" ? "API offline" : "Checking API";
  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium" title={status === "down" ? `No response from ${apiBaseUrl()}/health` : undefined}>
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          status === "ok" && "bg-brand",
          status === "down" && "bg-danger",
          status === "checking" && "animate-pulse bg-faint",
        )}
      />
      {label}
    </span>
  );
}
