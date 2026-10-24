import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { BrowserFrame } from "../components/BrowserFrame";
import { Caption } from "../components/Caption";
import { Cursor } from "../components/Cursor";

const CLICK_AT = 36;

export const NewCaseScene: React.FC = () => {
  const frame = useCurrentFrame();
  // The sample report "types" into the box right to left, the way Arabic is written.
  const revealLeft = interpolate(frame, [CLICK_AT + 6, CLICK_AT + 50], [1470, 790], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="اكتب البلاغ كما وصلك" en="Paste the incident report exactly as it arrived" />
      <BrowserFrame url="localhost:8501/?view=new">
        <div
          style={{
            position: "absolute",
            width: 1920,
            height: 1080,
            transformOrigin: "0 0",
            scale: interpolate(frame, [0, 95, 130], [0.78125, 0.78125, 1.3], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.65, 0, 0.35, 1),
            }),
            translate: interpolate(frame, [0, 95, 130], ["0px 0px", "0px 0px", "-712px -22px"], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.65, 0, 0.35, 1),
            }),
          }}
        >
          <Img src={staticFile("shots/new-ar.png")} style={{ position: "absolute", width: 1920, height: 1080 }} />
          <Img
            src={staticFile("shots/new-sample-ar.png")}
            style={{
              position: "absolute",
              width: 1920,
              height: 1080,
              clipPath: `inset(210px 450px 800px ${revealLeft}px)`,
            }}
          />
          <Img
            src={staticFile("shots/new-sample-ar.png")}
            style={{
              position: "absolute",
              width: 1920,
              height: 1080,
              opacity: interpolate(frame, [CLICK_AT + 50, CLICK_AT + 54], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          />
          <div
            style={{
              opacity: interpolate(frame, [70, 85], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          >
            <Cursor
              x={interpolate(frame, [8, 32], [1560, 1262], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.65, 0, 0.35, 1),
              })}
              y={interpolate(frame, [8, 32], [820, 570], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.65, 0, 0.35, 1),
              })}
              clickAt={CLICK_AT}
            />
          </div>
        </div>
      </BrowserFrame>
    </AbsoluteFill>
  );
};
