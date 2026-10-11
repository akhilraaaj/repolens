import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repository already has project instructions in the root AGENTS.md.
  agentRules: false,
  // The dev server is opened as localhost, and the API default is 127.0.0.1.
  // Next blocks dev assets when those hosts differ unless this list allows it.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
