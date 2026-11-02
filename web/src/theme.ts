import { useSyncExternalStore } from "react";

export type ThemePreference = "system" | "light" | "dark";
type ThemeSnapshot = { preference: ThemePreference; resolvedTheme: "light" | "dark" };
declare global {
  interface Window {
    alphaTheme: {
      getSnapshot: () => ThemeSnapshot;
      subscribe: (listener: () => void) => () => void;
      setPreference: (preference: ThemePreference) => void;
    };
  }
}

const serverSnapshot: ThemeSnapshot = { preference: "system", resolvedTheme: "light" };
const getServerSnapshot = () => serverSnapshot;
const subscribe = (listener: () => void) => window.alphaTheme.subscribe(listener);
const getSnapshot = () => window.alphaTheme.getSnapshot();

export function useTheme() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { ...snapshot, setPreference: (value: ThemePreference) => window.alphaTheme.setPreference(value) };
}
