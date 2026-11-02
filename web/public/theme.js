/* Runs before styles/React. This is the single theme store for startup and the UI. */
(() => {
  const key = "alpha-theme";
  const normalize = (value) => value === "light" || value === "dark" ? value : "system";
  let saved;
  try { saved = window.localStorage.getItem(key); } catch { /* Storage may be blocked. */ }
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  const listeners = new Set();
  let snapshot;

  function apply(preference) {
    const resolvedTheme = preference === "system" ? (media?.matches ? "dark" : "light") : preference;
    if (snapshot?.preference === preference && snapshot.resolvedTheme === resolvedTheme) return;
    snapshot = Object.freeze({ preference, resolvedTheme });
    const root = document.documentElement;
    root.dataset.theme = resolvedTheme;
    root.dataset.themePreference = preference;
    root.style.colorScheme = resolvedTheme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content", resolvedTheme === "dark" ? "#040b1c" : "#f4f7fc",
    );
    listeners.forEach((listener) => listener());
  }

  apply(normalize(saved));
  const onSystemChange = () => {
    if (snapshot.preference === "system") apply("system");
  };
  media?.addEventListener("change", onSystemChange);
  window.addEventListener("storage", (event) => {
    try {
      if (event.storageArea !== window.localStorage) return;
    } catch { return; }
    if (event.key === key || event.key === null) apply(normalize(event.newValue));
  });

  window.alphaTheme = {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setPreference(value) {
      const preference = normalize(value);
      if (preference === snapshot.preference) return;
      apply(preference);
      try { window.localStorage.setItem(key, preference); } catch { /* Keep working in memory. */ }
    },
  };
})();
