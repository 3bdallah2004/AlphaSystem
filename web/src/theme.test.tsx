import source from "../public/theme.js?raw";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ThemeSwitcher from "./components/ThemeSwitcher";
import { readStoredValue, writeStoredValue } from "./storage";

const originalStore = window.alphaTheme;

function boot(saved: string | null = null, dark = false, blocked = false) {
  const media = new EventTarget() as EventTarget & { matches: boolean };
  media.matches = dark;
  const storage = {
    getItem: vi.fn(() => { if (blocked) throw new Error("blocked"); return saved; }),
    setItem: vi.fn((_key: string, value: string) => { if (blocked) throw new Error("blocked"); saved = value; }),
  };
  const browser = Object.assign(new EventTarget(), {
    localStorage: storage,
    matchMedia: vi.fn(() => media),
    alphaTheme: originalStore,
  });
  new Function("window", "document", source)(browser, document);
  return {
    store: browser.alphaTheme, storage,
    changeSystem(value: boolean) { media.matches = value; media.dispatchEvent(new Event("change")); },
    changeStorage(value: string | null, key: string | null = "alpha-theme", storageArea = storage) {
      browser.dispatchEvent(Object.assign(new Event("storage"), { key, newValue: value, storageArea }));
    },
  };
}

afterEach(() => {
  cleanup();
  window.alphaTheme = originalStore;
  vi.restoreAllMocks();
});

describe("theme startup and preference store", () => {
  it.each([false, true])("defaults to system before React renders (OS dark=%s)", (dark) => {
    const { store, storage } = boot(null, dark);
    expect(store.getSnapshot()).toEqual({ preference: "system", resolvedTheme: dark ? "dark" : "light" });
    expect(document.documentElement.dataset.theme).toBe(dark ? "dark" : "light");
    expect(document.documentElement.style.colorScheme).toBe(dark ? "dark" : "light");
    expect(storage.setItem).not.toHaveBeenCalled();
  });

  it("responds to OS changes only in system mode, without writing storage", () => {
    const { store, changeSystem, storage } = boot();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    changeSystem(true);
    expect(store.getSnapshot().resolvedTheme).toBe("dark");
    changeSystem(false);
    expect(store.getSnapshot().resolvedTheme).toBe("light");
    expect(listener).toHaveBeenCalledTimes(2);
    expect(storage.setItem).not.toHaveBeenCalled();
    unsubscribe();
    changeSystem(true);
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it.each(["light", "dark"] as const)("restores and forces saved %s regardless of OS", (preference) => {
    const { store, changeSystem } = boot(preference, preference === "light");
    changeSystem(false);
    changeSystem(true);
    expect(store.getSnapshot()).toEqual({ preference, resolvedTheme: preference });
    expect(document.documentElement.dataset.themePreference).toBe(preference);
  });

  it("persists manual choices once and resolves the current OS when returning to system", () => {
    const { store, storage, changeSystem } = boot(null, true);
    store.setPreference("light");
    store.setPreference("light");
    expect(storage.setItem).toHaveBeenCalledTimes(1);
    expect(storage.setItem).toHaveBeenLastCalledWith("alpha-theme", "light");
    changeSystem(false);
    changeSystem(true);
    expect(store.getSnapshot().resolvedTheme).toBe("light");
    store.setPreference("dark");
    expect(storage.setItem).toHaveBeenLastCalledWith("alpha-theme", "dark");
    store.setPreference("system");
    expect(storage.setItem).toHaveBeenLastCalledWith("alpha-theme", "system");
    expect(store.getSnapshot()).toEqual({ preference: "system", resolvedTheme: "dark" });
    expect(boot("system", false).store.getSnapshot().resolvedTheme).toBe("light");
  });

  it("normalizes invalid storage and works when storage is unavailable", () => {
    expect(boot("unknown", true).store.getSnapshot().preference).toBe("system");
    const { store } = boot(null, true, true);
    expect(() => store.setPreference("light")).not.toThrow();
    expect(store.getSnapshot().resolvedTheme).toBe("light");
  });

  it("syncs other tabs and storage clearing without write-back loops", () => {
    const { store, changeStorage, storage } = boot(null, true);
    changeStorage("light");
    expect(store.getSnapshot().resolvedTheme).toBe("light");
    changeStorage("dark", "unrelated");
    expect(store.getSnapshot().preference).toBe("light");
    changeStorage(null, null);
    expect(store.getSnapshot()).toEqual({ preference: "system", resolvedTheme: "dark" });
    expect(storage.setItem).not.toHaveBeenCalled();
  });

  it("updates browser chrome along with the document", () => {
    const meta = document.createElement("meta");
    meta.name = "theme-color";
    document.head.append(meta);
    const { store } = boot("dark");
    expect(meta.content).toBe("#040b1c");
    store.setPreference("light");
    expect(meta.content).toBe("#f4f7fc");
    meta.remove();
  });
});

describe("theme control", () => {
  it("shows all three localized choices and keeps selection separate from the rendered theme", () => {
    const runtime = boot(null, true);
    window.alphaTheme = runtime.store;
    const view = render(<ThemeSwitcher lang="en" />);
    expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("system");
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getByRole("status")).toHaveTextContent("System (Dark)");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "light" } });
    expect(screen.getByRole("option", { name: "Light" })).toHaveProperty("selected", true);
    act(() => runtime.changeSystem(true));
    expect(screen.getByRole("status")).toHaveTextContent("Light (Light)");
    view.rerender(<ThemeSwitcher lang="ar" />);
    expect(screen.getByRole("combobox", { name: "المظهر" })).toHaveValue("light");
    expect(screen.getByRole("option", { name: "النظام" })).toBeInTheDocument();
  });

  it("retains preference when the control unmounts and remounts", () => {
    window.alphaTheme = boot().store;
    const first = render(<ThemeSwitcher lang="en" />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "dark" } });
    first.unmount();
    render(<ThemeSwitcher lang="en" />);
    expect(screen.getByRole("combobox")).toHaveValue("dark");
  });

  it("existing language/history persistence also tolerates blocked storage", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readStoredValue("alpha-language")).toBeNull();
    expect(() => writeStoredValue("alpha-language", "en")).not.toThrow();
  });
});
