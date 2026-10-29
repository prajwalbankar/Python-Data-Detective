# Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A professional "Clean analyst" web UI for Python Data Detective that runs on localhost and offers every terminal feature.

**Architecture:**
- `web_api.py` holds a `DetectiveApi` class that turns `(method, path, query, body)` into a `Response`, using `Dataset`, `Investigator` and `Report` unchanged.
- `web_app.py` is thin `http.server` glue that serves `web/index.html`, `style.css` and `app.js`.
- The page is vanilla JavaScript that calls the JSON API.

**Tech Stack:** Python 3.9+ standard library (`http.server`, `json`, `threading`, `tempfile`, `webbrowser`, `urllib.parse`), with HTML, CSS and vanilla JavaScript. Tests use `unittest` and `urllib.request`. The front end is checked in the in-app browser.

**Spec:** `docs/2026-10-29-web-ui-design.md`. Section numbers below (e.g. §5) refer to it. The program spec is `docs/2026-10-26-python-data-detective-design.md`.

## Global Constraints

- **Standard library only.** The page loads nothing from the internet: no CDNs and no web fonts.
- **Localhost only.** The server binds to `127.0.0.1` and tries ports 8000–8010.
- **`main.py` behaviour is unchanged.** The existing 113 tests stay green.
- **Professional copy:** sentence case, no slang, no "!". Program messages are shown as they are, with the first letter capitalised.
- **Data goes into the page with `textContent` only, never `innerHTML`.**
- **Every new Python function and class has a docstring and type hints** (the `test_docs` check enforces this).
- **Limits:** `MAX_UPLOAD_BYTES = 200 * 1024 * 1024`, `MAX_OPEN_CASES = 20`, `LIST_LIMIT = 100`.
- **Bands:** `{"Case closed": "good", "Minor clean-up": "fair", "Needs cleaning": "poor", "Unreliable": "bad"}`.
- **Tests:** `python -m unittest discover -s dev_tests -v` from the project root. Commit only when it exits 0. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **An uploaded file name with spaces or accents** (e.g. `ventes été 2024.csv`) arrives URL-encoded. The case must show the real name, and the saved report must use it. Covered in Task 2.
2. **Data containing HTML** (`<script>alert(1)</script>` in a cell or column name) must appear as text. The API passes it through unchanged (Task 3), and the page check covers it (Task 7).
3. **The server restarting while the page is open:** an unknown case id gives a friendly 404 that the page shows as a banner. Covered in Tasks 1 and 7.
4. **Two requests at once on the same case** (double clicks, a slow file) must not break the shared state. Covered in Task 5, a threaded test.
5. **A very wide file** (1,000 columns) must return every profile and keep the page usable. Covered in Task 3 (the API) and Task 7 (the page).

---

### Task 1: `DetectiveApi` core: routing, locker, opening a case, evidence

**Files:**
- Create: `python_data_detective/web_api.py`
- Test: `dev_tests/test_web_api.py`

**Interfaces:**
- Produces:
  - `class ApiError(Exception)`, created as `ApiError(status: int, message: str)`
  - `class Response` with `status: int`, `content_type: str`, `body: bytes` and `headers: dict[str, str]`, and the module helpers `json_response(status: int, data: dict) -> Response` and `text_response(text: str, filename: str) -> Response`
  - `DetectiveApi(datasets_dir: str, reports_dir: str, upload_dir: str, base_dir: str)`
  - `DetectiveApi.handle(method: str, path: str, query: dict, body: bytes) -> Response`, which never raises
  - `list_locker() -> dict`, `open_locker(name: str) -> dict`, `evidence(case_id: str) -> dict`
  - module functions `case_summary(case_id: str, dataset: Dataset) -> dict` and `capitalise(message: str) -> str`
  - `self.cases: dict[str, Dataset]`, `self.findings: dict[str, Findings]`
- Consumes: `main.list_csv_files`, `report.DELIMITER_NAMES`, `Dataset`, `DatasetError`.

- [ ] **Step 1: Write the failing tests**

`setUp` puts `t.csv` (`SAMPLE_TEXT`) and `e.csv` (empty) in a temp datasets folder, and makes `api = DetectiveApi(datasets, reports, uploads, base)`. The helper `call(method, path, body=b"", query=None)` returns `(status, json.loads(body))`.

| Test | Call | Assertions |
|---|---|---|
| `test_locker_lists_csv_files` | `GET /api/locker` | 200, `[d["name"] for d in datasets] == ["e.csv", "t.csv"]`, and `"bytes"` for `t.csv` equals the file size |
| `test_open_from_locker` | `POST /api/cases/locker` with `{"name": "t.csv"}` | 200; `case == {"id": "c1", "name": "t.csv", "rows": 10, "columns": 2, "delimiter": "','", "encoding": "utf-8", "warnings": []}` |
| `test_open_refused_file_reports_reason` | open `e.csv` | 422, `{"error": "File is empty"}` |
| `test_unknown_or_unsafe_locker_names` | `"nope.csv"`, `"../t.csv"`, `"a/b.csv"` | 404, `"There's no dataset called '<name>' in the evidence locker."` |
| `test_evidence` | open `t.csv`, then `GET /api/cases/c1/evidence` | `header == ["a","b"]`, `preview[0] == ["1","x"]`, `len(preview) == 5`, `blank_lines_skipped == 0`, `trailing_delimiters is False` |
| `test_unknown_case` | `GET /api/cases/c99/evidence` | 404, `"This case is no longer open. Open it again from the evidence locker."` |
| `test_unknown_path_and_method` | `GET /api/nothing`; `DELETE /api/locker` | 404 `"Not found."`; 405 `"Method not allowed."` |
| `test_unexpected_error_is_hidden` | patch `Dataset` to raise `RuntimeError("boom")` | 500, `"Something went wrong. Details are in the terminal."` |

- [ ] **Step 2: Run them to check they fail**

Run: `python -m unittest discover -s dev_tests -p "test_web_api.py" -v`
Expected: `ModuleNotFoundError: No module named 'web_api'`.

- [ ] **Step 3: Implement `web_api.py` (§5 and §8)**

- **Routing:** match on `(method, path parts)`. `/api/cases/<id>/...` looks up `self.cases`.
- **`handle` error mapping:**
  - `ApiError` → its status;
  - `DatasetError` → 422 with `capitalise(str(err))`;
  - `MemoryError` → 413;
  - any other exception → 500, with `traceback.print_exc()` printed by the server.
- **Locker names** are rejected with 404 if they contain `/`, `\` or `..`, or aren't in `list_csv_files(self.datasets_dir)`.
- **Locking:** `handle` runs every request inside `with self.lock:`, where `self.lock` is a `threading.Lock()`. The server is threaded, but the state is shared (§4).

- [ ] **Step 4: Run them to check they pass**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test passes.

- [ ] **Step 5: Commit**: `feat: add web API core (locker, open case, evidence)`

---

### Task 2: Uploads, the open-case limit, out of memory

**Files:** Modify `web_api.py`; test in `dev_tests/test_web_api.py`.

**Interfaces:**
- Produces:
  - `open_upload(name: str, data: bytes) -> dict` (route `POST /api/cases/upload?name=`)
  - `safe_file_name(name: str) -> str`, which returns the base name, or `"upload.csv"` when that is blank, `.` or `..`
- Consumes: Task 1's `case_summary`.

- [ ] **Step 1: Write the failing tests**

| Test | Assertions |
|---|---|
| `test_upload_csv` | `POST /api/cases/upload` with query `{"name": "ventes été 2024.csv"}` and body `SAMPLE_TEXT.encode()` → 200, `case["name"] == "ventes été 2024.csv"`, `case["rows"] == 10` (Review Focus 1) |
| `test_upload_png_is_named` | body `b"\x89PNG\r\n\x1a\n\x00\x00"` → 422, `error == "This is a PNG image, not a CSV file"` |
| `test_upload_too_big` | patch `web_api.MAX_UPLOAD_BYTES` to 10; body of 11 bytes → 413, `"Files over 200 MB can't be uploaded."` |
| `test_safe_file_name` | `"../../x.csv"` → `"x.csv"`; `"C:\\a\\b.csv"` → `"b.csv"`; `""` → `"upload.csv"`; `".."` → `"upload.csv"` |
| `test_open_case_limit` | open `t.csv` 21 times → `"c1" not in api.cases`, `"c21" in api.cases`, `len(api.cases) == 20` |
| `test_out_of_memory` | patch `web_api.Dataset` with `side_effect=MemoryError` → 413, `"This file is too large for this computer's memory."` |

- [ ] **Step 2: Run them to check they fail.** Expected: 404 or AttributeError failures.
- [ ] **Step 3: Implement the uploads.**
  - `safe_file_name` splits on both `/` and `\`.
  - Each upload is written to `tempfile.mkdtemp(dir=self.upload_dir)/<safe name>`.
  - The limit check drops the oldest entry from `self.cases` (dicts keep insertion order), together with its findings.
- [ ] **Step 4: Run the full suite.** Expected: every test passes.
- [ ] **Step 5: Commit**: `feat: accept uploaded files in the web API`

---

### Task 3: Findings JSON, saving, report download

**Files:**
- Modify: `web_api.py` and `python_data_detective/report.py`.
- Test: `dev_tests/test_web_api.py`. The existing report tests must stay green.

**Interfaces:**
- Produces:
  - in `report.py`: `sub_score_notes(findings: Findings) -> list[tuple[str, float, str]]`, which returns `(label, score, note)` for Completeness, Uniqueness and Validity. The note has no surrounding brackets, e.g. `"3.3% of cells missing"`. `Report._score_lines` uses it, so the wording lives in one place.
  - in `web_api.py`: `findings_json(findings: Findings, summary: dict) -> dict` (§5), `investigate(case_id) -> dict`, `save(case_id) -> dict` and `report_text(case_id) -> str`. The route for `GET .../report.txt` returns `text_response(text, "<stem>_report.txt")` with the header `Content-Disposition: attachment; filename="<stem>_report.txt"`.
- Consumes: Task 1's routing and `self.findings`.

- [ ] **Step 1: Write the failing tests**

| Test | Assertions |
|---|---|
| `test_investigate_sample` | `score == 48`, `band == "bad"`, `verdict == "Unreliable evidence - investigate before use"`, `duplicates == {"total": 1, "items": [{"line": 11, "original": 2}]}`, `sub_scores[0] == {"name": "Completeness", "score": 50.0, "note": "10.0% of cells missing"}`, the suspect for column `a` has `examples == [{"value": "bad", "line": 9}]`, `len(profiles) == 2`, `case_number` matches `^\d{8}-\d{4}$` |
| `test_profiles_shape` | column `a`: `kind == "numeric"`, `stats["max"] == 7.0`; column `b`: `kind == "text"`, `most_common == {"value": "x", "count": 2}`, `unique == 8` |
| `test_html_in_data_is_passed_through` | upload `"<b>col</b>\n<script>x</script>\n"` → after investigating, the profile's column is `"<b>col</b>"` and `most_common["value"] == "<script>x</script>"` (Review Focus 2) |
| `test_wide_file_returns_every_profile` | upload a 1,000-column, 3-row CSV → `len(profiles) == 1000` (Review Focus 5) |
| `test_lists_are_capped` | upload `"a\n" + "1\n" * 150` → `duplicates["total"] == 149`, `len(duplicates["items"]) == 100` |
| `test_save_and_replace` | `POST .../save` twice → `{"path": os.path.join("reports", "t_report.txt"), "replaced": False}`, then `replaced` is True, and the file exists |
| `test_report_download_matches_terminal` | `GET .../report.txt` → content type `text/plain; charset=utf-8`, attachment name `t_report.txt`, body equal to `Report(api.findings["c1"]).to_text()` |
| `test_save_runs_investigation_first` | open, then save without investigating → 200, and the file exists |
| `test_save_error` | point `api.reports_dir` at an existing *file* → 500, and `error` starts with `"Couldn't save the report: "` |

- [ ] **Step 2: Run them to check they fail.**
- [ ] **Step 3: Implement.**
  - First extract `sub_score_notes` in `report.py` and run `test_report` to confirm it's still green.
  - Then add `findings_json`, which uses `investigated_at.strftime("%Y%m%d-%H%M")` and `.isoformat()`.
  - Paths are shown relative to `base_dir`.
- [ ] **Step 4: Run the full suite.** Expected: every test passes.
- [ ] **Step 5: Commit**: `feat: findings, saving and report download in the web API`

---

### Task 4: Investigate ALL and Save all

**Files:**
- Modify: `web_api.py` and `report.py`.
- Test: `dev_tests/test_web_api.py`.

**Interfaces:**
- Produces:
  - in `report.py`: `rank_findings(findings_list: list[Findings]) -> list[Findings]`, the ranking `Report.leaderboard_text` already uses, so it's shared.
  - in `web_api.py`: `investigate_all() -> dict` and `save_all() -> dict`. The last results are kept as `self.board: Optional[tuple[list[Findings], list[tuple[str, str]]]]`.
- Consumes: `main.TOO_BIG`, `main.list_csv_files`.

- [ ] **Step 1: Write the failing tests**

| Test | Assertions |
|---|---|
| `test_investigate_all` | with `good.csv` (`"a,b\n1,x\n2,y\n"`), `t.csv` and `e.csv`: `ranked[0]` is `{"rank": 1, "name": "good.csv", "rows": 2, "score": 100, "verdict": "Case closed - ready for analysis", "short_verdict": "Case closed", "band": "good"}`, `ranked[1]["name"] == "t.csv"`, and `failures == [{"name": "e.csv", "reason": "File is empty"}]` |
| `test_save_all` | `POST /api/save-all` (without investigating first) → `{"saved": 2, "folder": "reports"}`, and the reports folder holds `good_report.txt`, `leaderboard.txt` and `t_report.txt` |
| `test_investigate_all_out_of_memory` | patch `Dataset` with `side_effect=MemoryError` → every file is in `failures` with the reason `"Too large for this computer's memory"` |

- [ ] **Step 2: Run them to check they fail.**
- [ ] **Step 3: Implement.** First extract `rank_findings` and confirm `test_report` is still green. Then implement the two endpoints. `leaderboard.txt` uses `Report.leaderboard_text`.
- [ ] **Step 4: Run the full suite.** Expected: every test passes.
- [ ] **Step 5: Commit**: `feat: case board endpoints in the web API`

---

### Task 5: `web_app.py`: the HTTP server

**Files:**
- Create: `python_data_detective/web_app.py`, plus placeholder `python_data_detective/web/index.html`, `style.css` and `app.js` (filled in by Tasks 6–7).
- Test: `dev_tests/test_web_app.py`.

**Interfaces:**
- Produces:
  - `STATIC_FILES: dict[str, tuple[str, str]]` (path → (file name, content type))
  - `class Handler(BaseHTTPRequestHandler)`, whose `do_GET` and `do_POST` call `server.api.handle`
  - `start_server(ports: list[int], api: DetectiveApi) -> ThreadingHTTPServer`, which binds to `127.0.0.1` on the first free port and raises `OSError` if none is free
  - `main(argv: list[str]) -> None`, which accepts `--no-browser`
- Consumes: `DetectiveApi`, `MAX_UPLOAD_BYTES`.

- [ ] **Step 1: Write the failing tests**

The server starts on port 0 in a background thread (`serve_forever`), and `tearDown` calls `shutdown()`.

| Test | Assertions |
|---|---|
| `test_serves_the_page` | `GET /` → 200, `text/html`, and the body contains `<title>Data Detective</title>`; `/style.css` → `text/css`; `/app.js` → `text/javascript` |
| `test_unknown_static_path` | `GET /../main.py` and `GET /secret.txt` → 404 |
| `test_api_round_trip` | `POST /api/cases/locker` `{"name": "t.csv"}`, then `POST /api/cases/c1/investigate` → `score == 48` |
| `test_upload_over_http` | `POST /api/cases/upload?name=x%20y.csv` with CSV bytes → `case["name"] == "x y.csv"` |
| `test_binds_to_localhost` | `server.server_address[0] == "127.0.0.1"` |
| `test_falls_back_to_next_port` | occupy a port P, then `start_server([P, P+1], api)` binds to P+1 |
| `test_concurrent_requests` | 8 threads each open `t.csv` and investigate → every reply is 200 and `len(api.cases) == 8` (Review Focus 4) |

- [ ] **Step 2: Run them to check they fail.**
- [ ] **Step 3: Implement `web_app.py`.**
  - **Static files:** read from `os.path.join(BASE_DIR, "web", name)`.
  - **Reading the request body:** read `Content-Length` bytes. If that exceeds `MAX_UPLOAD_BYTES`, reply 413 without reading the body, and set `Connection: close`.
  - **Uploads folder:** a `tempfile.mkdtemp()` folder that `main` deletes in `finally`.
  - **Logging:** override `log_message` so normal requests don't flood the terminal.
  - **Startup:** `main` prints the running message (§11) and calls `webbrowser.open` unless `--no-browser` is given.
- [ ] **Step 4: Run the full suite.** Expected: every test passes.
- [ ] **Step 5: Commit**: `feat: add the local web server`

---

### Task 6: Front end, part 1: shell, locker, upload, Evidence tab, themes

**Files:** Modify `web/index.html`, `web/style.css` and `web/app.js`.

**Interfaces:**
- Consumes: the API in §5.
- Produces these JavaScript functions, used by Task 7:
  - `api(method, path, body)` returns parsed JSON or throws `Error(message)`, with the network-failure message from §8
  - `el(tag, attrs, ...children)` builds elements using `textContent` only
  - `showBanner(kind, text)` and `announce(text)`
  - `state = {caseId, view, tab}`
  - `openCase(summary)`, `renderEvidence(data)`, `setTab(name)`

- [ ] **Step 1:** Load the `dataviz` skill, which is required before writing the score bars and verdict colours.
- [ ] **Step 2: `index.html`.**
  - The top bar, with an inline magnifier SVG, "Data Detective", the Case / Case board tabs and the theme button.
  - The sidebar: an "Evidence locker" list and a drop-zone `<label>` around `<input type="file" hidden>`.
  - The main area, plus `<div aria-live="polite" class="sr-only">`.
  - `<title>Data Detective</title>`.
  - No external URLs.
- [ ] **Step 3: `style.css`.**
  - The tokens and band colours from §7: `:root` holds the light values, and `[data-theme="dark"]` plus `@media (prefers-color-scheme: dark)` (for when no `data-theme` is set) hold the dark ones.
  - The fonts from §7.
  - A 240px sidebar that stacks below 800px.
  - No shadows and no gradients.
- [ ] **Step 4: `app.js`.**
  - Load the locker on start.
  - A locker click calls `POST /api/cases/locker`. A drop or browse uploads via `fetch` with the body as the `File`.
  - Then show the Evidence tab (§6): metric cards, amber warning banners, column chips, a preview table with `title` for full cell values, and the **Run investigation** button (wired up in Task 7).
  - Errors show a red banner in the main area.
  - The theme toggle cycles light ⇄ dark and is kept in `localStorage`, inside `try/catch`.
- [ ] **Step 5: Check in the in-app browser.** Start the server with `python python_data_detective/web_app.py --no-browser` (through `.claude/launch.json` and `preview_start`).
  - The empty state shows.
  - Opening `iris.csv` shows 150 rows, 5 columns and the preview.
  - Opening `not_really_a_csv.csv` shows the red banner *"This is a PNG image, not a CSV file"*.
  - The dark theme is readable.
  - At 375px wide, the sidebar stacks.
  - The browser console shows no errors.
- [ ] **Step 6: Run the full suite, then commit**: `feat: web UI shell, locker, uploads and evidence view`

---

### Task 7: Front end, part 2: Findings, saving, Case board

**Files:** Modify `web/app.js`, `web/style.css` and `web/index.html`.

**Interfaces:**
- Consumes: Task 6's functions and the §5 endpoints.
- Produces `renderFindings(data)`, `sortTable(table, columnIndex)` and `renderBoard(data)`.

- [ ] **Step 1: Findings (§6).**
  - The score card with the band badge, "Case file #…", and the time.
  - Three sub-score cards with bars coloured by score band.
  - Tables:
    - **Suspects:** examples shown as `value (line N)`.
    - **Duplicates:** with "…and N more".
    - **Malformed rows.**
    - **Profiles:** sortable by clicking a header; numbers sort numerically.
  - "None found" for empty tables.
  - **Run investigation** disables itself and shows a spinner and the status "Investigating <name>…" until it finishes.
- [ ] **Step 2: Actions.**
  - **Save to reports/** shows the confirmation from §6.
  - **Download .txt** is an `<a href="/api/cases/<id>/report.txt" download>`.
- [ ] **Step 3: Case board.**
  - **Investigate all datasets**.
  - The ranked table, with a score bar and the number, and a badge.
  - Clicking a row opens that case.
  - The "Couldn't open" list.
  - **Save all reports** shows its confirmation.
- [ ] **Step 4: Check every feature in the in-app browser:**
  - `messy_sales.csv`: score 83, the "Significant cleaning needed" badge, and the `price` suspect with `twelve (line 12)`;
  - profile sorting;
  - saving twice (the "replaced" note);
  - the download link returns the report text;
  - the case board ranks penguins first, with `empty.csv` and `not_really_a_csv.csv` under "Couldn't open";
  - a board row click opens the case;
  - the dark theme;
  - keyboard only: Tab reaches the locker, the drop zone and the buttons, and Enter activates them;
  - an uploaded file containing `<script>` shows as text (upload it with `fetch` from the browser's JavaScript console helper) (Review Focus 2);
  - `wide_1000_columns.csv` from `stress_tests/files` stays usable (Review Focus 5);
  - restart the server, then click Run investigation → the "no longer open" banner (Review Focus 3);
  - stop the server, then click anything → the "Can't reach the Data Detective server" banner;
  - no console errors.
- [ ] **Step 5: Run the full suite, then commit**: `feat: findings and case board in the web UI`

---

### Task 8: Docs, a check that it runs on its own, final review

**Files:**
- Modify: `python_data_detective/README.txt`, `README.md`, the program spec §4.1, and `python_data_detective/main.py`'s docstring module list.
- Create: `.claude/launch.json`.

- [ ] **Step 1: README updates.**
  - **`README.txt`:** a "WEB UI (OPTIONAL)" section covering `python web_app.py`, `--no-browser`, localhost only, the stop key, and that it needs a normal Python install rather than Ed. List the new files under "What's in the folder", and add `http.server` and `webbrowser` to the concepts list.
  - **`README.md`:** a "Web UI" section with a screenshot taken in Task 7, saved as `docs/web-ui.png` and referenced relatively.
- [ ] **Step 2: Fresh-copy check.** Copy `python_data_detective/` to a temp folder and run `web_app.py --no-browser` from another directory. `GET /` and an investigate request should succeed, and Ctrl+C should delete the uploads folder.
- [ ] **Step 3: Run the full suite one last time,** then commit `docs: document the web UI`.
- [ ] **Step 4: Final review** (executing-plans: one fresh reviewer on the whole branch), then fix and ledger the findings.
