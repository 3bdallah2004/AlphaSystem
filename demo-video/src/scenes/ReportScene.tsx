import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { BrowserFrame } from "../components/BrowserFrame";
import { Caption } from "../components/Caption";
import { Highlight } from "../components/Highlight";

export const ReportScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="تقرير منظم في دقائق" en="Summary, facts, hypotheses, evidence and next steps" />
      <BrowserFrame url="localhost:8501/?view=case&case=1">
        <div
          style={{
            position: "absolute",
            width: 1920,
            height: 1800,
            transformOrigin: "0 0",
            scale: interpolate(frame, [0, 30, 65, 95, 130, 170, 210], [0.78125, 0.78125, 1.1, 1.1, 1.2, 1.2, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.65, 0, 0.35, 1),
            }),
            translate: interpolate(
              frame,
              [0, 30, 65, 95, 130, 170, 210],
              ["0px 0px", "0px 0px", "-328px 0px", "-328px 0px", "0px -184px", "0px -184px", "-238px -542px"],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.65, 0, 0.35, 1) },
            ),
          }}
        >
          <Img src={staticFile("shots/case-ar-tall.png")} style={{ width: 1920, height: 1800 }} />
          <Highlight x={480} y={198} w={253} h={69} from={58} to={98} />
          <Highlight x={58} y={215} w={374} h={334} from={125} to={168} />
          <Highlight x={480} y={682} w={1017} h={463} from={205} to={250} />
        </div>
      </BrowserFrame>
    </AbsoluteFill>
  );
};
