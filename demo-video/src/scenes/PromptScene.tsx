import { AbsoluteFill, Easing, Interactive, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Caption } from "../components/Caption";
import { colors, fonts } from "../theme";

// The keys the "Call LLM" node's system prompt asks for, in order.
const KEYS: [string, string][] = [
  ["ملخص القضية", "string"],
  ["الوقائع الرئيسية", "list"],
  ["الأدلة والقرائن", "list"],
  ["الأطراف المعنية", "list"],
  ["الفرضيات المحتملة", "list"],
  ["الخطوات التحقيقية المقترحة", "list"],
  ["مستوى الخطورة", "low · medium · high"],
];

const RULES: [string, string][] = [
  ["لا يخترع وقائع", "Never invents facts; missing details are stated explicitly"],
  ["أي مزوّد متوافق مع OpenAI", "OpenAI, Gemini, Claude, Groq or local Ollama"],
  ["يُستورد ويُفعَّل تلقائياً", "Docker loads and activates it on every start"],
];

export const PromptScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="ماذا يُطلب من النموذج؟" en="Every analysis comes back as the same seven-part JSON report" />
      <Interactive.Div
        name="JSON schema card"
        style={{
          position: "absolute",
          left: 1000,
          top: 270,
          width: 760,
          borderRadius: 22,
          backgroundColor: "#071917",
          border: "2px solid rgba(255,255,255,0.14)",
          padding: "26px 34px",
          opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        }}
      >
        <div style={{ fontFamily: "Consolas, 'Courier New', monospace", fontSize: 26, color: colors.muted, marginBottom: 10 }}>
          {"{ JSON }"}
        </div>
        {KEYS.map(([key, type], i) => (
          <div
            key={key}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              height: 82,
              borderTop: i === 0 ? "none" : "1px solid rgba(255,255,255,0.08)",
              opacity: interpolate(frame, [15 + i * 10, 25 + i * 10], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
              translate: interpolate(frame, [15 + i * 10, 28 + i * 10], ["30px 0px", "0px 0px"], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
            }}
          >
            <span style={{ fontFamily: "Consolas, 'Courier New', monospace", fontSize: 24, color: "#61C554" }}>{type}</span>
            <span style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 36, color: "#FFFFFF", direction: "rtl" }}>
              «{key}»
            </span>
          </div>
        ))}
      </Interactive.Div>
      {RULES.map(([ar, en], i) => (
        <div
          key={ar}
          style={{
            position: "absolute",
            left: 160,
            top: 290 + i * 230,
            width: 780,
            height: 200,
            borderRadius: 22,
            backgroundColor: "rgba(255,255,255,0.07)",
            border: "2px solid rgba(255,255,255,0.14)",
            borderRight: `8px solid ${colors.accentBright}`,
            padding: "0 36px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "flex-end",
            gap: 12,
            opacity: interpolate(frame, [95 + i * 18, 110 + i * 18], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            translate: interpolate(frame, [95 + i * 18, 115 + i * 18], ["-40px 0px", "0px 0px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
          }}
        >
          <div style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 42, color: "#FFFFFF", direction: "rtl" }}>{ar}</div>
          <div style={{ fontFamily: fonts.latin, fontWeight: 600, fontSize: 26, color: colors.muted, textAlign: "right" }}>{en}</div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
