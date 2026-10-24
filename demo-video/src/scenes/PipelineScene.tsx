import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Caption } from "../components/Caption";
import { colors, fonts } from "../theme";

const Node: React.FC<{ x: number; at: number; ar: string; en: string; note: string }> = ({ x, at, ar, en, note }) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        position: "absolute",
        left: x - 200,
        top: 410,
        width: 400,
        height: 230,
        borderRadius: 24,
        backgroundColor: "rgba(255,255,255,0.06)",
        border: "2px solid rgba(255,255,255,0.18)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        opacity: interpolate(frame, [at, at + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        scale: interpolate(frame, [at, at + 20], [0.8, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.spring({ damping: 14 }),
        }),
      }}
    >
      <div style={{ fontFamily: fonts.latin, fontWeight: 800, fontSize: 52, color: "#FFFFFF" }}>{en}</div>
      <div style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 34, color: colors.accentBright }}>{ar}</div>
      <div style={{ fontFamily: fonts.latin, fontSize: 22, color: colors.muted }}>{note}</div>
    </div>
  );
};

export const PipelineScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="التحليل يتم عبر n8n ونموذج لغوي" en="Each case goes through an n8n workflow to the LLM of your choice" />
      <Node x={420} at={10} en="Streamlit" ar="الواجهة" note="Case intake · SQLite" />
      <Node x={960} at={34} en="n8n" ar="سير العمل" note="Webhook · PostgreSQL" />
      <Node x={1500} at={58} en="LLM" ar="نموذج لغوي" note="OpenAI · Gemini · Claude · Ollama" />
      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        <defs>
          <marker id="head" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 Z" fill={colors.accentBright} />
          </marker>
          <marker id="head-white" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10 Z" fill="#FFFFFF" />
          </marker>
        </defs>
        <Interactive.Path
          name="Arrow to n8n"
          d="M 632 525 L 740 525"
          stroke={colors.accentBright}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={108}
          markerEnd={frame >= 36 ? "url(#head)" : undefined}
          strokeDashoffset={interpolate(frame, [22, 36], [108, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
        />
        <Interactive.Path
          name="Arrow to LLM"
          d="M 1172 525 L 1280 525"
          stroke={colors.accentBright}
          strokeWidth={6}
          strokeLinecap="round"
          strokeDasharray={108}
          markerEnd={frame >= 60 ? "url(#head)" : undefined}
          strokeDashoffset={interpolate(frame, [46, 60], [108, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
        />
        <Interactive.Path
          name="Report back to app"
          d="M 1500 650 C 1500 830, 420 830, 420 662"
          fill="none"
          stroke="#FFFFFF"
          strokeWidth={5}
          strokeLinecap="round"
          markerEnd={frame >= 115 ? "url(#head-white)" : undefined}
          strokeDasharray={1400}
          strokeDashoffset={interpolate(frame, [80, 115], [1400, 0], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.65, 0, 0.35, 1),
          })}
        />
      </svg>
      <Interactive.Div
        name="Report label"
        style={{
          position: "absolute",
          top: 800,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          gap: 24,
          alignItems: "baseline",
          opacity: interpolate(frame, [105, 120], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}
      >
        <span style={{ fontFamily: fonts.latin, fontWeight: 600, fontSize: 34, color: colors.muted }}>
          Structured JSON report
        </span>
        <span style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 44, color: "#FFFFFF" }}>تقرير منظم</span>
      </Interactive.Div>
    </AbsoluteFill>
  );
};
