import type { Metadata } from "next";

import { Workspace } from "./workspace";

export const metadata: Metadata = {
  title: "Workspace",
  description: "Overview, guide, architecture map, and cited answers for one commit.",
};

export default async function WorkspacePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className="flex h-screen flex-col overflow-hidden bg-canvas">
      <Workspace id={id} />
    </main>
  );
}
