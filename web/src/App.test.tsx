import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const cases = {
  cases: [{
    id: 17,
    case_name: "Sample case",
    case_number: "ALP-2026-017",
    case_type: "سرقة",
    status: "analyzed",
    severity: "medium",
    location: "Central district",
    latitude: null,
    longitude: null,
    date: null,
    timestamp: "2026-10-26 10:00:00",
    attachment_count: 0,
    attachment_bytes: 0,
  }],
  stats: {
    total: 1,
    by_status: { analyzed: 1 },
    by_type: [["سرقة", 1]],
    by_severity: [["medium", 1]],
    by_type_severity: [["سرقة", "medium", 1]],
  },
  count: 1,
};

const caseDetail = {
  ...cases.cases[0],
  case_text: "A sample incident report.",
  report: { "Incident summary": "A sample analyzed report." },
  report_raw: "",
  versions: [],
  attachments: [],
  message_count: 0,
};

function renderApp(initialEntry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "*", element: <App /> }], { initialEntries: [initialEntry] });
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("application shell", () => {
  beforeEach(() => {
    localStorage.removeItem("alpha-search-history");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the register in the requested language", async () => {
    renderApp("/cases?lang=en");
    expect(await screen.findByRole("heading", { name: "All cases" })).toBeInTheDocument();
    expect(await screen.findAllByText("Sample case")).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "Export register CSV" })).toHaveAttribute("href", "/api/cases/export.csv?lang=en");
    expect(screen.getByRole("columnheader", { name: "Attachments" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Date added" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Cases by severity" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Cases by type and severity" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chart" })).toHaveAttribute("href", "/cases/chart?lang=en");
    await waitFor(() => expect(document.documentElement.dir).toBe("ltr"));
  });

  it("suggests recent searches and remembers new register queries", async () => {
    localStorage.setItem("alpha-search-history", JSON.stringify(["financial fraud", "theft"]));
    renderApp("/cases?lang=en");

    const search = await screen.findByPlaceholderText("Search by title, number, or report text");
    expect(search).toHaveAttribute("list", "search-history-register");
    expect(document.querySelector("#search-history-register option[value='theft']")).not.toBeNull();

    fireEvent.change(search, { target: { value: "sample incident" } });
    await waitFor(() => expect(JSON.parse(localStorage.getItem("alpha-search-history") ?? "[]"))
      .toEqual(["sample incident", "financial fraud", "theft"]));
  });

  it("renders the type and severity chart on its own page", async () => {
    renderApp("/cases/chart?lang=en");
    expect(await screen.findByRole("heading", { name: "Chart" })).toBeInTheDocument();
    const typeSeverityChart = await screen.findByRole("group", { name: "Cases by type and severity" });
    expect(typeSeverityChart).toHaveTextContent("Theft");
    expect(typeSeverityChart).toHaveTextContent("Medium");
    expect(typeSeverityChart).toHaveTextContent("1");
    await waitFor(() => expect(document.documentElement.dir).toBe("ltr"));
  });

  it("prefetches case details when a case link is hovered", async () => {
    const requested: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      requested.push(url);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases?lang=en");
    await screen.findByRole("heading", { name: "All cases" });
    await waitFor(() => expect(document.querySelector(".table-open")).not.toBeNull());
    fireEvent.mouseEnter(document.querySelector(".table-open")!);
    await waitFor(() => expect(requested.some((url) => url.startsWith("/api/cases/17?"))).toBe(true));
  });

  it("shows About only in the menu while keeping All cases accessible from the brand", async () => {
    const playVideo = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    renderApp("/cases?lang=en");
    expect(await screen.findByRole("heading", { name: "All cases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Alpha/ })).toHaveAttribute("href", "/cases?lang=en");
    expect(screen.queryByRole("link", { name: "All cases" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "About" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = screen.getByRole("dialog", { name: "Menu" });
    expect(within(menu).getAllByRole("link", { name: "About" })).toHaveLength(1);
    fireEvent.click(within(menu).getByRole("link", { name: "About" }));
    expect(await screen.findByRole("heading", { name: "Abdullah Haj Ali" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Discover more" })).toHaveAttribute("href", "/cases?lang=en");
    expect(screen.getByRole("list", { name: "Alpha System features" }).querySelectorAll("li")).toHaveLength(4);
    expect(screen.queryByRole("link", { name: "All cases" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("WhatsApp")).toBeInTheDocument();
    expect(screen.getByLabelText("GitHub")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    const video = document.querySelector("video");
    expect(video).toHaveProperty("autoplay", true);
    expect(video).toHaveProperty("muted", true);
    expect(video).toHaveProperty("playsInline", true);
    expect(playVideo).toHaveBeenCalled();
    expect(document.querySelector(".topbar-about")).toBeInTheDocument();
  });

  it("keeps a single About entry in the menu on desktop and mobile layouts", async () => {
    renderApp("/cases?lang=en");
    await screen.findByRole("heading", { name: "All cases" });
    fireEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = screen.getByRole("dialog", { name: "Menu" });
    expect(within(menu).queryByRole("link", { name: "All cases" })).not.toBeInTheDocument();
    expect(within(menu).getAllByRole("link", { name: "About" })).toHaveLength(1);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.querySelector(".mobile-menu-backdrop")).toHaveClass("menu-closing");
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Menu" })).not.toBeInTheDocument());
  });

  it("uploads the selected attachment before clearing the file input", async () => {
    const uploadBodies: FormData[] = [];
    const uploadUrls: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/cases/17/attachments?") && init?.method === "POST") uploadUrls.push(url);
      if (url.startsWith("/api/cases/17/attachments?")) {
        if (init?.method === "POST") {
          uploadBodies.push(init.body as FormData);
          return new Response(JSON.stringify({ uploaded: 1, errors: [], attachments: [] }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17/edit?step=2&flow=review&lang=en");
    const input = await screen.findByLabelText("Add attachments");
    const file = new File(["valid upload"], "evidence.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText(/Attachments uploaded: 1/)).toBeInTheDocument();
    expect(uploadBodies).toHaveLength(1);
    expect(uploadBodies[0].getAll("files")).toHaveLength(1);
    expect((uploadBodies[0].get("files") as File).name).toBe("evidence.txt");
    expect(uploadUrls[0]).toContain("reanalyze=false");
  });

  it("reanalyzes after a newly uploaded case attachment is saved", async () => {
    const requested: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requested.push(`${init?.method ?? "GET"} ${url}`);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17/attachments?") && init?.method === "POST") {
        return new Response(JSON.stringify({ uploaded: 1, errors: [], attachments: [] }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?") && init?.method === "PATCH") {
        return new Response(JSON.stringify({ case: caseDetail, duplicate_case_number: false }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17/analyze?")) {
        return new Response(JSON.stringify({ status: "analyzing" }), { status: 202 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17/edit?step=2&flow=review&lang=en");

    fireEvent.change(await screen.findByLabelText("Add attachments"), {
      target: { files: [new File(["new evidence"], "evidence.txt", { type: "text/plain" })] },
    });
    await screen.findByText(/Attachments uploaded: 1/);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(requested.some((url) => url.startsWith("POST /api/cases/17/analyze?"))).toBe(true));
    expect(requested.find((url) => url.startsWith("POST /api/cases/17/attachments?"))).toContain("reanalyze=false");
  });

  it("starts a fresh analysis after saving an edited original report", async () => {
    const requests: Array<{ url: string; method: string; body?: string }> = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      requests.push({ url, method, body: typeof init?.body === "string" ? init.body : undefined });
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?") && method === "PATCH") {
        return new Response(JSON.stringify({
          case: { ...caseDetail, case_text: JSON.parse(String(init?.body)).case_text },
          duplicate_case_number: false,
        }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17/analyze?")) {
        return new Response(JSON.stringify({ status: "analyzing" }), { status: 202 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17/edit?step=2&flow=review&lang=en");

    await screen.findByRole("heading", { name: "Review case before saving" });
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Original report" }), {
      target: { value: "Updated report with new shipment details." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save and analyze" }));

    await waitFor(() => expect(requests.some(({ url }) => url.startsWith("/api/cases/17/analyze?"))).toBe(true));
    const patch = requests.find(({ method }) => method === "PATCH");
    expect(JSON.parse(patch?.body ?? "{}").case_text).toBe("Updated report with new shipment details.");
  });

  it("keeps the report visible alongside the sources panel", async () => {
    renderApp("/cases/17/sources?lang=en");
    expect(await screen.findByRole("heading", { name: "Incident summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(document.querySelector(".source-layout")).toBeInTheDocument();
  });

  it("renders a previous structured report with the report design", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify({
          ...caseDetail,
          versions: [{
            id: 42,
            timestamp: "2026-10-25 10:00:00",
            report_text: JSON.stringify({
              "Previous incident summary": "The earlier report remains structured.",
              "Evidence": ["First item", "Second item"],
            }),
          }],
        }), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17?lang=en");

    await screen.findByRole("heading", { name: "Incident summary" });
    fireEvent.change(screen.getByLabelText("Report"), { target: { value: "42" } });

    expect(await screen.findByRole("heading", { name: "Previous incident summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByText("The earlier report remains structured.")).toBeInTheDocument();
    expect(document.querySelector(".report-document pre")).not.toBeInTheDocument();
    expect(document.querySelectorAll(".report-section")).toHaveLength(2);
  });

  it("opens the original report for editing from sources and saves its changes", async () => {
    let savedReport = "";
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?") && init?.method === "PATCH") {
        savedReport = JSON.parse(String(init.body)).case_text;
        return new Response(JSON.stringify({
          case: { ...caseDetail, case_text: savedReport },
          duplicate_case_number: false,
        }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17/sources?lang=en");

    const editOriginalLink = (await screen.findAllByRole("link", { name: "Edit" }))
      .find((link) => link.getAttribute("href")?.includes("editOriginal=1"));
    expect(editOriginalLink).toBeDefined();
    fireEvent.click(editOriginalLink!);
    const report = await screen.findByRole("textbox", { name: "Original report" });
    expect(report).toHaveValue(caseDetail.case_text);
    fireEvent.change(report, { target: { value: "Updated original report text." } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(savedReport).toBe("Updated original report text."));
  });

  it("renders older case details that do not include attachment and version lists", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        const { attachments: _attachments, versions: _versions, ...legacyCase } = caseDetail;
        return new Response(JSON.stringify({ ...legacyCase, attachments: null, versions: {} }), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17?lang=en");

    expect(await screen.findByRole("heading", { name: "Sample case" })).toBeInTheDocument();
    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Sources/ })).toHaveTextContent("0");
  });

  it("distinguishes new-case details from reviewing an existing case", async () => {
    renderApp("/cases/17/edit?step=2&flow=new&lang=en");
    expect(await screen.findByRole("heading", { name: "Case details" })).toBeInTheDocument();
    expect(screen.getByLabelText("Incident date")).toHaveAttribute("type", "date");
    expect(screen.getByLabelText("Incident date")).toHaveAttribute("lang", "en");
  });

  it("opens case details without waiting for background suggestions and prevents duplicate creation", async () => {
    const requests: Array<{ url: string; method: string }> = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      requests.push({ url, method });
      if (url.startsWith("/api/cases?") && method === "POST") {
        return new Response(JSON.stringify(caseDetail), { status: 201 });
      }
      if (url.startsWith("/api/cases/17/suggest")) {
        return new Promise<Response>(() => {});
      }
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/new?step=1&lang=en");
    fireEvent.change(await screen.findByLabelText("Incident report"), {
      target: { value: "A detailed incident report for testing the case creation flow." },
    });
    const nextButton = screen.getByRole("button", { name: "Continue" });
    fireEvent.click(nextButton);
    fireEvent.click(nextButton);

    expect(await screen.findByRole("heading", { name: "Case details" })).toBeInTheDocument();
    expect(await screen.findByText("Suggesting case details in the background. You can continue filling the form."))
      .toBeInTheDocument();
    expect(requests.filter(({ url, method }) => url.startsWith("/api/cases?") && method === "POST")).toHaveLength(1);
    expect(requests.filter(({ url }) => url.startsWith("/api/cases/17/suggest"))).toHaveLength(1);
  });

  it("fills suggested fields without waiting for the location lookup", async () => {
    const requests: string[] = [];
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      requests.push(url);
      if (url.startsWith("/api/cases?") && method === "POST") {
        return new Response(JSON.stringify(caseDetail), { status: 201 });
      }
      if (url.startsWith("/api/cases/17/suggest")) {
        return new Response(JSON.stringify({ case_name: "Suggested title", location: "Ramallah" }), { status: 200 });
      }
      if (url.startsWith("/api/geocode")) return new Promise<Response>(() => {});
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify(caseDetail), { status: 200 });
      }
      if (url.startsWith("/api/cases")) {
        return new Response(JSON.stringify(cases), { status: 200 });
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/new?step=1&lang=en");
    fireEvent.change(await screen.findByLabelText("Incident report"), {
      target: { value: "A detailed incident report for testing the case creation flow." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("heading", { name: "Case details" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("Case title")).toHaveValue("Suggested title"));
    expect(screen.getByLabelText("Location")).toHaveValue("Ramallah");
    expect(requests.some((url) => url.startsWith("/api/geocode"))).toBe(true);
    expect(screen.queryByText("Suggesting case details in the background. You can continue filling the form."))
      .not.toBeInTheDocument();
  });

  it("navigates to the case immediately while register data refreshes after analysis starts", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/health")) {
        return new Response(JSON.stringify({ level: "success", message: "ready" }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17/attachments")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      if (url.startsWith("/api/cases/17/analyze")) {
        return new Response(JSON.stringify({ status: "analyzing" }), { status: 202 });
      }
      if (url.startsWith("/api/cases/17?") && init?.method === "PATCH") {
        return new Response(JSON.stringify({
          case: { ...caseDetail, status: "analyzed" },
          duplicate_case_number: false,
        }), { status: 200 });
      }
      if (url.startsWith("/api/cases/17?")) {
        return new Response(JSON.stringify({ ...caseDetail, status: "analyzing" }), { status: 200 });
      }
      if (url.startsWith("/api/cases?")) {
        return new Promise<Response>(() => {});
      }
      return new Response(JSON.stringify([]), { status: 200 });
    });
    renderApp("/cases/17/edit?step=2&flow=review&lang=en");
    fireEvent.click(await screen.findByRole("button", { name: "Save and analyze" }));

    expect(await screen.findByRole("heading", { name: "Sample case" })).toBeInTheDocument();
    expect(await screen.findAllByText("Analyzing")).not.toHaveLength(0);
  });

  it("places the original report before the form when reviewing an existing case", async () => {
    renderApp("/cases/17/edit?step=2&flow=review&lang=en");
    expect(await screen.findByRole("heading", { name: "Review case before saving" })).toBeInTheDocument();
    const layout = document.querySelector(".editor-layout");
    expect(layout).toHaveClass("editor-layout-review");
  });

  it("does not leak editor workflow parameters into general navigation", async () => {
    renderApp("/cases/17/edit?step=2&flow=review&suggest_failed=true&type=سرقة&lang=en");
    const casesLink = await screen.findByRole("link", { name: /^Alpha/ });
    expect(casesLink).toHaveAttribute("href", "/cases?type=%D8%B3%D8%B1%D9%82%D8%A9&lang=en");
  });

  it("switches direction and language without discarding filters", async () => {
    renderApp("/cases?type=سرقة&lang=en");
    const toggle = await screen.findAllByRole("button", { name: "العربية" }).then((buttons) => buttons[0]);
    fireEvent.click(toggle);
    await waitFor(() => expect(document.documentElement.dir).toBe("rtl"));
    expect(screen.getByRole("heading", { name: "كل القضايا" })).toBeInTheDocument();
    await waitFor(() => expect(
      vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("type=")),
    ).toBe(true));
  });

  it("asks before leaving a new case with unsaved text", async () => {
    renderApp("/cases/new?step=1&lang=en");
    fireEvent.change(await screen.findByLabelText("Incident report"), {
      target: { value: "A detailed incident report that has not been saved." },
    });
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole("link", { name: /^Alpha/ }));
    expect(await screen.findByRole("alertdialog", { name: "Unsaved changes" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Stay on page" }));
    expect(screen.getByLabelText("Incident report")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /^Alpha/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Leave page" }));
    expect(await screen.findByRole("heading", { name: "All cases" })).toBeInTheDocument();
  });
});
