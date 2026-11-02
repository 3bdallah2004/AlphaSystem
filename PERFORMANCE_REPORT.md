# Performance fixes — 2026-10-28

## Live slowdown investigation (follow-up, 2026-10-28)

The user reported slow field extraction/analysis after the initial report. The live Docker stack was then inspected; these observations supersede the earlier limitation that no live timings had been obtained, but do not establish a controlled before/after deployment benchmark.

- Read-only requests to `/`, `/api/meta`, `/api/cases`, and one case detail returned in 4.8–13.9 ms during the check.
- Recent extraction execution 1522 took 31.969 s, with 31.861 s in `Suggest with LLM`, using provider 1 / `gemini-flash-lite-latest`. It produced 44 completion tokens from 249 prompt tokens.
- Recent analysis execution 1525 took 32.187 s, with 31.195 s in `Call LLM`, using the same provider/model. It produced 759 completion tokens from 366 prompt tokens.
- Earlier same-provider executions on October 27 included extraction at 2.007 s and analysis at 3.368 s for a different 302-character complaint. These historical samples confirm substantial variability; they are not identical-input benchmarks or proof of deployment causation.
- Two concurrent synthetic extraction requests with identical, short, non-sensitive source text were sent through n8n to compare configured keys: provider 1 succeeded (HTTP 200) in 21.300 s; provider 2 failed (webhook HTTP 502) in 12.174 s. Its workflow record contained upstream `503`, `UNAVAILABLE`, and `high demand` indicators.
- The observed delay is concentrated inside the workflow's outbound model request, which includes provider/network time. The backup-key probe also demonstrates current upstream capacity trouble. These observations do not justify switching the primary key or claiming a code change will remove this delay. No provider order, model, timeout, or application code was changed during this investigation.

Scope: new-case analysis, complaint-field extraction, conversation generation, and their shared HTTP/database paths. Existing unrelated working-tree changes, including theme work, were preserved. No provider/model changes or dependencies were introduced.

## 1. New Case Analysis

**Trace:** React creates a draft through `POST /api/cases` (zero AI calls). Entering the new-case details step requests `suggest`; saving and requesting analysis calls `analyze`, which starts a background worker. n8n routes `suggest`, `analyze`, and `chat` to separate branches. Extraction does not run full analysis. Attachments can require additional extraction/vision requests.

**Bottlenecks:** the analysis worker started optional geocoding concurrently but joined it before saving the completed AI report. Saving a location could also synchronously wait for geocoding. Duplicate analysis requests launched redundant workers even though stale results were subsequently discarded.

**Changes:** geocoding runs independently, with duplicate lookup suppression and a conditional database update that cannot replace a subsequently edited location/pin. The report becomes available immediately after analysis and persistence. Identical in-flight analysis submissions share one worker; changed source/configuration starts a new generation. Completed reports can still be explicitly reanalyzed. Saving/analyzing is guarded against duplicate UI clicks.

**Measurements:** a local synthetic test with 50 ms provider delay and 250 ms geocoder delay measured the old blocking join at **251.667 ms**, versus **95.580 ms** until the new report was saved. A final repeat measured **257.362 ms / 197.009 ms**; that repeat uses an event gate to prove deterministically that report persistence finishes while geocoding is still blocked. These are component tests, not production end-to-end measurements; scheduling/SQLite overhead varies on this machine.

## 2. Automatic Field Population

**Trace:** extraction starts once on entering the details step of the new-case flow, rather than on each keystroke. The backend validates the suggested JSON fields and returns them together. There was no successful-result cache or coalescing of simultaneous duplicate requests.

**Changes:** successful extraction results are cached in memory for five minutes, with a 128-entry bound. Keys include database path, case ID, language, exact complaint-text hash, and processing-configuration hash. Simultaneous identical requests share one pending result; failures are not cached. Calls without a case scope remain uncached. Source/configuration changes select a different cache entry. Date validation now rejects impossible calendar dates.

The UI aborts/disregards obsolete suggestions and their location lookups. An older response cannot replace fields after the original complaint text changes or after saving/unmounting. Existing field-preservation rules remain in place. The API also checks whether the stored source changed while extraction ran and returns HTTP 409 in that case. A fast-response hydration race discovered by the frontend regression test was fixed by synchronizing the source reference when loading case data.

**Measurements:** with a synthetic 80 ms provider delay, uncached extraction measured **80.709 ms**, versus **0.156 ms** for a warm scoped cache hit. The final repeat measured **81.795 ms / 0.313 ms**. Cold requests still incur provider latency. These timings exclude browser rendering/network transfer and do not establish live extraction accuracy or live provider speed.

## 3. Conversational Responses

**Trace:** a submitted message creates a user message and a pending reply, then a background worker builds context and invokes the chat workflow. The browser polls for completion. Existing case analysis is reused; ordinary text chat does not trigger another analysis/extraction. Referenced cases and file attachments can add context work.

**Bottlenecks:** overview generation listed cases and reopened the database once per case, processed the entire register before truncation, and repeated focused-case summary text. History loaded all messages and transformed usable messages twice. Message polling performed one attachment query per message. Three-second polling added avoidable display delay after the reply/report was ready.

**Changes:** one cursor supplies the overview and stops at the existing 30,000-character budget; the focused case remains available separately. History is read newest-first up to the existing 20-message limit, transformed once, and bounded before the current message ID so later questions cannot contaminate an earlier reply. Polling attachments uses one joined query. Pending chat/analysis polling now runs every second; this reduces the nominal polling-delay bound from three seconds to one, at the cost of more requests while pending.

Chat submission IDs and content fingerprints are stored atomically with the user/pending-reply pair. Repeating the same transport request reuses its existing turn and worker; using its ID with different content is rejected. A distinct submission ID still allows intentionally repeated questions. Retry transitions are atomic, preventing concurrent retries of one failed response. Frontend guards prevent same-tick duplicate clicks and preserve a submission ID across a transport failure retry.

**Measurements:** with 121 synthetic cases, the old list-plus-per-case reads took **679.592 ms**, while the new bounded overview took **16.141 ms**; final repeat: **876.524 ms / 9.676 ms**. Overview database queries changed from **122 to 1**. The baseline measures the old read pattern; the new measurement also includes overview formatting. These are context-preparation measurements, not total AI response latency. Live time to first content and total response latency were not measured.

**Streaming:** not implemented. The current n8n/webhook path buffers the entire reply, including structured action proposals that are parsed and validated before display. The existing completed-response protocol was retained. Independent, genuinely distinct chat turns may still execute concurrently; there is no new FIFO queue, and a follow-up sent before an earlier response completes cannot include that unfinished response.

## Shared infrastructure and AI call counts

Python provider/webhook requests now reuse HTTP connection pools across short-lived workers, while each call gets an isolated Session for cookies, headers, and authentication. A local HTTP/1.1 test verified three calls across fresh worker threads used one TCP connection, with no credential/cookie leakage. The adapter adds no automatic retries; existing provider-fallback/error behavior remains intact.

`Server-Timing: app;dur=...` exposes API request handling time through response headers. This measures handling until the response headers, not background-job completion or provider-only latency. Existing workflow/phase timing logs remain available; cache-hit and asynchronous geocoding timing logs were added without recording complaint text or credentials.

| Text-only successful path, without provider fallback | Before | After |
|---|---:|---:|
| Create draft | 0 AI calls | 0 |
| Cold extraction then explicit analysis | 2 | 2 |
| Repeat identical successful extraction within cache window | 1 | 0 |
| Two simultaneous identical extraction requests | 2 | 1 |
| Two identical in-flight analysis submissions | 2 | 1 |
| Ordinary chat message | 1 | 1 |
| Duplicate transport submission of the same chat turn | 2 | 1 |

Counts refer to the corresponding generation requests, not attachment vision calls or provider fallback attempts. No essential analysis step was removed to reduce call counts.

## Files changed for this task

Some listed files also contain changes that predated this task; this list describes only the performance-related contributions.

| File | Performance-related change |
|---|---|
| `app/analysis.py` | Scoped extraction cache, concurrent-request coalescing, date validation, in-flight analysis deduplication, nonblocking guarded geocoding, pooled HTTP usage. |
| `app/chat.py` | Bounded cursor context/history, current-turn history cutoff, batched attachments, idempotent submissions, guarded retries. |
| `app/db.py` | Additive nullable request ID/fingerprint columns and unique partial index; atomic turn/retry helpers; cursor/join helpers. Existing rows retained. |
| `app/http_pool.py` (new) | Shared HTTP transport pools with per-request Session state. |
| `app/llm.py`, `app/extract.py` | Use the pooled transport wrapper. |
| `api/main.py` | Server-Timing header. |
| `api/routes/cases.py` | Asynchronous location enrichment; scoped suggestions and stale-source conflict detection. |
| `api/routes/messages.py` | Accept optional bounded request ID; reject conflicting reuse. |
| `web/src/App.tsx` | Duplicate submission guards, stable chat request IDs, stale extraction protection, one-second pending polling, source-reference race fix. |
| `web/src/api/client.ts` | Pass cancellation signal to suggestion requests. |
| `tests/test_performance.py` (new) | Reproducible synthetic timings and cache/deduplication/history regression checks. |
| `tests/test_http_pool.py` (new) | Connection reuse, concurrent state isolation, zero automatic retries. |
| `tests/test_api_messages.py` | Update mocked chat signatures for optional request ID. |
| `tests/test_chat_actions.py` | Mark retry fixture failed before retrying, matching the endpoint contract. This file existed untracked before these edits. |
| `web/src/App.test.tsx` | Delayed extraction/rapid source-edit regression coverage. |
| `PERFORMANCE_REPORT.md` (new) | This report. |

## Verification actually executed

Run backend commands from the repository root, frontend commands from `web/`.

| Command | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests -q` | **365 passed, 3 skipped**, 49.82 s. Skips are opt-in live vision/provider tests requiring `ALPHA_LIVE=1`. |
| `.\.venv\Scripts\python.exe -m pytest tests/test_performance.py tests/test_api_messages.py tests/test_chat_actions.py -q -s` | **54 passed**, 20.66 s; first measurements reported above. |
| `.\.venv\Scripts\python.exe -m pytest tests/test_performance.py tests/test_http_pool.py -q -s` | Final focused run: **9 passed**, 9.73 s; repeat measurements reported above. |
| `npm.cmd test -- --reporter=dot` | **37 passed**, two files, 20.13 s. |
| `npm.cmd run build` | Passed TypeScript `tsc -b` and Vite production build; Vite build 11.88 s. |
| `git diff --check` | Passed; only existing LF/CRLF conversion notices. |

No lint command is configured in the frontend package. Initial checks exposed two outdated mocks, a retry fixture with the wrong status, the fast extraction hydration race, and a timing-sensitive geocode assertion; each was corrected and the relevant checks rerun. The geocode assertion now uses synchronization rather than assuming scheduler speed.

## Limits and manual verification

- No live paid/provider request was sent for these measurements. Browser end-to-end timings, live output accuracy, long/short complaint comparisons, and live follow-up response quality still require the configured service stack. No production-speed percentage is claimed.
- Cache, extraction coalescing, and analysis-worker deduplication are process-local. They do not coordinate independent API processes; chat request-ID persistence does coordinate through the shared SQLite database. A durable distributed job queue was not introduced.
- This application already has a global investigator conversation. The work preserves that access model; it does not add multi-user tenancy. Extraction cache keys include case/database scope, and existing API access checks remain in place.
- Source changes invalidate cache reuse through their key; old entries remain only within the bounded memory cache until eviction/expiry.
- Provider latency, attachment OCR/vision, provider fallback, and large meaningful case context can still dominate real requests. Existing prompt/output budgets were retained to avoid an unmeasured accuracy tradeoff.

For manual verification with the services running:

1. Create a short complaint and enter its details step. Inspect the Network panel for one suggest request. Repeat for a long complaint. Verify names, dates, location, missing values, and manually edited fields against the source.
2. Delay the suggest request and change the complaint before it resolves. Confirm that the old response does not fill fields. Repeat identical scoped requests to check cache reuse; modify the source to confirm a fresh request.
3. Save/analyze twice quickly. Confirm one in-flight analysis worker and a usable report without waiting for location lookup. Edit the location/pin during a lookup and verify it is preserved.
4. Send a case question and, after completion, a factual follow-up. Retry the same request ID after a simulated transport failure and confirm one user/reply pair. A different payload using that ID should return 409. Check rapid distinct submissions remain associated with their own questions.
5. Compare browser request durations, Server-Timing, and workflow phase logs under the same provider/model/input and warmed/cold conditions. Measure visible completion separately from request acceptance; background jobs are not represented by the POST duration alone.
