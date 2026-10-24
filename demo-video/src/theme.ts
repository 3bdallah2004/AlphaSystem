import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadKufi } from "@remotion/google-fonts/NotoKufiArabic";
import { loadFont as loadPlex } from "@remotion/google-fonts/IBMPlexSansArabic";

export const fonts = {
  latin: loadInter("normal", { weights: ["400", "600", "800"], subsets: ["latin"] }).fontFamily,
  heading: loadKufi("normal", { weights: ["700", "800"], subsets: ["arabic", "latin"] }).fontFamily,
  body: loadPlex("normal", { weights: ["400", "600"], subsets: ["arabic", "latin"] }).fontFamily,
};

// Taken from the app's .streamlit/config.toml so the video matches the product.
export const colors = {
  ink: "#0B2422",
  teal: "#10302E",
  tealLight: "#1B4A46",
  accent: "#B8430E",
  accentBright: "#E0662A",
  paper: "#F4F6F5",
  muted: "#9FB8B4",
};
