import type { Metadata } from "next";

import { Workspace } from "./workspace";

export const metadata: Metadata = {
  title: "Workspace",
  description: "Overview, guide, architecture map, and cited answers for one commit.",
};

export default async function WorkspacePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ view?: string | string[] }>;
}) {
  const { id } = await params;
  const { view } = await searchParams;
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-canvas">
      <Workspace id={id} initialView={typeof view === "string" ? view : null} />
    </main>
  );
}
