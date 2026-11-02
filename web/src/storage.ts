// Preferences and convenience history must not prevent rendering in private/blocked storage.
export function readStoredValue(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

export function writeStoredValue(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* Optional persistence. */ }
}
