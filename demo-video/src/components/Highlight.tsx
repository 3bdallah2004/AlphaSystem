import { interpolate, useCurrentFrame } from "remotion";
import { colors } from "../theme";

// Accent ring drawn in page pixels, so it moves with the camera.
export const Highlight: React.FC<{
  x: number;
  y: number;
  w: number;
  h: number;
  from: number;
  to: number;
}> = ({ x, y, w, h, from, to }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [from, from + 10, to - 10, to], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const grow = interpolate(frame, [from, from + 14], [14, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: x - 8 - grow,
        top: y - 8 - grow,
        width: w + 16 + grow * 2,
        height: h + 16 + grow * 2,
        borderRadius: 14,
        border: `4px solid ${colors.accentBright}`,
        boxShadow: `0 0 0 9999px rgba(11,36,34,${0.3 * opacity})`,
        opacity,
      }}
    />
  );
};
