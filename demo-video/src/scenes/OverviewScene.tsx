import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { BrowserFrame } from "../components/BrowserFrame";
import { Caption } from "../components/Caption";
import { Highlight } from "../components/Highlight";

export const OverviewScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="كل القضايا في مكان واحد" en="Every case, its status and severity at a glance" />
      <BrowserFrame>
        <div
          style={{
            position: "absolute",
            width: 1920,
            height: 1080,
            transformOrigin: "0 0",
            scale: interpolate(frame, [0, 40, 75, 110, 140], [0.78125, 0.78125, 1.25, 1.25, 1.15], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.65, 0, 0.35, 1),
            }),
            translate: interpolate(
              frame,
              [0, 40, 75, 110, 140],
              ["0px 0px", "0px 0px", "-684px 0px", "-684px 0px", "-354px -299px"],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.65, 0, 0.35, 1) },
            ),
          }}
        >
          <Img src={staticFile("shots/overview-ar.png")} style={{ width: 1920, height: 1080 }} />
          <Highlight x={723} y={156} w={848} h={90} from={70} to={112} />
          <Highlight x={348} y={465} w={1224} h={226} from={135} to={182} />
        </div>
      </BrowserFrame>
    </AbsoluteFill>
  );
};
