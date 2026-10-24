import { interpolate, useCurrentFrame } from "remotion";
import { colors } from "../theme";

// Mouse pointer in page pixels with a click ripple at `clickAt`.
export const Cursor: React.FC<{ x: number; y: number; clickAt: number }> = ({ x, y, clickAt }) => {
  const frame = useCurrentFrame();
  const ripple = interpolate(frame, [clickAt, clickAt + 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const press = interpolate(frame, [clickAt - 3, clickAt, clickAt + 4], [1, 0.82, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ position: "absolute", left: x, top: y }}>
      {frame >= clickAt ? (
        <div
          style={{
            position: "absolute",
            left: -40 * ripple,
            top: -40 * ripple,
            width: 80 * ripple,
            height: 80 * ripple,
            borderRadius: "50%",
            border: `4px solid ${colors.accentBright}`,
            opacity: 1 - ripple,
          }}
        />
      ) : null}
      <svg width={38} height={46} viewBox="0 0 19 23" style={{ scale: String(press), transformOrigin: "0 0" }}>
        <path d="M1 1 L1 18 L5.5 13.8 L8.6 21 L11.6 19.7 L8.6 12.6 L14.6 12.6 Z" fill="#111" stroke="#fff" strokeWidth={1.4} />
      </svg>
    </div>
  );
};
