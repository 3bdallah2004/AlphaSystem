import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { Background } from "../components/Background";
import { BrowserFrame } from "../components/BrowserFrame";
import { Caption } from "../components/Caption";
import { Highlight } from "../components/Highlight";

export const DetailsScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Background />
      <Caption ar="العنوان والتصنيف والموقع جاهزة" en="Title, type, date and location suggested from the text" />
      <BrowserFrame url="localhost:8501/?view=new&case=1">
        <div
          style={{
            position: "absolute",
            width: 1920,
            height: 1080,
            transformOrigin: "0 0",
            scale: interpolate(frame, [0, 25, 55, 90, 120], [0.78125, 0.78125, 1.15, 1.15, 1.15], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.65, 0, 0.35, 1),
            }),
            translate: interpolate(
              frame,
              [0, 25, 55, 90, 120],
              ["0px 0px", "0px 0px", "-538px -12px", "-538px -12px", "-538px -414px"],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.65, 0, 0.35, 1) },
            ),
          }}
        >
          <Img src={staticFile("shots/details-ar.png")} style={{ width: 1920, height: 1080 }} />
          <Highlight x={774} y={210} w={693} h={222} from={50} to={92} />
          <Highlight x={774} y={504} w={693} h={340} from={115} to={158} />
        </div>
      </BrowserFrame>
    </AbsoluteFill>
  );
};
