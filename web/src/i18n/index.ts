import ar from "./ar";
import en from "./en";

export type Language = "ar" | "en";
export const dictionaries = { ar, en };
export function translate(language: Language, key: keyof typeof ar): string {
  return dictionaries[language][key];
}
