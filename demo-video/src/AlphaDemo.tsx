import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { DetailsScene } from "./scenes/DetailsScene";
import { IntroScene } from "./scenes/IntroScene";
import { NewCaseScene } from "./scenes/NewCaseScene";
import { OutroScene } from "./scenes/OutroScene";
import { OverviewScene } from "./scenes/OverviewScene";
import { PipelineScene } from "./scenes/PipelineScene";
import { PromptScene } from "./scenes/PromptScene";
import { ReportScene } from "./scenes/ReportScene";
import { WorkflowScene } from "./scenes/WorkflowScene";

// Registered in Root.tsx at 1720 frames: 1840 frames of scenes minus 8 transitions of 15 frames.
export const AlphaDemo: React.FC = () => (
  <TransitionSeries>
    <TransitionSeries.Sequence name="Intro" durationInFrames={120}>
      <IntroScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Overview" durationInFrames={190}>
      <OverviewScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="New case" durationInFrames={180}>
      <NewCaseScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Details" durationInFrames={160}>
      <DetailsScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Pipeline" durationInFrames={150}>
      <PipelineScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Workflow" durationInFrames={400}>
      <WorkflowScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Prompt" durationInFrames={240}>
      <PromptScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Report" durationInFrames={250}>
      <ReportScene />
    </TransitionSeries.Sequence>
    <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />
    <TransitionSeries.Sequence name="Outro" durationInFrames={150}>
      <OutroScene />
    </TransitionSeries.Sequence>
  </TransitionSeries>
);
