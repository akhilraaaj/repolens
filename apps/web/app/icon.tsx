import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** The logo mark from components/logo.tsx, in hex because the image renderer may not read oklch. */
export default function Icon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: "#09090b" }}>
        <svg width="32" height="32" viewBox="0 0 24 24">
          <rect x="0.5" y="0.5" width="23" height="23" rx="7" fill="#16161a" stroke="#2e2e36" />
          <path d="M8 9 L16 8 M8 9 L12 16.5 M16 8 L12 16.5" stroke="#6b6b76" strokeWidth="1.2" strokeLinecap="round" />
          <circle cx="8" cy="9" r="2.6" fill="#6bcbf7" />
          <circle cx="16" cy="8" r="2" fill="#b0a4f8" />
          <circle cx="12" cy="16.5" r="2.2" fill="#f28788" />
        </svg>
      </div>
    ),
    { ...size },
  );
}
