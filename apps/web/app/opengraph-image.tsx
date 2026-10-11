import { ImageResponse } from "next/og";

export const alt = "RepoLens";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#09090b",
          color: "#ededf0",
          padding: "72px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              border: "1px solid #2e2e36",
              background: "#16161a",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 18,
                height: 18,
                borderRadius: 999,
                border: "4px solid #6ee7b7",
              }}
            />
          </div>
          <div style={{ fontSize: 28, fontWeight: 600 }}>RepoLens</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 860 }}>
          <div style={{ fontSize: 68, fontWeight: 600, lineHeight: 1.05, letterSpacing: -1.5 }}>Understand a repository at one commit.</div>
          <div style={{ fontSize: 28, lineHeight: 1.4, color: "#9b9ba6" }}>
            A map of how the files connect, and answers that cite exact lines.
          </div>
        </div>
      </div>
    ),
    { ...size },
  );
}
