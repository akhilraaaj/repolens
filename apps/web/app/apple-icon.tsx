import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#09090b",
        }}
      >
        <div
          style={{
            width: 132,
            height: 132,
            borderRadius: 32,
            border: "2px solid #2e2e36",
            background: "#16161a",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 999,
              border: "8px solid #6ee7b7",
            }}
          />
        </div>
      </div>
    ),
    { ...size },
  );
}
