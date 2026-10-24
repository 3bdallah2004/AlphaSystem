import { getLength, getPointAtLength } from "@remotion/paths";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { Caption } from "../components/Caption";
import { colors, fonts } from "../theme";

// Mirrors n8n/workflows/alpha-analysis.json: one webhook, routed by two IF nodes.
const NODE_W = 290;
const NODE_H = 96;

type NodeId = "webhook" | "health" | "respHealth" | "suggestIf" | "suggestLLM" | "callLLM" | "respReport" | "respError";

const NODES: Record<NodeId, { x: number; y: number; name: string; kind: string; color: string }> = {
  webhook: { x: 220, y: 560, name: "Webhook", kind: "POST /alpha-analyze", color: "#E0662A" },
  health: { x: 560, y: 560, name: "Health check?", kind: "IF · ping", color: "#3FA37C" },
  respHealth: { x: 905, y: 360, name: "Respond health", kind: "Respond to Webhook", color: "#8E7CC3" },
  suggestIf: { x: 905, y: 660, name: "Suggest details?", kind: "IF · mode", color: "#3FA37C" },
  suggestLLM: { x: 1255, y: 520, name: "Suggest with LLM", kind: "HTTP Request", color: "#4A90D9" },
  callLLM: { x: 1255, y: 790, name: "Call LLM", kind: "HTTP Request", color: "#4A90D9" },
  respReport: { x: 1640, y: 600, name: "Respond report", kind: "Respond to Webhook", color: "#8E7CC3" },
  respError: { x: 1640, y: 820, name: "Respond LLM error", kind: "HTTP 502", color: "#C0473B" },
};

const edgePath = (from: NodeId, to: NodeId) => {
  const a = NODES[from];
  const b = NODES[to];
  const x1 = a.x + NODE_W / 2;
  const x2 = b.x - NODE_W / 2;
  return `M ${x1} ${a.y} C ${x1 + 50} ${a.y}, ${x2 - 50} ${b.y}, ${x2} ${b.y}`;
};

type EdgeId = "e1" | "e2" | "e3" | "e4" | "e5" | "e6" | "e7" | "e8" | "e9";

const EDGES: Record<EdgeId, { d: string; label?: string }> = {
  e1: { d: edgePath("webhook", "health") },
  e2: { d: edgePath("health", "respHealth"), label: "ping" },
  e3: { d: edgePath("health", "suggestIf"), label: "else" },
  e4: { d: edgePath("suggestIf", "suggestLLM"), label: "suggest" },
  e5: { d: edgePath("suggestIf", "callLLM"), label: "analyze" },
  e6: { d: edgePath("suggestLLM", "respReport") },
  e7: { d: edgePath("callLLM", "respReport") },
  e8: { d: edgePath("suggestLLM", "respError") },
  e9: { d: edgePath("callLLM", "respError") },
};

const STAGES: { start: number; end: number; nodes: NodeId[]; edges: EdgeId[]; ar: string; en: string }[] = [
  {
    start: 45,
    end: 135,
    nodes: ["webhook", "health", "respHealth"],
    edges: ["e1", "e2"],
    ar: "فحص الاتصال: يتأكد أن سير العمل يعمل وأن مفتاح النموذج مضبوط",
    en: "Ping — the app's “Check analysis service” button confirms the workflow is live and an API key is set",
  },
  {
    start: 135,
    end: 225,
    nodes: ["webhook", "health", "suggestIf", "suggestLLM", "respReport"],
    edges: ["e1", "e3", "e4", "e6"],
    ar: "الاقتراح: يستخرج العنوان والتصنيف والموقع والتاريخ من نص البلاغ",
    en: "Suggest — extracts title, case type, location and date from the raw report",
  },
  {
    start: 225,
    end: 315,
    nodes: ["webhook", "health", "suggestIf", "callLLM", "respReport"],
    edges: ["e1", "e3", "e5", "e7"],
    ar: "التحليل: يرسل القضية كاملة إلى النموذج ويعيد تقريراً منظماً",
    en: "Analyze — sends the full case to the LLM and returns a structured JSON report",
  },
  {
    start: 315,
    end: 400,
    nodes: ["webhook", "health", "suggestIf", "callLLM", "respError"],
    edges: ["e1", "e3", "e5", "e9"],
    ar: "عند الفشل: يعيد الخطأ فتُحفظ القضية لإعادة التحليل",
    en: "On failure — returns the error, and the case is kept so it can be re-analyzed",
  },
];

const stageFade = (frame: number, start: number, end: number) =>
  interpolate(frame, [start, start + 10, end - 10, end], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const activity = (frame: number, pick: (s: (typeof STAGES)[number]) => boolean) =>
  Math.max(0, ...STAGES.filter(pick).map((s) => stageFade(frame, s.start, s.end)));

// A dot that travels the stage's edges one after another.
const routeDot = (frame: number, stage: (typeof STAGES)[number]) => {
  const paths = stage.edges.map((e) => EDGES[e].d);
  const lengths = paths.map((p) => getLength(p));
  const total = lengths.reduce((a, b) => a + b, 0);
  let along = interpolate(frame, [stage.start + 8, stage.start + 55], [0, total], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.45, 0, 0.55, 1),
  });
  for (let i = 0; i < paths.length; i++) {
    if (along <= lengths[i] || i === paths.length - 1) {
      return getPointAtLength(paths[i], Math.min(along, lengths[i])) ?? { x: 0, y: 0 };
    }
    along -= lengths[i];
  }
  return { x: 0, y: 0 };
};

export const WorkflowScene: React.FC = () => {
  const frame = useCurrentFrame();
  const current = STAGES.find((s) => frame >= s.start && frame < s.end);

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="سير عمل n8n يوجّه كل طلب إلى مساره" en="The n8n workflow receives every request from the app and routes it" />

      <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0 }}>
        {(Object.keys(EDGES) as EdgeId[]).map((id, i) => {
          const edge = EDGES[id];
          const length = getLength(edge.d);
          const on = activity(frame, (s) => s.edges.indexOf(id) >= 0);
          const mid = getPointAtLength(edge.d, length / 2) ?? { x: 0, y: 0 };
          return (
            <g key={id}>
              <path
                d={edge.d}
                fill="none"
                stroke="rgba(255,255,255,0.28)"
                strokeWidth={4}
                strokeDasharray={length}
                strokeDashoffset={interpolate(frame, [10 + i * 3, 30 + i * 3], [length, 0], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                })}
              />
              <path d={edge.d} fill="none" stroke={colors.accentBright} strokeWidth={6} opacity={on} />
              {edge.label ? (
                <g opacity={interpolate(frame, [30, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}>
                  <rect
                    x={mid.x - 52}
                    y={mid.y - 18}
                    width={104}
                    height={36}
                    rx={18}
                    fill={on > 0.5 ? colors.accentBright : "#163C39"}
                    stroke="rgba(255,255,255,0.25)"
                  />
                  <text
                    x={mid.x}
                    y={mid.y + 7}
                    textAnchor="middle"
                    fontFamily={fonts.latin}
                    fontWeight={600}
                    fontSize={19}
                    fill="#FFFFFF"
                  >
                    {edge.label}
                  </text>
                </g>
              ) : null}
            </g>
          );
        })}
      </svg>

      {(Object.keys(NODES) as NodeId[]).map((id, i) => {
        const node = NODES[id];
        const on = activity(frame, (s) => s.nodes.indexOf(id) >= 0);
        return (
          <div
            key={id}
            style={{
              position: "absolute",
              left: node.x - NODE_W / 2,
              top: node.y - NODE_H / 2,
              width: NODE_W,
              height: NODE_H,
              borderRadius: 16,
              backgroundColor: "#0E2B29",
              border: `2px solid ${on > 0.5 ? colors.accentBright : "rgba(255,255,255,0.2)"}`,
              boxShadow: `0 0 ${40 * on}px rgba(224,102,42,${0.55 * on})`,
              display: "flex",
              alignItems: "center",
              overflow: "hidden",
              opacity: interpolate(frame, [i * 3, i * 3 + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
              scale: interpolate(frame, [i * 3, i * 3 + 18], [0.85, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.spring({ damping: 14 }),
              }),
            }}
          >
            <div style={{ width: 12, alignSelf: "stretch", backgroundColor: node.color }} />
            <div style={{ padding: "0 20px", display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ fontFamily: fonts.latin, fontWeight: 600, fontSize: 24, color: "#FFFFFF", whiteSpace: "nowrap" }}>{node.name}</div>
              <div style={{ fontFamily: fonts.latin, fontSize: 18, color: colors.muted }}>{node.kind}</div>
            </div>
          </div>
        );
      })}

      {current ? (
        <div
          style={{
            position: "absolute",
            left: routeDot(frame, current).x - 11,
            top: routeDot(frame, current).y - 11,
            width: 22,
            height: 22,
            borderRadius: 11,
            backgroundColor: "#FFFFFF",
            boxShadow: `0 0 24px 8px ${colors.accentBright}`,
          }}
        />
      ) : null}

      {STAGES.map((s, i) => (
        <div
          key={s.start}
          style={{
            position: "absolute",
            left: 160,
            right: 160,
            top: 905,
            height: 120,
            borderRadius: 20,
            backgroundColor: "rgba(255,255,255,0.07)",
            border: "2px solid rgba(255,255,255,0.14)",
            display: "flex",
            alignItems: "center",
            gap: 28,
            padding: "0 32px",
            opacity: stageFade(frame, s.start, s.end),
          }}
        >
          <div
            style={{
              fontFamily: fonts.latin,
              fontWeight: 800,
              fontSize: 30,
              color: "#FFFFFF",
              backgroundColor: colors.accentBright,
              borderRadius: 30,
              width: 60,
              height: 60,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            {i + 1}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
            <div style={{ fontFamily: fonts.heading, fontWeight: 700, fontSize: 36, color: "#FFFFFF", direction: "rtl" }}>
              {s.ar}
            </div>
            <div style={{ fontFamily: fonts.latin, fontWeight: 600, fontSize: 24, color: colors.muted }}>{s.en}</div>
          </div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
