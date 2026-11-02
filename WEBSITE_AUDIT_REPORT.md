# Website Audit Report

**Audit date:** 2026-10-26  
**Scope:** Read-only browser and source inspection of the local Alpha website  
**Primary URL:** `http://localhost:8601`  
**Legacy URL:** `http://localhost:8501`  
**Result:** 4 confirmed findings: 1 Medium functional, 1 Medium security, and 2 Low accessibility.

## Executive summary

The live application was opened and exercised in a browser. Both the current React website (port 8601) and the legacy Streamlit interface (port 8501) were reachable. Read-only routes, search, filters, language rendering, direct URLs, refresh/history navigation, and the map were checked. A synthetic audit case was used for read-only case detail, report, conversation, source, and edit-screen inspection. No case was created, edited, analyzed, deleted, uploaded to, or messaged during the audit.

The main confirmed functional defect is that the case register omits location values that are present on the same case’s detail and map views. A security concern is that there is no application login or authorization layer: case APIs and destructive endpoints are included without authentication, although the documented Docker port bindings limit default access to loopback. Two low-severity accessibility defects were observed: the register search box has no explicit accessible name, and attachment-open links expose only an arrow glyph.

The six requested viewport widths were checked on the main register, map, and conversation surfaces. No document width larger than the viewport was measured. No React page errors or failed local API requests were observed during the settled read-only browser sessions. The legacy Streamlit page emitted browser feature-policy and iframe-sandbox warnings; these did not prevent rendering.

**No application source, configuration, database, environment variable, or case record was changed.** The only deliverables created are this report and screenshots in `website-audit-evidence/`.

## Project architecture and feature inventory

| Layer | Observed implementation |
|---|---|
| Current frontend | React 19 + TypeScript, Vite build, React Router, TanStack Query, Leaflet |
| Legacy frontend | Streamlit, still available while migration is in progress |
| API | FastAPI; React requests `/api` through the web service |
| Case data | SQLite database and local attachment files shared by the two frontends |
| Analysis workflow | n8n; PostgreSQL stores n8n workflow/execution data; analysis uses configured language/vision providers |
| Maps | Leaflet and OpenStreetMap tiles; geocoding service configured separately |
| Local URLs | React `:8601`; legacy Streamlit `:8501`; API `:8000` is internal to the Compose network; n8n `:5678` is loopback-bound by the documented Compose configuration |
| Authentication | No application login/logout or per-user authorization was found in the inspected frontend/API routes. The documented local deployment binds web and Streamlit ports to `127.0.0.1`; this reduces remote exposure but is not user authentication. The runtime value of any webhook token was not inspected. |

### Current React routes

| Route | Purpose |
|---|---|
| `/` | Redirects to the case register |
| `/cases` | Register, summary charts, search and filters, table/cards, CSV export, map links |
| `/cases/map` | Case map with markers |
| `/cases/new` | Two-step new-case flow |
| `/cases/:id/edit` | Edit/review a case, original report, details and attachments |
| `/cases/:id` | Case report and report-version controls |
| `/cases/:id/chat` | Case conversation |
| `/cases/:id/sources` | Original report, attachments, preview-read action and location |
| `/cases/:id/chat/sources` | Conversation with source inspector |
| `/about` | About page, contact links and video |
| `*` | Redirects unknown paths to `/cases` |

### Legacy Streamlit surfaces

The legacy app uses query-driven views rather than separate path routes:

| URL pattern | Purpose |
|---|---|
| `/?view=overview` | Case dashboard, charts, filters, map and table |
| `/?view=new` | Two-step case creation/edit flow |
| `/?view=case&case={id}` | Case report, history, map, attachments and actions |
| `/?view=about` | About page and video |

### API surface discovered

All endpoints are under `/api`:

- **Meta:** `GET /health`, `/meta`, `/samples`, `/geocode`; `GET /assets/{asset_name}`
- **Cases:** `GET /cases`, `GET /cases/export.csv`, `POST /cases`, `GET/PATCH/DELETE /cases/{case_id}`, `POST /cases/{case_id}/suggest`, `POST /cases/{case_id}/analyze`, `GET /cases/{case_id}/versions/{version_id}`, `GET /cases/{case_id}/report.txt`
- **Attachments:** `GET/POST /cases/{case_id}/attachments`, `POST /cases/{case_id}/attachments/read-preview`, `GET/DELETE /attachments/{attachment_id}/file` (the delete route is `/attachments/{attachment_id}`)
- **Messages:** `GET/POST /cases/{case_id}/messages`, `POST /messages/{message_id}/retry`, `POST /messages/{message_id}/update-report`, `DELETE /cases/{case_id}/messages`

## Issue summary

| ID | Severity | Category | Page/Feature | Description | Status |
|---|---|---|---|---|---|
| BUG-001 | Medium | Functional | React case register | Location is missing in list rows/cards although the detail/source view has a location. | Confirmed |
| SEC-001 | Medium | Security | All case/API routes | No application authentication or authorization protects sensitive case reads and mutations. | Confirmed |
| A11Y-001 | Low | Accessibility | React register search | Search textbox has no explicit accessible name; the accessibility snapshot reports an unnamed textbox. | Confirmed |
| A11Y-002 | Low | Accessibility | React attachment rows | Attachment-open links expose only `↗` rather than a descriptive accessible name. | Confirmed |

## Confirmed findings

### BUG-001 — Case register drops populated location

- **Affected URL/feature:** `http://localhost:8601/cases`; React case summary table/cards
- **Category / severity / status:** Functional / Medium / Confirmed
- **Reproduction:**
  1. Open the case register.
  2. Observe the synthetic audit case row/card; its location is shown as “location not specified”.
  3. Open that same synthetic case in the detail/source view; the case has a populated location and appears on the map.
- **Expected:** The register should display the same saved location as the detail view, or a missing-location label only when no location exists.
- **Actual:** The list falls back to “location not specified” for a case whose detail view has a location.
- **Evidence:** Browser snapshots from `/cases`, `/cases/80`, and `/cases/80/sources`; the audit used the pre-existing synthetic record only. `app/db.py:333-334` selects case summary fields but omits `location`. The frontend reads `item.location` at `web/src/App.tsx:494` and `:576`, then falls back to the missing-location label.
- **Likely cause:** The summary query/API payload does not include the location field expected by the React list.
- **Suggested fix:** Include the location in the case-list projection/response and add a regression check that list and detail views agree. No fix was applied.

### SEC-001 — No application authentication/authorization on case APIs

- **Affected URL/feature:** `http://localhost:8601/cases` and all `/api` case, attachment, and message routes
- **Category / severity / status:** Security / Medium / Confirmed
- **Reproduction:**
  1. Open the live website in a fresh browser context at `http://localhost:8601/cases`.
  2. The case register and its records render without a login or identity step.
  3. Source inspection confirms the API routers are registered without an authentication dependency or auth middleware.
- **Expected:** If the service is used by multiple users or exposed beyond the local machine, only authenticated and authorized users should be able to read case data, attachments, or invoke case mutations.
- **Actual:** There is no application login/logout flow or authorization check in the inspected routes. `api/routes/common.py:23-26` checks only whether a case exists; it does not establish a user’s permission. The API also exposes create/update/delete and attachment/message mutation endpoints.
- **Evidence:** Browser access without a login; `api/main.py:33-37` registers the routers; `api/routes/common.py:23-26` only checks case existence; examples of unprotected file and delete handlers are in `api/routes/attachments.py:64-79` and `api/routes/cases.py:99-104`.
- **Likely cause:** The current application is designed as a local single-user tool rather than a multi-user service.
- **Suggested fix:** Before sharing the application across users or exposing it through a network/reverse proxy, add authentication and per-resource authorization across reads, files, exports, and mutations. Keep the existing loopback-only binding unless a protected deployment is configured. This audit did not attempt to access records through guessed identifiers or exploit the issue.
- **Risk qualification:** The documented Compose setup binds the browser-facing ports to `127.0.0.1`, which materially reduces remote reachability by default. It does not protect data from other local processes/users or compensate for exposure after a deployment change.

### A11Y-001 — Register search has no explicit accessible name

- **Affected URL/feature:** `http://localhost:8601/cases`; search field
- **Category / severity / status:** Accessibility / Low / Confirmed
- **Reproduction:** Inspect the register’s accessibility snapshot or navigate to the search field with a screen reader. The field is announced as a generic textbox; its placeholder is present, but no explicit accessible name is reported.
- **Expected:** A stable programmatic label such as “Search cases” should be exposed independently of placeholder text.
- **Actual:** The input is nested in a label containing an icon but no text and has no `aria-label`; see `web/src/App.tsx:305-308`.
- **Likely cause:** The visible placeholder is being used as the only user-facing prompt.
- **Suggested fix:** Add a visible or visually hidden `<label>` text, or an appropriate `aria-label`. No fix was applied.

### A11Y-002 — Attachment-open links are announced as an arrow

- **Affected URL/feature:** `http://localhost:8601/cases/80/sources`; attachment list
- **Category / severity / status:** Accessibility / Low / Confirmed
- **Reproduction:** Inspect the attachment list with the browser accessibility tree. Each file-open link is announced as `↗`, with no filename or clear action in its accessible name.
- **Expected:** Each link should communicate the destination/action and identify the associated attachment.
- **Actual:** The icon-only link has a generic `title` but no `aria-label` or visually hidden text; the observed accessible name is the arrow glyph.
- **Evidence:** Browser accessibility snapshot for the synthetic test case; implementation at `web/src/App.tsx:880-889`.
- **Likely cause:** The link relies on an icon and tooltip title rather than a descriptive link name.
- **Suggested fix:** Provide an accessible label such as “Open attachment [filename]” and retain the visible icon. No fix was applied.

## Test coverage matrix

Statuses are restricted to **PASS**, **FAIL**, **BLOCKED**, and **NOT TESTED**. “BLOCKED” means the operation was deliberately not executed because it could modify application data or the browser tool could not reliably perform the action.

| # | Page / scenario | Status | Notes |
|---|---|---|---|
| 1 | React root `/` | PASS | Redirected to the case register. |
| 2 | React `/cases` register | PASS | Loaded; summary, charts, list/table and controls rendered. |
| 3 | Search and reset | PASS | Typed a synthetic no-match query, verified empty state/zero visible rows, then cleared it. |
| 4 | Type filter | PASS | Direct filtered URL returned the matching synthetic record; filter state remained in the URL. |
| 5 | Severity/status filters | PASS | Controls were present; exhaustive combinations were not tested. |
| 6 | Sorting and pagination | NOT TESTED | No sorting or pagination control was discovered in the current register. |
| 7 | React `/cases/map` | PASS | Map and tiles loaded; zoom controls and the empty/result map layout rendered. |
| 8 | Map marker popup/drag/zoom interaction | NOT TESTED | Map rendering was checked; marker and map interactions were not exhaustively exercised. |
| 9 | React `/cases/new` step 1 | PASS | Blank form rendered; below-minimum synthetic text showed 11/20 and kept “Next” disabled. No submit occurred. |
| 10 | Create-case submit / step transition | BLOCKED | Would create persistent case data; prohibited by the read-only scope. |
| 11 | React `/cases/:id` report | PASS | Read-only report view rendered for the synthetic audit case. |
| 12 | Report version restore/download | BLOCKED | Avoided operations that could expose/export case content or change the active report. |
| 13 | React `/cases/:id/edit` | PASS | Synthetic case fields, original report and attachment list rendered; no edits were saved. |
| 14 | Save/edit/reanalyze | BLOCKED | Would modify a case and/or trigger external analysis. |
| 15 | React `/cases/:id/chat` | PASS | Empty state rendered; send remained disabled when empty. |
| 16 | Send/retry/clear/update-report chat operations | BLOCKED | Would persist conversation/report data or trigger model processing. |
| 17 | React `/cases/:id/sources` | PASS | Original text, attachments and location panels rendered for synthetic data. |
| 18 | React `/cases/:id/chat/sources` | PASS | Combined conversation/source layout rendered. |
| 19 | Upload/delete attachment or run read-preview | BLOCKED | Upload/delete would alter data; read-preview may submit attachment contents for analysis. |
| 20 | Download/export case files or CSV | BLOCKED | Avoided exporting potentially sensitive records and attachments. |
| 21 | React `/about` | PASS | Content rendered; video resource reached ready state with no media error. |
| 22 | About video playback | BLOCKED | A click could not be reliably confirmed as a trusted user gesture by the automation session; no playback defect is claimed. |
| 23 | Unknown React path | PASS | Redirected to `/cases`. |
| 24 | Direct URL, refresh, back/forward | PASS | Register and map routes survived direct navigation, refresh, back and forward. |
| 25 | Arabic/English rendering | PASS | Both language query modes rendered the expected headings; browser language preference was restored to Arabic afterward. |
| 26 | Responsive widths: 320, 375, 390, 768, 1024, 1440 px | PASS | Root scroll width did not exceed the viewport on register, map and conversation surfaces. |
| 27 | Legacy Streamlit `/?view=overview` | PASS | Overview, filters, map and table rendered. |
| 28 | Legacy Streamlit `/?view=new` | PASS | Empty form rendered. No case was submitted; its submit-time validation could not be confirmed through the browser tool. |
| 29 | Legacy Streamlit `/?view=case&case=80` | PASS | Read-only synthetic case view rendered. |
| 30 | Legacy Streamlit `/?view=about` | PASS | About content rendered; video reached ready state. |
| 31 | Login/logout | NOT TESTED | No login/logout workflow or UI was found; the absence is covered by SEC-001. |
| 32 | API access logs/container logs | BLOCKED | The API port is internal to the Compose network; host log files available for inspection were empty. No container log inspection was performed. |
| 33 | Performance benchmark/load testing | NOT TESTED | No repeatable benchmark or concurrency test was run; this audit was focused on safe functional/browser checks. |
| 34 | Full keyboard/screen-reader audit | NOT TESTED | Accessibility-tree observations were made, but a complete keyboard and assistive-technology pass was not possible. |

**Coverage summary:** 34 scenarios listed: **21 PASS, 8 BLOCKED, 5 NOT TESTED**. The four confirmed findings are tracked separately from scenario status; a route can pass its read-only rendering check while a mutation workflow on that route is blocked.

## UI/UX and responsive observations

- Register and map surfaces were measured at **320, 375, 390, 768, 1024 and 1440 px**. No document-level width greater than the viewport was observed on the tested register, map and conversation views.
- The mobile register intentionally makes the summary strip horizontally scrollable; this was not classified as page-level overflow.
- The map rendered at desktop and mobile test widths. Individual marker popups and touch gestures were not exercised.
- New-case validation was visibly communicated in the React form with a 20-character minimum and disabled continuation for a short input. The legacy Streamlit form showed an enabled Next action at zero characters; the submit-time guard was not confirmed in the browser, so this is recorded as an optional UX review item rather than a confirmed bug.
- The current React UI and legacy Streamlit UI are both running and share the same case database/files. This is consistent with the README’s migration note but may confuse users about which interface is authoritative; no functional failure was confirmed from having both online.

## Technical and security observations

- **Console:** No React page errors or console errors were observed during settled register/map sessions. Streamlit emitted browser warnings for unrecognized feature-policy names and a sandboxed iframe with both `allow-scripts` and `allow-same-origin`. These are recorded as framework/browser warnings, not as a confirmed exploitable vulnerability.
- **Network:** No failed local API request was observed during settled React register/map sessions. The about video request sometimes reported `ERR_ABORTED` when navigating away, but a later observation showed the media element at ready state 4 with no media error. This is consistent with a canceled in-flight request and is not classified as a broken asset.
- **Service status:** The live header reported the analysis service as ready. The model identifier was visible in the service tooltip; no credential or token value was inspected or included.
- **Input handling:** Source inspection found minimum-length validation on case text and validation of case type. No malformed persistent mutation request was sent.
- **Output handling:** Reviewed case strings are rendered by React text nodes; map popup text uses text nodes for case titles/numbers. No unsafe output-rendering issue was confirmed in the inspected paths.
- **Deployment/configuration:** The README states that browser-facing ports are loopback-bound by default. The runtime value of `ALPHA_WEBHOOK_TOKEN` and other secrets was deliberately not inspected. The README documents that an empty webhook token disables that layer, so verify the token is configured wherever n8n is exposed beyond the trusted local setup.
- **Logs/performance:** Local `streamlit.log` and `streamlit-error.log` yielded no content. The internal FastAPI container logs were not inspected. No load, latency, or asset-size benchmark was run.

## Evidence

Screenshots contain only the new-case form with synthetic short input and a filtered map view; no case report or attachment content is included.

- [New-case minimum-length state](./website-audit-evidence/new-case-min-length.png)
- [Filtered case map](./website-audit-evidence/map.png)

Browser evidence was also recorded in accessibility snapshots and route/navigation results during the audit. No screenshot was captured of the real case record.

## Prioritized action plan

1. **Review SEC-001 before any shared/network deployment.** Decide whether the product remains strictly single-user and loopback-only or needs authentication and per-resource authorization.
2. **Correct BUG-001.** Add location to the case-list response and validate list/detail consistency.
3. **Address A11Y-001 and A11Y-002.** Add explicit accessible names to search and attachment links.
4. **Run the blocked mutation workflows only with an isolated disposable database and fixture set.** Cover create, edit, analyze, upload, conversation, report version restore, export, and deletion after authorization.
5. **Complete a separate keyboard/screen-reader and performance pass.** Include dialog focus management, map keyboard access, representative attachment sizes, and API latency under a controlled test fixture.

## Limitations and audit boundary

- This was a browser-backed, read-only audit, not a penetration test or complete accessibility certification.
- The audit did not inspect or change database files, environment files, secrets, or container volumes.
- A pre-existing synthetic case was used for read-only rendering checks; the real case was not opened or modified.
- Operations that could persist data, remove data, trigger analysis, send case content to an external model, or export user records were intentionally not performed.
- Some browser actions (notably media playback and a few button activations) could not be reliably confirmed by the automation tool. They are marked **BLOCKED**, not reported as reproduced defects.
- Only page/feature coverage documented in the matrix is claimed. No full application coverage is claimed.
