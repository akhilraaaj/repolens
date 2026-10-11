import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

const description =
  "Understand a public GitHub repository at one commit. RepoLens maps how the files connect and answers questions with citations to exact lines.";

export const metadata: Metadata = {
  title: {
    default: "RepoLens",
    template: "%s · RepoLens",
  },
  description,
  applicationName: "RepoLens",
  keywords: ["codebase", "repository", "static analysis", "pgvector", "citations"],
  robots: { index: true, follow: true },
  openGraph: {
    title: "RepoLens",
    description,
    siteName: "RepoLens",
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: "RepoLens",
    description,
  },
};

export const viewport: Viewport = {
  themeColor: "#09090b",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} dark`} suppressHydrationWarning>
      <body className="bg-background font-sans text-foreground antialiased" suppressHydrationWarning>
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
