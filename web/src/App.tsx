import { Icon } from "@mdi/react";
import {
  mdiAlertCircleOutline,
  mdiArrowLeft,
  mdiArrowRight,
  mdiCalendar,
  mdiChartBar,
  mdiCheckCircleOutline,
  mdiChevronDown,
  mdiChevronLeft,
  mdiChevronRight,
  mdiDownload,
  mdiFileDocumentOutline,
  mdiClose,
  mdiEmail,
  mdiGithub,
  mdiHistory,
  mdiMapMarkerOutline,
  mdiMenu,
  mdiMessageTextOutline,
  mdiMagnify,
  mdiPaperclip,
  mdiPlus,
  mdiTranslate,
  mdiWhatsapp,
} from "@mdi/js";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Component,
  createContext,
  lazy,
  Suspense,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ErrorInfo, FormEvent, ReactNode } from "react";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useBlocker,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, Attachment, CaseDetail, CaseSummary, ChatMessage, GeoPoint } from "./api/client";
import { Language, translate } from "./i18n";

const MapCanvas = lazy(() => import("./components/MapCanvas"));
const LocationPicker = lazy(() => import("./components/LocationPicker"));
const CASE_TYPES = ["عام", "سرقة", "احتيال مالي", "جرائم إلكترونية", "اعتداء", "فقدان أو اختفاء", "أخرى"];
const CASE_TYPE_EN: Record<string, string> = {
  عام: "General", سرقة: "Theft", "احتيال مالي": "Financial fraud", "جرائم إلكترونية": "Cybercrime",
  اعتداء: "Assault", "فقدان أو اختفاء": "Missing person", أخرى: "Other",
};
const caseTypeLabel = (value: string, lang: Language) => lang === "en" ? CASE_TYPE_EN[value] ?? value : value;
const SEARCH_HISTORY_KEY = "alpha-search-history";
const SEARCH_HISTORY_LIMIT = 8;

function loadSearchHistory(): string[] {
  const saved = localStorage.getItem(SEARCH_HISTORY_KEY);
  if (!saved) return [];
  try {
    const parsed: unknown = JSON.parse(saved);
    return Array.isArray(parsed)
      ? parsed.filter((query): query is string => typeof query === "string" && query.trim().length > 0).slice(0, SEARCH_HISTORY_LIMIT)
      : [];
  } catch {
    return [];
  }
}

type Locale = { lang: Language; t: (key: Parameters<typeof translate>[1]) => string; toggle: () => void };
const LocaleContext = createContext<Locale | null>(null);

function useLocale(): Locale {
  const locale = useContext(LocaleContext);
  if (!locale) throw new Error("LocaleProvider is missing");
  return locale;
}

function LocaleProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const stored = localStorage.getItem("alpha-language");
  const lang = (params.get("lang") === "en" || params.get("lang") === "ar"
    ? params.get("lang")
    : stored === "en" ? "en" : "ar") as Language;

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    localStorage.setItem("alpha-language", lang);
  }, [lang]);

  useEffect(() => {
    if (!params.has("lang")) {
      const next = new URLSearchParams(params);
      next.set("lang", lang);
      setParams(next, { replace: true });
    }
  }, [lang, params, setParams]);

  const value = useMemo<Locale>(() => ({
    lang,
    t: (key) => translate(lang, key),
    toggle: () => {
      const next = new URLSearchParams(params);
      next.set("lang", lang === "ar" ? "en" : "ar");
      setParams(next);
    },
  }), [lang, params, setParams]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

function localizedPath(path: string, search: string, lang: Language) {
  const [pathname, routeQuery = ""] = path.split("?", 2);
  const params = new URLSearchParams(search);
  params.delete("step");
  params.delete("flow");
  params.delete("suggest_failed");
  new URLSearchParams(routeQuery).forEach((value, key) => params.set(key, value));
  params.set("lang", lang);
  return `${pathname}?${params.toString()}`;
}

function App() {
  return (
    <LocaleProvider>
      <LocaleContext.Consumer>
        {(locale) => (
          <AppErrorBoundary lang={locale?.lang ?? "ar"}>
            <Routes>
              <Route element={<AppShell />}>
                <Route index element={<Navigate to="/cases" replace />} />
                <Route path="/cases" element={<RegisterPage />} />
                <Route path="/cases/map" element={<MapPage />} />
                <Route path="/cases/chart" element={<CaseChartPage />} />
                <Route path="/cases/new" element={<CaseEditor />} />
                <Route path="/cases/:id/edit" element={<CaseEditor />} />
                <Route path="/cases/:id" element={<Workspace mode="report" />} />
                <Route path="/cases/:id/chat" element={<Workspace mode="chat" />} />
                <Route path="/cases/:id/sources" element={<Workspace mode="sources" />} />
                <Route path="/cases/:id/chat/sources" element={<Workspace mode="chat-sources" />} />
                <Route path="/about" element={<AboutPage />} />
                <Route path="*" element={<Navigate to="/cases" replace />} />
              </Route>
            </Routes>
          </AppErrorBoundary>
        )}
      </LocaleContext.Consumer>
    </LocaleProvider>
  );
}

class AppErrorBoundary extends Component<{ children: ReactNode; lang: Language }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Application rendering failed", error, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    const english = this.props.lang === "en";
    return (
      <main className="app-error" role="alert">
        <Icon path={mdiAlertCircleOutline} size={1.4} />
        <h1>{english ? "Something went wrong" : "حدث خطأ غير متوقع"}</h1>
        <p>{english ? "Reload the page to continue." : "أعد تحميل الصفحة للمتابعة."}</p>
        <button className="button button-primary" onClick={() => window.location.reload()}>
          {english ? "Reload page" : "إعادة تحميل الصفحة"}
        </button>
      </main>
    );
  }
}

function AppShell() {
  const { lang, t, toggle } = useLocale();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuClosing, setMenuClosing] = useState(false);
  const menuCloseTimer = useRef<number | null>(null);
  const isAbout = location.pathname === "/about";
  const openMenu = () => {
    if (menuCloseTimer.current !== null) window.clearTimeout(menuCloseTimer.current);
    setMenuClosing(false);
    setMenuOpen(true);
  };
  const closeMenu = () => {
    if (!menuOpen || menuClosing) return;
    setMenuClosing(true);
    menuCloseTimer.current = window.setTimeout(() => {
      setMenuOpen(false);
      setMenuClosing(false);
      menuCloseTimer.current = null;
    }, 190);
  };

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen, menuClosing]);

  useEffect(() => () => {
    if (menuCloseTimer.current !== null) window.clearTimeout(menuCloseTimer.current);
  }, []);

  return (
    <div className="app">
      <header className={`topbar ${isAbout ? "topbar-about" : ""}`} dir="ltr">
        <Link to={localizedPath("/cases", location.search, lang)} className="brand">
          <svg className="brand-mark" aria-hidden="true" viewBox="0 0 100 96">
            <defs>
              <linearGradient id="alpha-mark-left" x1=".1" x2=".5" y1="0" y2="1">
                <stop offset="0" stopColor="#3aa6ff" /><stop offset="1" stopColor="#0a52f0" />
              </linearGradient>
              <linearGradient id="alpha-mark-right" x1="0" x2=".6" y1="0" y2="1">
                <stop offset="0" stopColor="#1e7bff" /><stop offset="1" stopColor="#0836c8" />
              </linearGradient>
            </defs>
            <path d="M50 2 58 17 21 90H3L10 76Z" fill="url(#alpha-mark-left)" />
            <path d="m50 2 47 90H72L38 40Z" fill="url(#alpha-mark-right)" />
            <path d="M19 74h42l-9 16H8Z" fill="url(#alpha-mark-left)" />
          </svg>
          <span><strong>{t("brand")}</strong><small>{t("tagline")}</small></span>
        </Link>
        <div className="top-actions">
          {!isAbout && <ServiceStatus />}
          {!isAbout && <button className="button button-primary button-small new-case-button" onClick={() => {
            navigate(localizedPath("/cases/new?step=1", location.search, lang));
          }}>
            <Icon path={mdiPlus} size={0.8} /><span>{t("newCase")}</span>
          </button>}
          <div className="language-switch" role="group" aria-label={t("language")}>
            <button className={lang === "ar" ? "active" : ""} aria-pressed={lang === "ar"}
              onClick={() => lang !== "ar" && toggle()}>العربية</button>
            <button className={lang === "en" ? "active" : ""} aria-pressed={lang === "en"}
              onClick={() => lang !== "en" && toggle()}>English</button>
          </div>
          {!isAbout && <button className="icon-button mobile-menu-button" aria-label={t("menu")} aria-expanded={menuOpen}
            onClick={openMenu}><Icon path={mdiMenu} size={1} /></button>
          }
        </div>
      </header>
      <main className={`main-content ${isAbout ? "main-content-about" : ""}`}>
        <div className="route-view" key={location.pathname}><Outlet /></div>
      </main>
      {menuOpen && <div className={`mobile-menu-backdrop ${menuClosing ? "menu-closing" : ""}`} onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeMenu();
      }}>
        <section className="mobile-menu-panel" dir={lang} role="dialog" aria-modal="true" aria-label={t("menu")}>
          <div className="mobile-menu-heading"><strong>{t("menu")}</strong>
            <button className="icon-button" aria-label={t("close")} onClick={closeMenu}><Icon path={mdiClose} size={0.9} /></button>
          </div>
          <Link onClick={closeMenu} to={localizedPath("/about", location.search, lang)}>{t("about")}</Link>
          <Link onClick={closeMenu} to={localizedPath("/cases/new?step=1", location.search, lang)}>{t("newCase")}</Link>
          <div className="mobile-menu-service"><ServiceStatus /></div>
          <button className="button button-secondary" onClick={() => { closeMenu(); toggle(); }}>
            <Icon path={mdiTranslate} size={0.9} />{t("language")}
          </button>
        </section>
      </div>}
    </div>
  );
}

function ServiceStatus() {
  const { lang, t } = useLocale();
  const { data, isError } = useQuery({
    queryKey: ["health", lang],
    queryFn: async () => {
      const response = await fetch(`/api/health?lang=${lang}`);
      if (!response.ok) throw new Error("Health request failed");
      return response.json() as Promise<{ level: string; message: string }>;
    },
    refetchInterval: 60_000,
  });
  const level = isError ? "error" : data?.level ?? "checking";
  return (
    <span className={`service-status service-${level}`} title={data?.message ?? t("service")}>
      <i /> <span>{t("service")}</span>
    </span>
  );
}

function PageHeading({ eyebrow, title, detail, children }: {
  eyebrow?: string; title: string; detail?: string; children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1>{detail && <p>{detail}</p>}</div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}

function CaseStatus({ value }: { value: string }) {
  const { t } = useLocale();
  const keys: Record<string, Parameters<typeof translate>[1]> = {
    draft: "draft", analyzing: "analyzing", analyzed: "analyzed", failed: "failed",
  };
  return <span className={`status-pill status-${value}`}>{t(keys[value] ?? "draft")}</span>;
}

function Severity({ value }: { value: string | null }) {
  const { t } = useLocale();
  if (!value) return <span className="severity-none">—</span>;
  const key = value === "high" || value === "medium" || value === "low" ? value : "low";
  return <span className={`severity severity-${key}`}><i />{t(key)}</span>;
}

function SearchFilters({ compact = false }: { compact?: boolean }) {
  const { lang, t } = useLocale();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const [history, setHistory] = useState(loadSearchHistory);
  const historyRef = useRef(history);

  useEffect(() => setText(params.get("q") ?? ""), [params]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const next = new URLSearchParams(params);
      const query = text.trim();
      if (query) next.set("q", query);
      else next.delete("q");
      if (next.toString() !== params.toString()) setParams(next, { replace: true });

      if (query && query !== (params.get("q") ?? "")) {
        const updatedHistory = [
          query,
          ...historyRef.current.filter((item) => item.toLocaleLowerCase() !== query.toLocaleLowerCase()),
        ].slice(0, SEARCH_HISTORY_LIMIT);
        historyRef.current = updatedHistory;
        setHistory(updatedHistory);
        localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(updatedHistory));
      }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [text, params, setParams]);

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  return (
    <div className={`search-filters ${compact ? "filters-compact" : ""}`}>
      <label className="search-field">
        <Icon path={mdiMagnify} size={0.9} />
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={t("search")}
          list={`search-history-${compact ? "compact" : "register"}`}
          autoComplete="off"
        />
        <datalist id={`search-history-${compact ? "compact" : "register"}`}>
          {history.map((query) => <option key={query} value={query} />)}
        </datalist>
      </label>
      <select aria-label={t("type")} value={params.get("type") ?? ""} onChange={(event) => setFilter("type", event.target.value)}>
        <option value="">{t("type")} · {t("all")}</option>
        {CASE_TYPES.map((value) => <option key={value} value={value}>{caseTypeLabel(value, lang)}</option>)}
      </select>
      <select aria-label={t("status")} value={params.get("status") ?? ""} onChange={(event) => setFilter("status", event.target.value)}>
        <option value="">{t("status")} · {t("all")}</option>
        <option value="analyzed">{t("analyzed")}</option><option value="analyzing">{t("analyzing")}</option>
        <option value="draft">{t("draft")}</option><option value="failed">{t("failed")}</option>
      </select>
      <select aria-label={t("severity")} value={params.get("severity") ?? ""} onChange={(event) => setFilter("severity", event.target.value)}>
        <option value="">{t("severity")} · {t("all")}</option>
        <option value="high">{t("high")}</option><option value="medium">{t("medium")}</option><option value="low">{t("low")}</option>
      </select>
    </div>
  );
}

function useCaseResults() {
  const { lang } = useLocale();
  const [params] = useSearchParams();
  const query = new URLSearchParams(params);
  query.delete("lang");
  return useQuery({
    queryKey: ["cases", query.toString(), lang],
    queryFn: () => api.cases(query, lang),
  });
}

type CaseStats = {
  total?: number;
  by_status?: Record<string, number>;
  by_type_severity?: [string, string, number][];
};

function typeSeverityRows(stats: CaseStats | undefined, lang: Language) {
  return CASE_TYPES.map((type) => ({
    key: type,
    label: caseTypeLabel(type, lang),
    counts: {
      high: stats?.by_type_severity?.find(([caseType, severity]) => caseType === type && severity === "high")?.[2] ?? 0,
      medium: stats?.by_type_severity?.find(([caseType, severity]) => caseType === type && severity === "medium")?.[2] ?? 0,
      low: stats?.by_type_severity?.find(([caseType, severity]) => caseType === type && severity === "low")?.[2] ?? 0,
      unknown: stats?.by_type_severity?.find(([caseType, severity]) => caseType === type && severity === "unknown")?.[2] ?? 0,
    },
  }));
}

function RegisterPage() {
  const { lang, t } = useLocale();
  const location = useLocation();
  const results = useCaseResults();
  const cases = results.data?.cases ?? [];
  const stats = results.data?.stats as CaseStats | undefined;
  const lastCaseId = localStorage.getItem("alpha-last-case");
  const lastCaseName = sessionStorage.getItem("alpha-last-case-name");
  return (
    <section className="register-page">
      <PageHeading eyebrow="ALPHA / REGISTER" title={t("allCases")} />
      <div className="register-summary" aria-label={t("caseSummary")}>
        <span className="register-total">{stats?.total ?? results.data?.count ?? 0} {t("casesInRegister")}</span>
        <SummaryStat status="analyzed" label={t("analyzed")} value={stats?.by_status?.analyzed ?? 0} />
        <SummaryStat status="analyzing" label={t("analyzing")} value={stats?.by_status?.analyzing ?? 0} />
        <SummaryStat status="draft" label={t("drafts")} value={stats?.by_status?.draft ?? 0} />
        <SummaryStat status="failed" label={t("needsReanalysis")} value={stats?.by_status?.failed ?? 0} />
      </div>
      <div className="register-actions">
        {lastCaseId && <Link className="continue-case" to={localizedPath(`/cases/${lastCaseId}`, location.search, lang)}>
          <Icon path={mdiHistory} size={0.85} />{t("continueLastCase")}
          <span>{lastCaseName || `#${lastCaseId}`}</span>
        </Link>}
        <div className="register-action-buttons">
          <a className="button button-secondary button-small" href={`/api/cases/export.csv?lang=${lang}`}>
            <Icon path={mdiDownload} size={0.8} />{t("exportCsv")}
          </a>
          <Link className="button button-secondary button-small" to={localizedPath("/cases/map", location.search, lang)}>
            <Icon path={mdiMapMarkerOutline} size={0.8} />{t("map")}
          </Link>
          <Link className="button button-secondary button-small" to={localizedPath("/cases/chart", location.search, lang)}>
            <Icon path={mdiChartBar} size={0.8} />{t("chart")}
          </Link>
        </div>
      </div>
      <SearchFilters />
      <div className="register-result-meta">
        <span>{t("showingCases")} <strong>{cases.length}</strong> {t("ofCases")} <strong>{results.data?.count ?? 0}</strong></span>
        <Link to={localizedPath("/cases/map", location.search, lang)}>
          <Icon path={mdiMapMarkerOutline} size={0.75} />{t("mapCoverage")}
        </Link>
      </div>
      {results.isPending ? <Loading /> : results.isError ? <ErrorPanel message={t("error")} /> : cases.length === 0 ? (
        <EmptyState title={t("noCases")} />
      ) : (
        <>
          <div className="table-wrap desktop-register">
            <table className="case-table">
              <thead><tr><th>{t("caseNumber")}</th><th>{t("caseName")}</th><th>{t("type")}</th>
                <th>{t("status")}</th><th>{t("severity")}</th><th>{t("attachments")}</th>
                <th>{t("addedAt")}</th><th>{t("open")}</th></tr></thead>
              <tbody>{cases.map((item) => (
                <CaseTableRow key={item.id} item={item} search={location.search} lang={lang} />
              ))}</tbody>
            </table>
          </div>
          <div className="case-cards">{cases.map((item) =>
            <CaseCard key={item.id} item={item} search={location.search} lang={lang} />)}</div>
        </>
      )}
    </section>
  );
}

function CaseTypeSeverityChart({ title, rows }: {
  title: string;
  rows: { key: string; label: string; counts: Record<"high" | "medium" | "low" | "unknown", number> }[];
}) {
  const { t } = useLocale();
  const severities = [
    ["high", t("high"), "severity-high"],
    ["medium", t("medium"), "severity-medium"],
    ["low", t("low"), "severity-low"],
    ["unknown", t("unclassified"), "severity-unknown"],
  ] as const;
  const maxCount = Math.max(1, ...rows.map(({ counts }) => Object.values(counts).reduce((sum, count) => sum + count, 0)));

  return (
    <section className="case-chart case-type-severity-chart" role="group" aria-label={title}>
      <h2>{title}</h2>
      <div className="severity-chart-legend">
        {severities.map(([key, label, color]) => (
          <span key={key}><i className={color} />{label}</span>
        ))}
      </div>
      <div className="case-type-severity-rows">
        {rows.map(({ key, label, counts }) => {
          const total = Object.values(counts).reduce((sum, count) => sum + count, 0);
          return (
            <div
              className="case-type-severity-row"
              key={key}
              role="group"
              aria-label={`${label}: ${severities.map(([severity, severityLabel]) => `${severityLabel} ${counts[severity]}`).join(", ")}`}
            >
              <div className="case-type-severity-heading">
                <span className="case-chart-label">{label}</span>
                <strong>{total}</strong>
              </div>
              <div className="severity-stacked-track" aria-hidden="true">
                {severities.map(([severity, , color]) => counts[severity] > 0 && (
                  <span
                    key={severity}
                    className={color}
                    style={{ width: `${counts[severity] / maxCount * 100}%` }}
                  />
                ))}
              </div>
              <div className="case-type-severity-counts">
                {severities.map(([severity, , color]) => (
                  <span key={severity} className={color}>{counts[severity]}</span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SummaryStat({ status, label, value }: { status: string; label: string; value: number }) {
  return <span className={`summary-stat summary-stat-${status}`}><i /><span><strong>{value}</strong> {label}</span></span>;
}

function rememberCase(id: number) {
  localStorage.setItem("alpha-last-case", String(id));
}

function prefetchCase(client: ReturnType<typeof useQueryClient>, id: number, lang: Language) {
  return client.prefetchQuery({
    queryKey: ["case", String(id), lang],
    queryFn: () => api.case(id, lang),
  });
}

function CaseCard({ item, search, lang }: { item: CaseSummary; search: string; lang: Language }) {
  const { t } = useLocale();
  const client = useQueryClient();
  const prefetch = () => void prefetchCase(client, item.id, lang);
  return (
    <Link className="case-card" to={localizedPath(`/cases/${item.id}`, search, lang)}
      onMouseEnter={prefetch} onFocus={prefetch} onClick={() => rememberCase(item.id)}>
      <div className="case-card-top"><span className="ltr">{item.case_number || `#${item.id}`}</span><CaseStatus value={item.status} /></div>
      <strong>{item.case_name || t("untitled")}</strong>
      <div className="case-card-facts"><span>{caseTypeLabel(item.case_type, lang)}</span><Severity value={item.severity} /></div>
      <div className="case-card-extra"><span><Icon path={mdiPaperclip} size={0.75} />{item.attachment_count ?? 0}</span>
        <time className="ltr">{item.timestamp.slice(0, 10)}</time></div>
      <span className="case-card-open">{t("open")}<Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.8} /></span>
    </Link>
  );
}

function CaseTableRow({ item, search, lang }: { item: CaseSummary; search: string; lang: Language }) {
  const { t } = useLocale();
  const client = useQueryClient();
  const prefetch = () => void prefetchCase(client, item.id, lang);
  return (
    <tr>
      <td className="ltr muted-cell">{item.case_number || `#${item.id}`}</td>
      <td><strong>{item.case_name || t("untitled")}</strong><small>{item.location || t("noLocation")}</small></td>
      <td>{caseTypeLabel(item.case_type, lang)}</td><td><CaseStatus value={item.status} /></td>
      <td><Severity value={item.severity} /></td>
      <td><span className="table-attachment-count"><Icon path={mdiPaperclip} size={0.75} />{item.attachment_count ?? 0}</span></td>
      <td className="ltr muted-cell">{item.timestamp.slice(0, 10)}</td>
      <td><Link className="table-open" onMouseEnter={prefetch} onFocus={prefetch} onClick={() => rememberCase(item.id)}
        to={localizedPath(`/cases/${item.id}`, search, lang)}>{t("open")} <Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.8} /></Link></td>
    </tr>
  );
}

function Workspace({ mode }: { mode: "report" | "chat" | "sources" | "chat-sources" }) {
  const { id = "" } = useParams();
  const { lang, t } = useLocale();
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const results = useCaseResults();
  const caseQuery = useQuery({
    queryKey: ["case", id, lang],
    queryFn: () => api.case(id, lang),
    refetchInterval: (query) => query.state.data?.status === "analyzing" ? 3000 : false,
  });
  const current = caseQuery.data;
  const resultCases = results.data?.cases ?? [];
  const index = resultCases.findIndex((item) => String(item.id) === id);
  const previous = index > 0 ? resultCases[index - 1] : undefined;
  const next = index >= 0 && index < resultCases.length - 1 ? resultCases[index + 1] : undefined;
  const querySuffix = location.search;
  const backTarget = localizedPath("/cases", querySuffix, lang);
  const isSources = mode === "sources" || mode === "chat-sources";
  const previousId = previous?.id;
  const nextId = next?.id;

  useEffect(() => {
    if (current) {
      localStorage.setItem("alpha-last-case", String(current.id));
      if (current.case_name) sessionStorage.setItem("alpha-last-case-name", current.case_name);
    }
  }, [current?.case_name, current?.id]);

  useEffect(() => {
    for (const neighborId of [previousId, nextId]) {
      if (neighborId !== undefined) {
        void prefetchCase(client, neighborId, lang);
      }
    }
  }, [client, lang, nextId, previousId]);

  const analyze = useMutation({
    mutationFn: () => api.analyze(Number(id), lang),
    onSuccess: () => client.invalidateQueries({ queryKey: ["case", id] }),
  });
  const remove = useMutation({
    mutationFn: () => api.removeCase(Number(id), lang),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["cases"] });
      navigate(backTarget);
    },
  });

  if (caseQuery.isPending) return <Loading />;
  if (!current || caseQuery.isError) return <ErrorPanel message={t("error")} />;

  const sourcesPath = mode === "chat" || mode === "chat-sources"
    ? `/cases/${id}/chat/sources` : `/cases/${id}/sources`;
  const dataPath = mode === "chat" || mode === "chat-sources"
    ? `/cases/${id}/chat` : `/cases/${id}`;

  return (
    <div className={`workspace ${isSources ? "workspace-sources" : ""}`}>
      <aside className="results-pane">
        <div className="pane-title"><span>{t("results")}</span><span className="count-badge">{resultCases.length}</span></div>
        <SearchFilters compact />
        <div className="result-list">
          {resultCases.map((item) => (
            <Link key={item.id} aria-current={String(item.id) === id ? "page" : undefined}
              className={`result-item ${String(item.id) === id ? "selected" : ""}`}
              onClick={() => rememberCase(item.id)}
              to={localizedPath(`/cases/${item.id}${mode === "chat" || mode === "chat-sources" ? "/chat" : ""}`, querySuffix, lang)}>
              <div className="result-top"><span className="ltr">{item.case_number || `#${item.id}`}</span><CaseStatus value={item.status} /></div>
              <strong>{item.case_name || t("untitled")}</strong>
              <small>{item.case_type} · {item.location || t("noLocation")}</small>
            </Link>
          ))}
        </div>
        <Link className="map-shortcut" to={localizedPath("/cases/map", querySuffix, lang)}>
          <Icon path={mdiMapMarkerOutline} size={0.9} />{t("map")}<Icon path={mdiChevronLeft} size={0.8} />
        </Link>
      </aside>
      <section className="case-pane">
        {isSources ? (
          <>
            <div className="case-header">
              <Link className="back-link" to={backTarget}><Icon path={lang === "ar" ? mdiArrowRight : mdiArrowLeft} size={0.8} />{t("backResults")}</Link>
              <div className="case-title-row">
                <div>
                  <div className="eyebrow ltr">{current.case_number || `CASE-${current.id}`}</div>
                  <h1>{current.case_name || t("untitled")}</h1>
                </div>
                <div className="case-header-actions">
                  <button className="icon-button" title={t("previous")} disabled={!previous}
                    onClick={() => {
                      if (!previous) return;
                      rememberCase(previous.id);
                      navigate(localizedPath(`/cases/${previous.id}${mode === "chat-sources" ? "/chat/sources" : "/sources"}`, querySuffix, lang));
                    }}>
                    <Icon path={lang === "ar" ? mdiChevronRight : mdiChevronLeft} size={0.9} />
                  </button>
                  <button className="icon-button" title={t("next")} disabled={!next}
                    onClick={() => {
                      if (!next) return;
                      rememberCase(next.id);
                      navigate(localizedPath(`/cases/${next.id}${mode === "chat-sources" ? "/chat/sources" : "/sources"}`, querySuffix, lang));
                    }}>
                    <Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.9} />
                  </button>
                  <Link className="button button-secondary button-small" to={localizedPath(`/cases/${id}/edit?step=2&flow=review`, querySuffix, lang)}>{t("edit")}</Link>
                </div>
              </div>
              <div className="fact-line"><span>{caseTypeLabel(current.case_type, lang)}</span><span><Icon path={mdiMapMarkerOutline} size={0.75} />{current.location || t("noLocation")}</span>
                {current.date && <span><Icon path={mdiCalendar} size={0.75} />{current.date}</span>}
                <CaseStatus value={current.status} /><Severity value={current.severity} /></div>
            </div>
            <div className={`source-layout ${mode === "chat-sources" ? "source-layout-chat" : ""}`}>
              {mode === "chat-sources" ? (
                <>
                  <div className="source-main" dir={lang}>
                    <div className="mode-tabs">
                      <NavLink end to={localizedPath(`/cases/${id}`, querySuffix, lang)}><Icon path={mdiFileDocumentOutline} size={0.8} />{t("report")}</NavLink>
                      <NavLink className="active" to={localizedPath(`/cases/${id}/chat`, querySuffix, lang)}><Icon path={mdiMessageTextOutline} size={0.8} />{t("conversation")}<span className="tab-count">{current.message_count}</span></NavLink>
                      <Link to={localizedPath(sourcesPath, querySuffix, lang)}><Icon path={mdiPaperclip} size={0.8} />{t("sources")}<span className="tab-count">{current.attachments.length}</span></Link>
                    </div>
                    <Conversation caseId={Number(id)} detail={current} />
                  </div>
                  <aside className="source-sidebar" dir={lang}>
                    <SourcesInspector caseId={Number(id)} caseDetail={current} returnTo={dataPath} />
                  </aside>
                </>
              ) : (
                <>
                  <aside className="source-sidebar" dir={lang}>
                    <SourcesInspector caseId={Number(id)} caseDetail={current} returnTo={dataPath} />
                  </aside>
                  <div className="source-main" dir={lang}>
                    <div className="mode-tabs">
                      <NavLink end className="active" to={localizedPath(`/cases/${id}`, querySuffix, lang)}><Icon path={mdiFileDocumentOutline} size={0.8} />{t("report")}</NavLink>
                      <NavLink to={localizedPath(`/cases/${id}/chat`, querySuffix, lang)}><Icon path={mdiMessageTextOutline} size={0.8} />{t("conversation")}<span className="tab-count">{current.message_count}</span></NavLink>
                      <Link to={localizedPath(sourcesPath, querySuffix, lang)}><Icon path={mdiPaperclip} size={0.8} />{t("sources")}<span className="tab-count">{current.attachments.length}</span></Link>
                    </div>
                    <ReportView caseDetail={current} onAnalyze={() => analyze.mutate()} busy={analyze.isPending}
                      onDelete={() => window.confirm(t("deleteConfirm")) && remove.mutate()} />
                  </div>
                </>
              )}
            </div>
          </>
        ) : (
          <>
            <div className="mobile-result-nav">
              <Link className="back-link" to={backTarget}>
                <Icon path={lang === "ar" ? mdiArrowRight : mdiArrowLeft} size={0.8} />{t("backResults")}
              </Link>
              <div className="mobile-result-pager">
                <button className="icon-button" title={t("previous")} aria-label={t("previous")} disabled={!previous}
                  onClick={() => {
                    if (!previous) return;
                    rememberCase(previous.id);
                    navigate(localizedPath(`/cases/${previous.id}${mode === "chat" ? "/chat" : ""}`, querySuffix, lang));
                  }}>
                  <Icon path={lang === "ar" ? mdiChevronRight : mdiChevronLeft} size={0.85} />
                </button>
                <span>{index >= 0 ? index + 1 : "–"} / {resultCases.length}</span>
                <button className="icon-button" title={t("next")} aria-label={t("next")} disabled={!next}
                  onClick={() => {
                    if (!next) return;
                    rememberCase(next.id);
                    navigate(localizedPath(`/cases/${next.id}${mode === "chat" ? "/chat" : ""}`, querySuffix, lang));
                  }}>
                  <Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.85} />
                </button>
              </div>
            </div>
            <div className="case-header">
              <Link className="back-link" to={backTarget}><Icon path={lang === "ar" ? mdiArrowRight : mdiArrowLeft} size={0.8} />{t("backResults")}</Link>
              <div className="case-title-row">
                <div>
                  <div className="eyebrow ltr">{current.case_number || `CASE-${current.id}`}</div>
                  <h1>{current.case_name || t("untitled")}</h1>
                </div>
                <div className="case-header-actions">
                  <button className="icon-button" title={t("previous")} disabled={!previous}
                    onClick={() => {
                      if (!previous) return;
                      rememberCase(previous.id);
                      navigate(localizedPath(`/cases/${previous.id}${mode === "chat" ? "/chat" : ""}`, querySuffix, lang));
                    }}>
                    <Icon path={lang === "ar" ? mdiChevronRight : mdiChevronLeft} size={0.9} />
                  </button>
                  <button className="icon-button" title={t("next")} disabled={!next}
                    onClick={() => {
                      if (!next) return;
                      rememberCase(next.id);
                      navigate(localizedPath(`/cases/${next.id}${mode === "chat" ? "/chat" : ""}`, querySuffix, lang));
                    }}>
                    <Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.9} />
                  </button>
                  <Link className="button button-secondary button-small" to={localizedPath(`/cases/${id}/edit?step=2&flow=review`, querySuffix, lang)}>{t("edit")}</Link>
                </div>
              </div>
              <div className="fact-line"><span>{caseTypeLabel(current.case_type, lang)}</span><span><Icon path={mdiMapMarkerOutline} size={0.75} />{current.location || t("noLocation")}</span>
                {current.date && <span><Icon path={mdiCalendar} size={0.75} />{current.date}</span>}
                <CaseStatus value={current.status} /><Severity value={current.severity} /></div>
            </div>
            <div className="mode-tabs">
              <NavLink end to={localizedPath(`/cases/${id}`, querySuffix, lang)}><Icon path={mdiFileDocumentOutline} size={0.8} />{t("report")}</NavLink>
              <NavLink to={localizedPath(`/cases/${id}/chat`, querySuffix, lang)}><Icon path={mdiMessageTextOutline} size={0.8} />{t("conversation")}<span className="tab-count">{current.message_count}</span></NavLink>
              <Link to={localizedPath(sourcesPath, querySuffix, lang)}><Icon path={mdiPaperclip} size={0.8} />{t("sources")}<span className="tab-count">{current.attachments.length}</span></Link>
            </div>
            {results.data && index < 0 && <div className="notice notice-info filter-warning">{t("noLongerMatches")}</div>}
            {mode === "chat" ? <Conversation caseId={Number(id)} detail={current} /> :
              <ReportView caseDetail={current} onAnalyze={() => analyze.mutate()} busy={analyze.isPending}
                onDelete={() => window.confirm(t("deleteConfirm")) && remove.mutate()} />}
          </>
        )}
      </section>
    </div>
  );
}

function ReportView({ caseDetail, onAnalyze, busy, onDelete }: {
  caseDetail: CaseDetail; onAnalyze: () => void; busy: boolean; onDelete: () => void;
}) {
  const { lang, t } = useLocale();
  const [version, setVersion] = useState<number | null>(null);
  const report = caseDetail.report;
  const items = report ? Object.entries(report) : [];
  const currentVersion = caseDetail.versions.find((item) => item.id === version);
  const previousReport = currentVersion ? parseReportText(currentVersion.report_text) : null;
  return (
    <div className="report-view">
      <div className="report-toolbar">
        <label className="version-select"><span>{t("report")}</span>
          <select value={version ?? ""} onChange={(event) => setVersion(event.target.value ? Number(event.target.value) : null)}>
            <option value="">—</option>
            {caseDetail.versions.map((entry, i) => <option value={entry.id} key={entry.id}>{t("previous")} {i + 1}</option>)}
          </select>
        </label>
        {version !== null && <button className="text-button" onClick={() => setVersion(null)}>{t("currentReport")}</button>}
        <a className="text-button" href={`/api/cases/${caseDetail.id}/report.txt?lang=${lang}${version ? `&version=${version}` : ""}`}>
          {t("download")}
        </a>
        <button className="text-button danger-text" onClick={onDelete}>{t("delete")}</button>
      </div>
      {version !== null && <div className="notice notice-info">{t("previousReport")}</div>}
      {caseDetail.status === "analyzing" && <div className="notice notice-info"><span className="spinner" />{t("analyzing")}</div>}
      {caseDetail.status === "failed" && <div className="notice notice-danger"><Icon path={mdiAlertCircleOutline} size={0.9} />{t("failed")}</div>}
      {caseDetail.status === "draft" && <div className="notice notice-info">{t("noReport")}</div>}
      {currentVersion ? previousReport ? <ReportDocument items={Object.entries(previousReport)} /> :
        <ReportDocument text={currentVersion.report_text} /> :
        items.length ? <ReportDocument items={items} /> : caseDetail.report_raw ? <ReportDocument text={caseDetail.report_raw} /> : null}
      {(caseDetail.status === "draft" || caseDetail.status === "failed") && (
        <div className="report-empty-action"><button className="button button-primary" onClick={onAnalyze} disabled={busy}>
          <Icon path={mdiCheckCircleOutline} size={0.85} />{caseDetail.status === "failed" ? t("reanalyze") : t("analyze")}
        </button></div>
      )}
    </div>
  );
}

function parseReportText(text: string): Record<string, unknown> | null {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```[a-zA-Z]*\s*([\s\S]*?)\s*```$/);
  const candidate = fenced?.[1] ?? trimmed;
  if (!candidate.startsWith("{")) return null;
  try {
    const parsed: unknown = JSON.parse(candidate);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function ReportDocument({ items, text }: { items?: [string, unknown][]; text?: string }) {
  if (text) return <article className="report-document"><pre>{text}</pre></article>;
  return (
    <article className="report-document">
      {items?.map(([title, value], index) => (
        <section className={`report-section ${index === 0 ? "report-lead" : ""}`} key={title}>
          <div className="section-kicker">0{index + 1}</div><div><h2>{title}</h2><ReportValue value={value} /></div>
        </section>
      ))}
    </article>
  );
}

function ReportValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <ul>{value.map((item, i) => <li key={i}>{String(item)}</li>)}</ul>;
  if (value && typeof value === "object") {
    return <dl className="report-fields">{Object.entries(value).map(([key, item]) =>
      <div key={key}><dt>{key}</dt><dd>{String(item)}</dd></div>)}</dl>;
  }
  return <p>{String(value ?? "—")}</p>;
}

function SourcesInspector({ caseId, caseDetail, returnTo }: {
  caseId: number; caseDetail: CaseDetail; returnTo: string;
}) {
  const { lang, t } = useLocale();
  const location = useLocation();
  const client = useQueryClient();
  const [preview, setPreview] = useState<{ text: string; errors: string[] } | null>(null);
  const files = useQuery({ queryKey: ["attachments", caseId, lang], queryFn: () => api.attachments(caseId, lang) });
  const previewMutation = useMutation({
    mutationFn: () => api.previewRead(caseId, lang),
    onSuccess: setPreview,
  });
  const uploadMutation = useMutation({
    mutationFn: (input: File[]) => api.upload(caseId, input, lang),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["attachments", caseId] });
      void client.invalidateQueries({ queryKey: ["case", String(caseId)] });
    },
  });
  return (
    <div className="sources-view">
      <div className="sources-heading">
        <div className="sources-heading-row">
          <Link className="back-link" to={localizedPath(returnTo, location.search, lang)}><Icon path={lang === "ar" ? mdiArrowRight : mdiArrowLeft} size={0.8} />{t("backResults")}</Link>
          <Link className="icon-button" aria-label={t("close")} title={t("close")}
            to={localizedPath(returnTo, location.search, lang)}><Icon path={mdiClose} size={0.8} /></Link>
        </div>
        <div className="eyebrow">{t("sources")}</div><h1>{t("sources")}</h1><p>{caseDetail.case_name || t("untitled")}</p>
      </div>
      <section className="source-section">
        <div className="section-heading">
          <div><span className="eyebrow">01 / REPORT</span><h2>{t("originalReport")}</h2></div>
          <Link className="button button-secondary button-small"
            to={localizedPath(`/cases/${caseId}/edit?step=2&flow=review&editOriginal=1`, location.search, lang)}>
            {t("edit")}
          </Link>
        </div>
        <div className="original-text">{caseDetail.case_text}</div>
      </section>
      <section className="source-section">
        <div className="section-heading"><div><span className="eyebrow">02 / EVIDENCE</span><h2>{t("attachment")}</h2></div>
          <label className="button button-secondary button-small">{t("upload")}<input className="sr-only" type="file" multiple
            disabled={uploadMutation.isPending} onChange={(event) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) uploadMutation.mutate(files);
              event.target.value = "";
            }} /></label>
        </div>
        {files.isPending ? <Loading /> : files.isError ? <div className="notice notice-danger">{t("attachmentsLoadError")}</div> :
          (files.data?.length ? <div className="attachment-list">{files.data.map((file) =>
            <AttachmentRow key={file.id} file={file} />)}</div> : <p className="muted">{t("noAttachments")}</p>)}
        {uploadMutation.isPending && <div className="notice notice-info">{t("loading")}</div>}
        {uploadMutation.data?.uploaded ? <div className="notice notice-info">{t("uploadComplete")}: {uploadMutation.data.uploaded}</div> : null}
        {uploadMutation.data?.errors.map((error) => <div className="notice notice-danger" key={error.name}>{error.name}: {error.error}</div>)}
        {uploadMutation.isError && <div className="notice notice-danger">{uploadMutation.error.message}</div>}
        <button className="button button-ghost" onClick={() => previewMutation.mutate()} disabled={previewMutation.isPending}>
          {t("previewRead")}
        </button>
        {previewMutation.isError && <div className="notice notice-danger">{t("previewError")} {previewMutation.error.message}</div>}
        {preview && <div className="preview-box"><pre>{preview.text || t("readError")}</pre>{preview.errors.map((error) => <p key={error}>{error}</p>)}</div>}
      </section>
      <section className="source-section location-card"><span className="eyebrow">03 / LOCATION</span><h2>{t("location")}</h2>
        <p>{caseDetail.location || t("noLocation")}</p>
        {caseDetail.latitude != null && caseDetail.longitude != null && (
          <div className="source-map">
            <Suspense fallback={<Loading />}>
              <MapCanvas cases={[caseDetail]} search={location.search} lang={lang} untitled={t("untitled")} />
            </Suspense>
          </div>
        )}
        {caseDetail.latitude != null && caseDetail.longitude != null &&
          <a target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${caseDetail.latitude}&mlon=${caseDetail.longitude}#map=14/${caseDetail.latitude}/${caseDetail.longitude}`}>
            {caseDetail.latitude.toFixed(4)}, {caseDetail.longitude.toFixed(4)}
          </a>}
      </section>
    </div>
  );
}

function AttachmentRow({ file }: { file: Attachment }) {
  const { lang, t } = useLocale();
  const state = file.read_status ?? "will_read";
  const label = state === "read" ? t("read") : state === "unread" ? t("unread") : t("willRead");
  return (
    <div className="attachment-row">
      <span className="file-icon"><Icon path={mdiFileDocumentOutline} size={1} /></span>
      <span className="attachment-name"><strong>{file.file_name}</strong><small>{file.kind} · {Math.max(1, Math.round(file.size / 1024))} KB</small></span>
      <span className={`read-state read-${state}`}>{label}</span>
      <a className="icon-button" title={t("attachment")} href={`/api/attachments/${file.id}/file?lang=${lang}`} target="_blank" rel="noreferrer">↗</a>
    </div>
  );
}

function Conversation({ caseId, detail }: { caseId: number; detail: CaseDetail }) {
  const { lang, t } = useLocale();
  const location = useLocation();
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [fileList, setFileList] = useState<FileList | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [updateNotice, setUpdateNotice] = useState(false);
  const draftKey = `alpha-chat-draft:${caseId}`;
  const messageKey = ["messages", caseId, lang];

  useEffect(() => {
    setText(sessionStorage.getItem(draftKey) ?? "");
  }, [draftKey]);
  useEffect(() => {
    if (text) sessionStorage.setItem(draftKey, text);
    else sessionStorage.removeItem(draftKey);
  }, [draftKey, text]);

  const messages = useQuery({
    queryKey: messageKey,
    queryFn: () => api.messages(caseId, lang),
    refetchInterval: (query) => query.state.data?.some((message) => message.status === "pending") ? 3000 : false,
  });
  const send = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.set("text", text);
      Array.from(fileList ?? []).forEach((file) => form.append("files", file));
      return api.sendMessage(caseId, form, lang);
    },
    onMutate: async () => {
      await client.cancelQueries({ queryKey: messageKey });
      const previous = client.getQueryData<ChatMessage[]>(messageKey);
      const optimistic: ChatMessage = {
        id: -Date.now(), case_id: caseId, role: "user", content: text, status: "ok",
        error: null, reply_to: null, attachments: [],
      };
      client.setQueryData<ChatMessage[]>(messageKey, (current) => [...(current ?? []), optimistic]);
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) client.setQueryData(messageKey, context.previous);
    },
    onSuccess: async () => {
      setText("");
      setFileList(null);
      sessionStorage.removeItem(draftKey);
      await client.invalidateQueries({ queryKey: messageKey });
    },
  });
  const clear = useMutation({
    mutationFn: () => api.clearMessages(caseId, lang),
    onSuccess: () => client.invalidateQueries({ queryKey: messageKey }),
  });
  const retry = useMutation({
    mutationFn: (messageId: number) => api.retry(messageId, lang),
    onSuccess: () => client.invalidateQueries({ queryKey: messageKey }),
  });
  const update = useMutation({
    mutationFn: (messageId: number) => api.updateReport(messageId, lang),
    onSuccess: async () => {
      setUpdateNotice(true);
      await client.invalidateQueries({ queryKey: ["case", String(caseId)] });
    },
  });
  useEffect(() => {
    if (nearBottom.current && transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
      setHasNewMessages(false);
    } else if (messages.data?.length) {
      setHasNewMessages(true);
    }
  }, [messages.data]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (text.trim() || fileList?.length) send.mutate();
  };
  const attachmentMessageIds = new Set((messages.data ?? [])
    .filter((item) => item.role === "user" && item.attachments.length > 0)
    .map((item) => item.id));
  return (
    <div className="conversation">
      <div className="conversation-top">
        <div><span className="eyebrow">{detail.case_number || `CASE-${caseId}`}</span><h2>{t("conversation")}</h2></div>
        <button className="text-button danger-text" onClick={() => window.confirm(t("clearChat")) && clear.mutate()}>{t("clearChat")}</button>
      </div>
      {updateNotice && <div className="notice notice-info update-notice">{t("reportUpdated")}
        <Link to={localizedPath(`/cases/${caseId}`, location.search, lang)}>{t("report")}</Link>
      </div>}
      <div className="transcript" ref={transcriptRef} onScroll={(event) => {
        const element = event.currentTarget;
        nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
        if (nearBottom.current) setHasNewMessages(false);
      }}>
        {messages.isPending ? <Loading /> : (messages.data ?? []).length === 0 ? <EmptyState title={t("noMessages")} /> :
          (messages.data ?? []).map((message) => (
            <MessageBubble key={message.id} message={message} onRetry={() => retry.mutate(message.id)}
              reportAutoUpdated={Boolean(message.reply_to && attachmentMessageIds.has(message.reply_to))}
              onUpdate={() => window.confirm(t("updateConfirm")) && update.mutate(message.id)} />
          ))}
        {hasNewMessages && <button className="button button-secondary new-reply-button"
          onClick={() => { if (transcriptRef.current) transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight; }}>
          {t("newReply")}
        </button>}
      </div>
      <form className="composer" onSubmit={submit}>
        {fileList && fileList.length > 0 && <div className="composer-files">{Array.from(fileList).map((file) => <span key={file.name}>{file.name}</span>)}</div>}
        <div className="composer-row">
          <label className="icon-button attach-button" title={t("upload")}>＋<input className="sr-only" type="file" multiple onChange={(event) => setFileList(event.target.files)} /></label>
          <textarea value={text} rows={1} onChange={(event) => setText(event.target.value)}
            placeholder={t("writeMessage")} onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (text.trim() || fileList?.length) send.mutate();
              }
            }} />
          <button className="button button-primary send-button" type="submit" disabled={send.isPending || (!text.trim() && !fileList?.length)}>{t("send")}</button>
        </div>
        {send.isError && <p className="form-error">{send.error.message}</p>}
      </form>
    </div>
  );
}

function MessageBubble({ message, reportAutoUpdated, onRetry, onUpdate }: {
  message: ChatMessage; onRetry: () => void; onUpdate: () => void;
  reportAutoUpdated: boolean;
}) {
  const { lang, t } = useLocale();
  const mine = message.role === "user";
  return (
    <article className={`message-row ${mine ? "message-mine" : "message-theirs"}`}>
      <div className="message-meta">{mine ? (lang === "ar" ? "أنت" : "You") : "Alpha"} <time>{message.status}</time></div>
      <div className="message-bubble">
        {message.status === "pending" ? <span className="typing"><i /><i /><i /></span> : message.content}
        {message.status === "failed" && <div className="message-error">{message.error}</div>}
      </div>
      {message.attachments?.map((file) => <AttachmentRow key={file.id} file={file} />)}
      {message.status === "failed" && <button className="text-button" onClick={onRetry}>{t("retry")}</button>}
      {!mine && message.status === "ok" && (reportAutoUpdated
        ? <small className="message-report-note">{t("attachmentReportAdded")}</small>
        : <button className="text-button" onClick={onUpdate}>{t("updateReport")}</button>)}
    </article>
  );
}

function CaseEditor() {
  const { id } = useParams();
  const isEdit = Boolean(id);
  const { lang, t } = useLocale();
  const navigate = useNavigate();
  const client = useQueryClient();
  const location = useLocation();
  const [params] = useSearchParams();
  const step = Number(params.get("step") ?? (isEdit ? 2 : 1));
  const [caseText, setCaseText] = useState("");
  const [editingOriginal, setEditingOriginal] = useState(() => params.get("editOriginal") === "1");
  const [flowError, setFlowError] = useState("");
  const [suggestionPending, setSuggestionPending] = useState(false);
  const [suggestionFailed, setSuggestionFailed] = useState(false);
  const [fields, setFields] = useState({
    case_name: "", case_number: "", case_type: "عام", location: "", date: "",
  });
  const [newAttachmentsUploaded, setNewAttachmentsUploaded] = useState(false);
  const [point, setPoint] = useState<GeoPoint | null>(null);
  const [mapOpen, setMapOpen] = useState(false);
  const [locationNotice, setLocationNotice] = useState("");
  const savedValues = useRef<{ caseText: string; fields: typeof fields; point: GeoPoint | null } | null>(null);
  const locationValue = useRef("");
  const hydratedCaseId = useRef<string | null>(null);
  const skipBlock = useRef(false);
  const createInProgress = useRef(false);
  const suggestedCaseId = useRef<string | null>(null);
  const suggestionCancelled = useRef(false);
  const caseQuery = useQuery({
    queryKey: ["case", id, lang],
    queryFn: () => api.case(id!, lang),
    enabled: isEdit,
  });
  const attachments = useQuery({
    queryKey: ["attachments", id, lang],
    queryFn: () => api.attachments(id!, lang),
    enabled: isEdit,
  });
  useEffect(() => {
    const item = caseQuery.data;
    if (item && hydratedCaseId.current !== id) {
      savedValues.current = {
        caseText: item.case_text,
        point: item.latitude == null || item.longitude == null
          ? null : { latitude: item.latitude, longitude: item.longitude },
        fields: {
          case_name: item.case_name ?? "", case_number: item.case_number ?? "", case_type: item.case_type || "عام",
          location: item.location ?? "", date: item.date ?? "",
        },
      };
      setCaseText(item.case_text);
      setFields(savedValues.current.fields);
      locationValue.current = savedValues.current.fields.location;
      setPoint(savedValues.current.point);
      hydratedCaseId.current = id ?? null;
    }
  }, [caseQuery.data, id]);
  const create = useMutation({ mutationFn: () => api.createCase(caseText, lang) });
  const patch = useMutation({
    mutationFn: (payload: Partial<CaseDetail>) => api.patchCase(Number(id), payload, lang),
  });
  const upload = useMutation({
    mutationFn: (files: File[]) => api.upload(Number(id), files, lang, { reanalyze: false }),
    onSuccess: async (result) => {
      if (result.uploaded > 0) setNewAttachmentsUploaded(true);
      await client.invalidateQueries({ queryKey: ["attachments", id] });
      await client.invalidateQueries({ queryKey: ["cases"] });
    },
  });
  const geocode = useMutation({
    mutationFn: (query: string) => api.geocode(query, lang),
    onSuccess: (result, query) => {
      if (fields.location.trim() !== query) return;
      setPoint(result);
      setLocationNotice(result ? "" : t("locationNotFound"));
    },
  });
  const isDirty = (savedValues.current
    ? caseText !== savedValues.current.caseText || JSON.stringify(fields) !== JSON.stringify(savedValues.current.fields) ||
      JSON.stringify(point) !== JSON.stringify(savedValues.current.point)
    : !isEdit && step === 1 && Boolean(caseText.trim())) || upload.isPending || newAttachmentsUploaded;
  const blocker = useBlocker(() => isDirty && !skipBlock.current);

  useEffect(() => {
    if (!isDirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDirty]);

  const samples = useQuery({
    queryKey: ["samples", lang],
    queryFn: async () => {
      const response = await fetch(`/api/samples?lang=${lang}`);
      if (!response.ok) throw new Error("Could not load samples");
      return response.json() as Promise<{ text: string; name: string }[]>;
    },
    enabled: !isEdit,
  });

  const updateField = (key: keyof typeof fields, value: string) => {
    setFields((current) => ({ ...current, [key]: value }));
    if (key === "location") {
      locationValue.current = value;
      setPoint(null);
      setLocationNotice("");
    }
  };
  useEffect(() => {
    const item = caseQuery.data;
    if (!isEdit || params.get("flow") !== "new" || step !== 2 || !item || suggestedCaseId.current === id) return;
    suggestedCaseId.current = id ?? null;
    suggestionCancelled.current = false;
    setSuggestionPending(true);
    setSuggestionFailed(false);
    const initialFields = {
      case_name: item.case_name ?? "",
      case_type: item.case_type || "عام",
      location: item.location ?? "",
      date: item.date ?? "",
    };
    const initialPoint = item.latitude == null || item.longitude == null
      ? null : { latitude: item.latitude, longitude: item.longitude };
    void api.suggest(Number(id), lang).then((suggestion) => {
      if (suggestionCancelled.current) return;
      setFields((current) => ({
        ...current,
        case_name: current.case_name === initialFields.case_name
          ? suggestion.case_name ?? current.case_name : current.case_name,
        case_type: current.case_type === initialFields.case_type
          ? suggestion.case_type ?? current.case_type : current.case_type,
        location: current.location === initialFields.location
          ? suggestion.location ?? current.location : current.location,
        date: current.date === initialFields.date
          ? suggestion.date ?? current.date : current.date,
      }));
      const { latitude, longitude } = suggestion;
      if (latitude != null && longitude != null) {
        setPoint((current) => current?.latitude === initialPoint?.latitude &&
          current?.longitude === initialPoint?.longitude
          ? { latitude, longitude } : current);
      }
      const suggestedLocation = suggestion.location;
      const canApplyLocation = locationValue.current === initialFields.location;
      if (suggestedLocation && canApplyLocation) {
        locationValue.current = suggestedLocation;
        void api.geocode(suggestedLocation, lang).then((point) => {
          if (suggestionCancelled.current || locationValue.current !== suggestedLocation) return;
          if (point) {
            setPoint((current) => current?.latitude === initialPoint?.latitude &&
              current?.longitude === initialPoint?.longitude ? point : current);
          }
        }).catch(() => {
          if (!suggestionCancelled.current && locationValue.current === suggestedLocation) {
            setLocationNotice(t("locationNotFound"));
          }
        });
      }
    }).catch(() => {
      if (!suggestionCancelled.current) setSuggestionFailed(true);
    }).finally(() => {
      setSuggestionPending(false);
    });
  }, [caseQuery.data, id, isEdit, lang, params, step]);
  const nextStep = async () => {
    if (createInProgress.current) return;
    createInProgress.current = true;
    setFlowError("");
    try {
      const created = await create.mutateAsync();
      const stepPath = `/cases/${created.id}/edit?step=2&flow=new`;
      skipBlock.current = true;
      navigate(localizedPath(stepPath, location.search, lang));
    } catch (error) {
      setFlowError(error instanceof Error ? error.message : t("unknownError"));
    } finally {
      createInProgress.current = false;
    }
  };
  const save = async (analyze: boolean) => {
    suggestionCancelled.current = true;
    setSuggestionPending(false);
    setFlowError("");
    const analyzeUpdatedCase = analyze || newAttachmentsUploaded;
    try {
      const { case: updatedCase } = await patch.mutateAsync({
        ...fields,
        case_text: caseText,
        latitude: point?.latitude ?? null,
        longitude: point?.longitude ?? null,
      });
      if (analyzeUpdatedCase) await api.analyze(Number(id), lang);
      client.setQueryData<CaseDetail>(["case", id, lang], {
        ...updatedCase,
        status: analyzeUpdatedCase ? "analyzing" : updatedCase.status,
      });
      setNewAttachmentsUploaded(false);
      savedValues.current = { caseText, fields: { ...fields }, point };
      skipBlock.current = true;
      void client.invalidateQueries({ queryKey: ["case", id] });
      void client.invalidateQueries({ queryKey: ["cases"] });
      navigate(localizedPath(`/cases/${id}`, location.search, lang));
    } catch (error) {
      setFlowError(error instanceof Error ? error.message : t("unknownError"));
    }
  };

  if (isEdit && caseQuery.isPending) return <Loading />;
  if (isEdit && caseQuery.isError) return <ErrorPanel message={t("error")} />;
  return (
    <div className={`editor-layout ${isEdit && params.get("flow") !== "new" ? "editor-layout-review" : ""}`}>
      <aside className="editor-results" dir={lang}>
        <Link className="back-link" to={localizedPath(isEdit ? `/cases/${id}` : "/cases", location.search, lang)}>
          <Icon path={lang === "ar" ? mdiArrowRight : mdiArrowLeft} size={0.8} />{isEdit ? t("backResults") : t("allCases")}
        </Link>
        {step === 2 ? (
          <div className="editor-original">
            <div className="editor-original-heading"><h2>{t("originalReport")}</h2>
              <button className="text-button" type="button" onClick={() => setEditingOriginal((value) => !value)}>
              {editingOriginal ? t("done") : t("edit")}
              </button>
            </div>
            {editingOriginal ? <textarea aria-label={t("originalReport")} value={caseText}
              onChange={(event) => setCaseText(event.target.value)} /> :
              <p>{caseText || t("noReport")}</p>}
          </div>
        ) : (
          <div className="editor-note"><span className="eyebrow">ALPHA / WORKSPACE</span><h2>{isEdit ? t("edit") : t("newCase")}</h2>
            <p>{t("aboutDescription")}</p></div>
        )}
      </aside>
      <section className="editor-main" dir={lang}>
        <PageHeading eyebrow={`STEP 0${step} / 02`} title={step === 1 ? t("stepOne") :
          isEdit && params.get("flow") !== "new" ? t("reviewBeforeSave") : t("stepTwo")} />
        {(params.get("suggest_failed") === "1" || suggestionFailed) &&
          <div className="notice notice-info">{t("suggestionFailed")}</div>}
        {suggestionPending && <div className="notice notice-info"><span className="spinner" />{t("suggestingDetails")}</div>}
        <div className="stepper"><span className={step === 1 ? "active" : "complete"}>01 <small>{t("stepOne")}</small></span>
          <i /><span className={step === 2 ? "active" : ""}>02 <small>{t("stepTwo")}</small></span></div>
        {step === 1 && !isEdit ? (
          <section className="editor-card">
            <label className="field-label" htmlFor="case-text">{t("caseText")}</label>
            <textarea id="case-text" className="large-textarea" value={caseText} onChange={(event) => setCaseText(event.target.value)}
              placeholder={t("stepOne")} minLength={20} rows={10} />
            <div className="field-hint"><span>{caseText.length} / 20</span>
              <label className="select-sample">{t("useSample")}<Icon path={mdiChevronDown} size={0.8} />
                <select value="" onChange={(event) => {
                  const sample = samples.data?.[Number(event.target.value)];
                  if (sample && (!caseText.trim() || window.confirm(t("useSample")))) setCaseText(sample.text);
                }}>
                  <option value="">—</option>{samples.data?.map((sample, index) => <option value={index} key={sample.name}>{sample.name}</option>)}
                </select>
              </label>
            </div>
            <div className="editor-footer"><span className="muted">20 {lang === "ar" ? "حرفاً كحد أدنى" : "characters minimum"}</span>
              <button className="button button-primary" onClick={() => void nextStep()} disabled={caseText.trim().length < 20 || create.isPending}>
                {t("nextStep")}<Icon path={lang === "ar" ? mdiChevronLeft : mdiChevronRight} size={0.8} />
              </button>
            </div>
            {flowError && <p className="form-error">{flowError}</p>}
          </section>
        ) : (
          <section className="editor-card">
            <div className="form-grid">
              <Field label={t("caseName")} value={fields.case_name} onChange={(value) => updateField("case_name", value)} />
              <Field label={t("caseNumber")} value={fields.case_number} onChange={(value) => updateField("case_number", value)} />
              <label className="field"><span>{t("type")}</span><select value={fields.case_type} onChange={(event) => updateField("case_type", event.target.value)}>
                {CASE_TYPES.map((value) => <option value={value} key={value}>{caseTypeLabel(value, lang)}</option>)}
              </select></label>
              <Field label={t("date")} type="date" lang={lang} value={fields.date}
                onChange={(value) => updateField("date", value)} />
              <Field label={t("location")} value={fields.location} onChange={(value) => updateField("location", value)} />
            </div>
            <div className="location-tools">
              <button className="button button-secondary button-small" onClick={() => geocode.mutate(fields.location.trim())}
                disabled={!fields.location.trim() || geocode.isPending}>
                {geocode.isPending ? t("loading") : t("findLocation")}
              </button>
              <button className="button button-ghost button-small" onClick={() => setMapOpen(true)}>{t("chooseOnMap")}</button>
              {point && <span className="muted ltr">{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</span>}
            </div>
            {(locationNotice || geocode.isError) && <div className="notice notice-danger">
              {locationNotice || `${t("geocodeError")} ${geocode.error?.message ?? ""}`}
            </div>}
            <div className="editor-location-preview">
              {point ? (
                <Suspense fallback={<Loading />}>
                  <MapCanvas cases={[{
                    id: Number(id), case_name: fields.case_name, case_number: fields.case_number,
                    case_type: fields.case_type, status: "draft", severity: null, location: fields.location,
                    latitude: point.latitude, longitude: point.longitude, date: fields.date, timestamp: "",
                  }]} search={location.search} lang={lang} untitled={t("untitled")} />
                </Suspense>
              ) : (
                <button className="button button-ghost" type="button" onClick={() => setMapOpen(true)}>
                  <Icon path={mdiMapMarkerOutline} size={0.85} />{t("chooseOnMap")}
                </button>
              )}
            </div>
            {isEdit && <>
              <label className="upload-zone">{t("upload")}<input type="file" multiple disabled={upload.isPending}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length) upload.mutate(files);
                  event.target.value = "";
                }} /></label>
              {upload.isPending && <div className="notice notice-info">{t("loading")}</div>}
              {upload.data?.uploaded ? <div className="notice notice-info">{t("uploadComplete")}: {upload.data.uploaded}</div> : null}
              {upload.data?.errors.map((error) => <div className="notice notice-danger" key={error.name}>{error.name}: {error.error}</div>)}
              {upload.isError && <div className="notice notice-danger">{upload.error.message}</div>}
              {attachments.isPending ? <Loading /> : attachments.isError ?
                <div className="notice notice-danger">{t("attachmentsLoadError")}</div> :
                (attachments.data?.length ? <div className="attachment-list">{attachments.data.map((file) =>
                  <AttachmentRow key={file.id} file={file} />)}</div> : <p className="muted">{t("noAttachments")}</p>)}
            </>}
            <div className="editor-footer editor-footer-wrap">
              <button className="button button-secondary" onClick={() => void save(false)} disabled={patch.isPending || geocode.isPending || upload.isPending}>{isEdit ? t("save") : t("saveDraft")}</button>
              <button className="button button-primary" onClick={() => void save(true)} disabled={patch.isPending || geocode.isPending || upload.isPending}>{t("saveAnalyze")}</button>
            </div>
            {flowError && <p className="form-error">{flowError}</p>}
          </section>
        )}
      </section>
      {mapOpen && <div className="dialog-backdrop">
        <section className="map-dialog" role="dialog" aria-modal="true" aria-labelledby="map-picker-title">
          <div className="map-dialog-heading"><div><h2 id="map-picker-title">{t("chooseOnMap")}</h2><p>{t("mapPickHint")}</p></div>
            <button className="icon-button" aria-label={t("close")} onClick={() => setMapOpen(false)}><Icon path={mdiClose} size={0.9} /></button>
          </div>
          <Suspense fallback={<Loading />}><LocationPicker point={point} onChange={(nextPoint) => {
            setPoint(nextPoint);
            setLocationNotice("");
          }} /></Suspense>
          <div className="map-dialog-footer">
            {point && <span className="muted ltr">{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</span>}
            <button className="button button-primary" onClick={() => setMapOpen(false)}>{t("save")}</button>
          </div>
        </section>
      </div>}
      {blocker.state === "blocked" && <div className="dialog-backdrop">
        <section className="confirm-dialog" role="alertdialog" aria-modal="true"
          aria-labelledby="unsaved-title" aria-describedby="unsaved-description">
          <h2 id="unsaved-title">{t("unsavedChanges")}</h2>
          <p id="unsaved-description">{t("leaveWithoutSaving")}</p>
          <div className="confirm-actions">
            <button className="button button-secondary" onClick={() => blocker.reset()}>{t("stay")}</button>
            <button className="button button-danger" onClick={() => blocker.proceed()}>{t("leave")}</button>
          </div>
        </section>
      </div>}
    </div>
  );
}

function Field({ label, value, onChange, type = "text", lang }: {
  label: string; value: string; onChange: (value: string) => void; type?: string; lang?: string;
}) {
  return <label className="field"><span>{label}</span><input type={type} lang={lang} value={value}
    onChange={(event) => onChange(event.target.value)} /></label>;
}

function MapPage() {
  const { lang, t } = useLocale();
  const location = useLocation();
  const results = useCaseResults();
  return (
    <section className="register-page">
      <PageHeading eyebrow="ALPHA / MAP" title={t("map")} detail={t("allCases")} />
      {results.isPending ? <Loading /> : results.isError ? <ErrorPanel message={t("error")} /> :
        <Suspense fallback={<Loading />}><MapCanvas cases={results.data?.cases ?? []} search={location.search}
          lang={lang} untitled={t("untitled")} /></Suspense>}
    </section>
  );
}

function CaseChartPage() {
  const { lang, t } = useLocale();
  const results = useCaseResults();
  const stats = results.data?.stats as CaseStats | undefined;
  return (
    <section className="register-page chart-page">
      <PageHeading eyebrow="ALPHA / CHART" title={t("chart")} detail={t("allCases")} />
      {results.isPending ? <Loading /> : results.isError ? <ErrorPanel message={t("error")} /> : (
        <CaseTypeSeverityChart title={t("typeSeveritySummary")} rows={typeSeverityRows(stats, lang)} />
      )}
    </section>
  );
}

function AboutPage() {
  const { lang, t } = useLocale();
  const location = useLocation();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [playbackBlocked, setPlaybackBlocked] = useState(false);
  const aboutName = t("aboutName");
  const [firstName, ...restName] = aboutName.split(" ");
  const startVideo = () => {
    const video = videoRef.current;
    if (!video) return;
    void video.play().then(
      () => setPlaybackBlocked(false),
      () => setPlaybackBlocked(true),
    );
  };
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let active = true;
    void video.play().then(
      () => { if (active) setPlaybackBlocked(false); },
      () => { if (active) setPlaybackBlocked(true); },
    );
    return () => {
      active = false;
      video.pause();
    };
  }, []);
  const features = [
    { title: t("featCases"), detail: t("featCasesDetail"), icon: "cases" },
    { title: t("featAI"), detail: t("featAIDetail"), icon: "ai" },
    { title: t("featFast"), detail: t("featFastDetail"), icon: "fast" },
    { title: t("featPrivate"), detail: t("featPrivateDetail"), icon: "private" },
  ];
  return (
    <section className="about-page" dir={lang}>
      <div className="about-media">
        <video ref={videoRef} autoPlay muted playsInline preload="auto">
        <source src="/api/assets/about-video-user.mp4" type="video/mp4" />
        </video>
        <div className="about-scrim" aria-hidden="true" />
        {playbackBlocked && <button className="about-play-button" onClick={startVideo}>{t("playVideo")}</button>}
        <nav className="about-social" aria-label={t("contact")}>
          <a href="https://wa.me/97056939064" target="_blank" rel="noreferrer" aria-label="WhatsApp" title="WhatsApp">
            <Icon path={mdiWhatsapp} size={1} />
          </a>
          <a href="https://github.com/3bdallah2004" target="_blank" rel="noreferrer" aria-label="GitHub" title="GitHub">
            <Icon path={mdiGithub} size={1} />
          </a>
          <a href="mailto:pcabdallah501@gmail.com" aria-label="Email" title="Email">
            <Icon path={mdiEmail} size={1} />
          </a>
        </nav>
        <div className="about-copy">
          <h1 className="about-name">
            <span>{firstName}</span>{" "}<span className="about-name-accent">{restName.join(" ")}</span>
          </h1>
          <p>{t("aboutDescription")}</p>
          <Link className="about-cta" to={localizedPath("/cases", location.search, lang)}>
            {lang === "ar" && <Icon path={mdiChevronRight} size={0.95} />}
            {t("discoverMore")}
            {lang === "en" && <Icon path={mdiChevronRight} size={0.95} />}
          </Link>
        </div>
        <ul className="about-features" aria-label={t("aboutFeatures")}>
          {features.map(({ title, detail, icon }) => (
            <li className="about-feature" key={title}>
              <span className={`about-feature-icon about-feature-icon-${icon}`} aria-hidden="true">
                {icon === "cases" && <svg viewBox="0 0 24 24"><path d="M3 8h18v12H3zM8 8V5h8v3M3 12h18M10 12v2h4v-2" /></svg>}
                {icon === "ai" && <svg viewBox="0 0 24 24"><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></svg>}
                {icon === "fast" && <svg viewBox="0 0 24 24"><path d="m13 2-9 12h7l-1 8 10-13h-7z" /></svg>}
                {icon === "private" && <svg viewBox="0 0 24 24"><path d="m12 3 8 3v6c0 5-3.4 8.3-8 9.5C7.4 20.3 4 17 4 12V6z" /></svg>}
              </span>
              <h2>{title}</h2>
              <p>{detail}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Loading() {
  const { t } = useLocale();
  return <div className="loading"><span className="spinner" />{t("loading")}</div>;
}

function ErrorPanel({ message }: { message: string }) {
  return <div className="error-panel"><Icon path={mdiAlertCircleOutline} size={1} /><span>{message}</span></div>;
}

function EmptyState({ title }: { title: string }) {
  return <div className="empty-state"><span className="empty-icon"><Icon path={mdiFileDocumentOutline} size={1.3} /></span><p>{title}</p></div>;
}

export default App;
