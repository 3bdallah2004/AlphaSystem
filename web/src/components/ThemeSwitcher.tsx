import { Icon } from "@mdi/react";
import { mdiMonitor, mdiWeatherNight, mdiWhiteBalanceSunny } from "@mdi/js";
import { translate, type Language } from "../i18n";
import { useTheme, type ThemePreference } from "../theme";

const icons = { system: mdiMonitor, light: mdiWhiteBalanceSunny, dark: mdiWeatherNight };

export default function ThemeSwitcher({ lang }: { lang: Language }) {
  const { preference, resolvedTheme, setPreference } = useTheme();
  const labels = {
    system: translate(lang, "themeSystem"),
    light: translate(lang, "themeLight"),
    dark: translate(lang, "themeDark"),
  };
  const description = `${translate(lang, "theme")}: ${labels[preference]} (${labels[resolvedTheme]})`;
  return (
    <label className="theme-switcher" dir={lang === "ar" ? "rtl" : "ltr"} title={description}>
      <Icon path={icons[preference]} size={0.85} aria-hidden="true" />
      <select aria-label={translate(lang, "theme")} value={preference}
        onChange={(event) => setPreference(event.target.value as ThemePreference)}>
        <option value="system">{labels.system}</option>
        <option value="light">{labels.light}</option>
        <option value="dark">{labels.dark}</option>
      </select>
      <span className="sr-only" role="status">{description}</span>
    </label>
  );
}
