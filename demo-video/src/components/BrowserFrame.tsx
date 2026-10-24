import { Easing, interpolate, useCurrentFrame } from "remotion";
import { colors, fonts } from "../theme";

export const FRAME = { width: 1500, height: 780, chrome: 44 };

// A browser window pointed at the local app. Children are positioned inside the page area.
export const BrowserFrame: React.FC<{
  children: React.ReactNode;
  url?: string;
  top?: number;
}> = ({ children, url = "localhost:8501", top = 250 }) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        top,
        left: (1920 - FRAME.width) / 2,
        width: FRAME.width,
        height: FRAME.height,
        borderRadius: 18,
        overflow: "hidden",
        backgroundColor: colors.paper,
        boxShadow: "0 40px 120px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.08)",
        opacity: interpolate(frame, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        translate: interpolate(frame, [0, 24], ["0px 60px", "0px 0px"], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.16, 1, 0.3, 1),
        }),
      }}
    >
      <div
        style={{
          height: FRAME.chrome,
          backgroundColor: "#E4E9E8",
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 18px",
          borderBottom: "1px solid #D5DDDB",
        }}
      >
        {["#EC6A5E", "#F4BF4F", "#61C554"].map((c) => (
          <div key={c} style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: c }} />
        ))}
        <div
          style={{
            marginLeft: 18,
            flex: 1,
            maxWidth: 560,
            height: 28,
            borderRadius: 14,
            backgroundColor: "#FFFFFF",
            display: "flex",
            alignItems: "center",
            padding: "0 16px",
            fontFamily: fonts.latin,
            fontSize: 16,
            color: "#4A6360",
          }}
        >
          {url}
        </div>
      </div>
      <div style={{ position: "relative", width: FRAME.width, height: FRAME.height - FRAME.chrome, overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
};
