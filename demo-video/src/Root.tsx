import { Composition, Folder } from "remotion";
import { AlphaDemo } from "./AlphaDemo";
import { DetailsScene } from "./scenes/DetailsScene";
import { IntroScene } from "./scenes/IntroScene";
import { NewCaseScene } from "./scenes/NewCaseScene";
import { OutroScene } from "./scenes/OutroScene";
import { OverviewScene } from "./scenes/OverviewScene";
import { PipelineScene } from "./scenes/PipelineScene";
import { PromptScene } from "./scenes/PromptScene";
import { ReportScene } from "./scenes/ReportScene";
import { WorkflowScene } from "./scenes/WorkflowScene";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="AlphaDemo" component={AlphaDemo} durationInFrames={1720} fps={30} width={1920} height={1080} />
      <Folder name="AlphaDemo-Scenes">
        <Composition id="Intro" component={IntroScene} durationInFrames={120} fps={30} width={1920} height={1080} />
        <Composition id="Overview" component={OverviewScene} durationInFrames={190} fps={30} width={1920} height={1080} />
        <Composition id="NewCase" component={NewCaseScene} durationInFrames={180} fps={30} width={1920} height={1080} />
        <Composition id="Details" component={DetailsScene} durationInFrames={160} fps={30} width={1920} height={1080} />
        <Composition id="Pipeline" component={PipelineScene} durationInFrames={150} fps={30} width={1920} height={1080} />
        <Composition id="Workflow" component={WorkflowScene} durationInFrames={400} fps={30} width={1920} height={1080} />
        <Composition id="Prompt" component={PromptScene} durationInFrames={240} fps={30} width={1920} height={1080} />
        <Composition id="Report" component={ReportScene} durationInFrames={250} fps={30} width={1920} height={1080} />
        <Composition id="Outro" component={OutroScene} durationInFrames={150} fps={30} width={1920} height={1080} />
      </Folder>
    </>
  );
};
