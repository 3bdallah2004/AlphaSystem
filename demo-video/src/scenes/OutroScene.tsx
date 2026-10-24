import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { colors, fonts } from "../theme";

const COMMAND = "docker compose up -d --build --wait";

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const typed = Math.round(
    interpolate(frame, [20, 60], [0, COMMAND.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
  );

  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: 40 }}>
        <Interactive.Div
          name="Headline"
          style={{
            fontFamily: fonts.heading,
            fontWeight: 800,
            fontSize: 80,
            color: "#FFFFFF",
            direction: "rtl",
            opacity: interpolate(frame, [0, 18], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [0, 22], ["0px 30px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          يعمل بأمر واحد
        </Interactive.Div>
        <Interactive.Div
          name="Terminal"
          style={{
            width: 1100,
            borderRadius: 18,
            backgroundColor: "#071917",
            border: "2px solid rgba(255,255,255,0.12)",
            padding: "36px 44px",
            fontFamily: "Consolas, 'Courier New', monospace",
            fontSize: 40,
            color: "#FFFFFF",
            boxShadow: "0 30px 90px rgba(0,0,0,0.5)",
            opacity: interpolate(frame, [8, 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}
        >
          <div>
            <span style={{ color: colors.accentBright }}>$ </span>
            {COMMAND.slice(0, typed)}
            <span style={{ opacity: frame % 30 < 15 ? 1 : 0 }}>▌</span>
          </div>
          <div
            style={{
              marginTop: 18,
              color: "#61C554",
              opacity: interpolate(frame, [68, 78], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          >
            ✔ Alpha is running → http://localhost:8501
          </div>
        </Interactive.Div>
        <Interactive.Div
          name="Repo"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 28,
            opacity: interpolate(frame, [85, 100], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
          }}
        >
          <span style={{ fontFamily: fonts.latin, fontWeight: 800, fontSize: 64, color: "#FFFFFF", letterSpacing: -2 }}>Alpha</span>
          <span style={{ width: 3, height: 54, backgroundColor: colors.accentBright }} />
          <span style={{ fontFamily: fonts.latin, fontWeight: 600, fontSize: 40, color: colors.muted }}>
            github.com/3bdallah2004/AlphaSystem
          </span>
        </Interactive.Div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
