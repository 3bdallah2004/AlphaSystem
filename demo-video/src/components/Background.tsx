import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { colors } from "../theme";

// Dark teal backdrop with a slowly drifting investigation grid.
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 600], [0, 60]);

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 0%, ${colors.tealLight} 0%, ${colors.teal} 45%, ${colors.ink} 100%)`,
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.07,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,1) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          backgroundPosition: `${drift}px ${drift}px`,
        }}
      />
    </AbsoluteFill>
  );
};
