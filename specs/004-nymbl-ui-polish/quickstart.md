# Quickstart: Verifying the Nymbl UI Polish

Manual + scripted verification path for the work in this feature. The list is deliberately concrete — a reviewer should be able to follow it cold.

## Prerequisites

- Docker running with `make up` (or `docker compose up`) on a fresh machine.
- A Gemini API key in `.env`.
- A modern browser (Chrome / Edge / Firefox / Safari, current).
- For dark-mode verification: OS appearance toggle accessible.
- For reduced-motion verification: OS reduce-motion toggle accessible (macOS: System Settings → Accessibility → Display → Reduce motion; Windows: Settings → Accessibility → Visual effects → Animation effects).

## 1. Bring the app up

```bash
make up
```

Open <http://localhost:8000/> in the browser.

## 2. Visual brand audit (light mode)

With OS appearance set to **light**:

- [ ] Background is warm off-white (paper), not pure white or cool gray. Sample any background pixel with the browser dev tools color picker and confirm `rgb(245, 241, 232)` (`--paper-50`).
- [ ] The page heading "RAG Demo" renders in **Fraunces** (serif). Disable web fonts in dev tools and confirm it falls back to Georgia / Iowan Old Style.
- [ ] The textarea, buttons, and body text render in **Geist Sans**. Disable web fonts and confirm fallback to system sans.
- [ ] The "Ask" button is the *only* chartreuse element on the screen (the brand `--signal-500` accent). No other large fill carries chartreuse.
- [ ] Body text is ink-dark, not pure black. Sample → confirm `rgb(10, 10, 15)` (`--ink-900`).
- [ ] No purple anywhere — the upload-progress card uses stone + signal + success, not the old `#5e35b1` purple.
- [ ] No `#ffffff` surface anywhere — every card background resolves to a paper or stone token.

## 3. Visual brand audit (dark mode)

Toggle OS appearance to **dark** and refresh:

- [ ] Page renders dark **on first paint**. There is no flash of the light theme. (Disable cache and refresh several times to confirm.)
- [ ] Body background is `--ink-900` (`#0A0A0F`).
- [ ] Body foreground is `--paper-50` — warm, not pure white.
- [ ] The "Ask" button is still chartreuse with ink-dark text on it (the accent does not invert).
- [ ] Citation chunk_ids and the page badge are legible Geist Mono with tabular numerals (numbers align vertically in stacked citations).

## 4. Error feedback verification

### 4a. Server error (5xx)

In a separate terminal:

```bash
docker compose stop db
```

This will make queries fail with an upstream provider error (the chunk repo can't connect). Submit a question.

- [ ] Within **2 seconds**: the "Thinking…" indicator clears, the **"Ask" button re-enables**, and a card titled "Server error" appears in the response area with body copy "Something went wrong on our end. Please try again." and a Retry button.
- [ ] The card has `role="alert"` (inspect the DOM).
- [ ] The card does **not** contain the raw `psycopg` / connection-error text.
- [ ] Clicking Retry re-submits the same question without page reload.

Bring the DB back up: `docker compose start db`.

### 4b. Validation error (4xx)

Submit a query with an empty textarea (the browser will block this — temporarily remove `required` in dev tools, or use curl). Alternatively, attempt to upload a non-PDF file.

- [ ] Card reads "Invalid input" with body "We couldn't process that request. Please review and try again."
- [ ] The raw `ValueError` or `InvalidPDFError` message is **not** displayed.

### 4c. Network error (client-side)

In dev tools → Network tab → throttle to "Offline." Submit a question.

- [ ] Within **5 seconds**: card reads "Network error" with body "Couldn't reach the server. Check your connection and try again." and a Retry button.
- [ ] The indicator clears; the Ask button re-enables.

Set network back to "Online" and click Retry. The query succeeds.

### 4d. Timeout

Force a query slower than 60 s (instrument `answer_question` with a sleep, or stop Gemini mid-call).

- [ ] At ~60 s, the same "Network error" card appears.

## 5. Loading indicator polish

- [ ] Submit a normal query. The "Thinking…" text appears in Geist Sans, chartreuse (`--signal-600`), at body-lg weight. It **pulses** between 0.45 and 1.0 opacity on a 1.5 s cycle.
- [ ] When the answer arrives, the indicator disappears with no layout jump.
- [ ] Enable OS reduce-motion. Reload. Submit a query.
  - [ ] The "Thinking…" text appears **static** (full opacity, no pulse animation).

## 6. Replace-document confirmation

- [ ] Start with **no document ingested** (run `docker compose exec db psql ... -c 'TRUNCATE chunks CASCADE'` if needed). Click the paperclip and pick a PDF. Upload proceeds with **no confirmation dialog**.
- [ ] After upload completes, click the paperclip and pick another PDF.
  - [ ] Browser shows a `confirm()` dialog: "Replace the current document? This cannot be undone."
  - [ ] Click **Cancel** → no upload starts; the existing document is unchanged in the `#current-doc` indicator.
  - [ ] Click the paperclip again and pick the same PDF. This time click **OK** → upload proceeds normally and replaces the document.

## 7. Screen reader smoke test (manual)

With VoiceOver (macOS) or NVDA (Windows) enabled:

- [ ] Submit a question. The answer is announced when it arrives ("polite").
- [ ] Force a server error (see 4a). The error is announced **immediately and preempts** any in-flight speech (the `role="alert"` behavior).
- [ ] Start an upload. Stage transitions are announced politely.

## 8. Automated checks

```bash
make test
```

The new tests MUST pass:

- `tests/unit/test_ui_routes.py::test_query_503_renders_server_category`
- `tests/unit/test_ui_routes.py::test_query_400_renders_validation_category`
- `tests/unit/test_ui_routes.py::test_upload_409_renders_concurrent_category`
- `tests/unit/test_ui_routes.py::test_upload_413_renders_validation_category`
- `tests/unit/test_ui_routes.py::test_upload_invalid_pdf_renders_validation_category`
- `tests/unit/test_ui_routes.py::test_error_partials_carry_role_alert`
- `tests/unit/test_ui_brand_contract.py::test_css_tokens_defined`
- `tests/unit/test_ui_brand_contract.py::test_no_forbidden_strings_in_styles`
- `tests/unit/test_ui_brand_contract.py::test_aria_attributes_on_base_template`
- `tests/unit/test_ui_brand_contract.py::test_error_templates_dont_emit_raw_backend_strings`

```bash
make lint
```

ruff MUST pass. No new lint warnings.

## 9. README screenshot refresh (Article VIII reminder)

If the README references any screenshots of the old UI, replace them with shots of the new design (light + dark side-by-side) before final commit. This keeps the README narratable per constitution Article VIII.3.

## 10. Demo dry-run

Per constitution Article VIII.6, run a full 30-minute demo dry-run end-to-end against this feature. Time it. The polish should not extend the architecture walkthrough or query flow — it lives entirely in the live demo's "what the reviewer sees" surface.

---

If every checkbox passes and `make test` + `make lint` are green, the feature is ready for tasks → implementation → commit → PR.
