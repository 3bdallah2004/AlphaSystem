import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { colors, fonts } from "../theme";

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", gap: 18 }}>
        <Interactive.Div
          name="Wordmark"
          style={{
            fontFamily: fonts.latin,
            fontWeight: 800,
            fontSize: 220,
            letterSpacing: -6,
            color: "#FFFFFF",
            lineHeight: 1,
            opacity: interpolate(frame, [0, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            scale: interpolate(frame, [0, 30], [0.85, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.spring({ damping: 200 }),
              output: "perceptual-scale",
            }),
          }}
        >
          Alpha
        </Interactive.Div>
        <Interactive.Div
          name="Accent bar"
          style={{
            height: 8,
            borderRadius: 4,
            backgroundColor: colors.accentBright,
            width: interpolate(frame, [18, 45], [0, 260], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        />
        <Interactive.Div
          name="Arabic tagline"
          style={{
            marginTop: 20,
            fontFamily: fonts.heading,
            fontWeight: 700,
            fontSize: 64,
            color: "#FFFFFF",
            direction: "rtl",
            opacity: interpolate(frame, [30, 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [30, 50], ["0px 24px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          نظام إدارة التحقيقات الجنائية الذكي
        </Interactive.Div>
        <Interactive.Div
          name="English tagline"
          style={{
            fontFamily: fonts.latin,
            fontWeight: 600,
            fontSize: 38,
            color: colors.muted,
            opacity: interpolate(frame, [42, 62], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            translate: interpolate(frame, [42, 62], ["0px 20px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          AI-powered criminal case analysis
        </Interactive.Div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
