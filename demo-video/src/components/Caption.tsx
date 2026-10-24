import { Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { colors, fonts } from "../theme";

// Arabic headline with an English line under it, mirroring the app's two languages.
export const Caption: React.FC<{ ar: string; en: string; top?: number }> = ({ ar, en, top = 44 }) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 0,
        right: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        // Room for Arabic descenders above the English line.
        gap: 22,
      }}
    >
      <Interactive.Div
        name="Arabic headline"
        style={{
          fontFamily: fonts.heading,
          fontWeight: 800,
          fontSize: 72,
          color: "#FFFFFF",
          direction: "rtl",
          lineHeight: 1.3,
          opacity: interpolate(frame, [5, 25], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(frame, [5, 25], ["0px 30px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        {ar}
      </Interactive.Div>
      <Interactive.Div
        name="English line"
        style={{
          fontFamily: fonts.latin,
          fontWeight: 600,
          fontSize: 36,
          color: colors.muted,
          opacity: interpolate(frame, [14, 34], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          translate: interpolate(frame, [14, 34], ["0px 20px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        {en}
      </Interactive.Div>
    </div>
  );
};
