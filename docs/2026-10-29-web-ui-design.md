# Python Data Detective: Web UI Design Spec

**Status:** Designed section by section with the user on 29 Oct 2026; this written spec is awaiting review.
**Builds on:** `docs/2026-10-26-python-data-detective-design.md`, the program's own spec. Nothing in it changes.

## 1. Summary

A minimal, professional web interface for Python Data Detective. It runs on the user's own computer (`localhost`) and is meant for real use by data professionals and for the tutorial demonstration. It offers every feature of the terminal program in a point-and-click page.

**Audience:** data professionals. The copy is professional and clear, with no slang. The detective theme stays only as light branding: "case", "evidence locker", "suspects", "verdict". *(The user changed this from an initial Gen Z framing.)*

**Look:** the "Clean analyst" style. That means neutral surfaces, a single teal accent, metric cards, readable tables, and light and dark mode.

### Success criteria
- `python web_app.py` opens a working page in the browser with nothing to install, and it works without internet.
- Every terminal feature is usable in the page (table in §4).
- Every refusal or error appears as a plain message, never as a traceback in the browser.
- Saved and downloaded reports are byte-for-byte the terminal program's `Report.to_text()`.
- No scoring or rule logic is duplicated. The UI only presents what `Dataset`, `Investigator` and `Report` produce.

## 2. Constraints

- **Standard library only.** It uses `http.server`, `json`, `webbrowser`, `tempfile`, `threading`, `urllib.parse` and the program's own modules. Python 3.9 or newer.
- **Front end:** one HTML page, one CSS file and one JavaScript file, with no frameworks. It loads nothing from the internet: no CDNs and no web fonts, only system fonts.
- **Localhost only.** The server binds to `127.0.0.1`.
- **The terminal program (`main.py`) is unchanged** and remains the main program. Ed can't run web apps, so the README says so, as the course instructions require for web-based programs.
- **Copy rules:** our own text is professional, uses sentence case, and has no slang or exclamation marks.

## 3. Decisions log (29 Oct 2026)

| Topic | Decision |
|---|---|
| Platform | Built-in `http.server` and one web page (rejected: tkinter, Flask/Streamlit) |
| Audience and tone | Data professionals; professional copy |
| Look | Clean analyst (rejected: outlined case file, sticker, midnight noir, pastel) |
| Opening any file | Upload by drag and drop or browse (a browser can't give the server a file path) |
| Upload limit | 200 MB |

## 4. Architecture

```
python_data_detective/
├── web_app.py     RUN THIS for the UI: HTTP server, static files, opens the browser
├── web_api.py     DetectiveApi: every API action, independent of HTTP (unit-testable)
└── web/
    ├── index.html   the single page
    ├── style.css    clean analyst theme, light and dark
    └── app.js       calls the API and renders the views
```

- **Dependencies:**
  - `web_app.py` imports `web_api.py`.
  - `web_api.py` imports `dataset`, `investigator`, `report`, `errors` and `main.list_csv_files`.
  - Nothing in the existing modules imports the web files.
- **State:** `DetectiveApi` keeps open cases in memory, as `case id → Dataset` plus cached `Findings`. Ids are `c1`, `c2`, and so on. At most **20** cases stay open; opening another drops the oldest. It also keeps the latest Investigate ALL result, for Save all.
- **Concurrency:** `ThreadingHTTPServer`. A single `threading.Lock` around each API call keeps the state consistent; it's a single-user tool.

| Terminal feature | Web UI | API |
|---|---|---|
| 1. Open a case from the locker | Evidence locker list | `GET /api/locker`, `POST /api/cases/locker` |
| 1. Open a case by path (`P`) | Drag and drop or browse any file | `POST /api/cases/upload?name=<file name>` |
| 2. Inspect the evidence | Evidence tab | `GET /api/cases/<id>/evidence` |
| 3. Run the investigation | Findings tab | `POST /api/cases/<id>/investigate` |
| 4. Save the case report | "Save to reports/" and "Download .txt" | `POST /api/cases/<id>/save`, `GET /api/cases/<id>/report.txt` |
| 5. Investigate ALL and save all | Case board view | `POST /api/investigate-all`, `POST /api/save-all` |
| 0. Quit | Ctrl+C in the terminal running `web_app.py` | (none) |

## 5. API

All JSON uses UTF-8. Errors always come back as `{"error": "<message>"}` with the status codes in §8.

**`CaseSummary`** = `{"id", "name", "rows", "columns", "delimiter", "encoding", "warnings": [str]}`. `delimiter` is the display form from `report.DELIMITER_NAMES` (`"','"`, `"tab"`, …).

| Endpoint | Request | Response 200 |
|---|---|---|
| `GET /api/locker` | — | `{"datasets": [{"name", "bytes"}]}`, alphabetical, `.csv` files only |
| `POST /api/cases/locker` | `{"name": "iris.csv"}` | `{"case": CaseSummary}`. The name must be in the locker list |
| `POST /api/cases/upload?name=<url-encoded>` | raw file bytes | `{"case": CaseSummary}`. The bytes are saved under the upload folder as the base name, inside a fresh subfolder, so `Dataset.name` matches the original file |
| `GET /api/cases/<id>/evidence` | — | `{"case", "blank_lines_skipped", "trailing_delimiters", "header": [str], "preview": [[str]]}` (first 5 rows) |
| `POST /api/cases/<id>/investigate` | — | **Findings JSON**, below |
| `POST /api/cases/<id>/save` | — | `{"path": "reports/<stem>_report.txt", "replaced": bool}`. Investigates first if needed |
| `GET /api/cases/<id>/report.txt` | — | `text/plain; charset=utf-8`, sent as an attachment named `<stem>_report.txt` |
| `POST /api/investigate-all` | — | `{"ranked": [{"rank", "name", "rows", "score", "verdict", "short_verdict", "band"}], "failures": [{"name", "reason"}]}`, ranked like `Report.leaderboard_text` |
| `POST /api/save-all` | — | `{"saved": int, "folder": "reports"}`. Saves every ranked report plus `leaderboard.txt` (the same text as the terminal), running Investigate ALL first if needed |

**Findings JSON:**
```
{"case": CaseSummary,
 "case_number": "20261029-1402", "investigated_at": "<ISO 8601>",
 "score": 83, "verdict": "Significant cleaning needed",
 "short_verdict": "Needs cleaning", "band": "poor",
 "sub_scores": [{"name": "Completeness", "score": 83.3, "note": "3.3% of cells missing"}, ... Uniqueness, Validity],
 "suspects": [{"column", "kind", "missing", "invalid", "not_numbers",
               "examples": [{"value", "line"}]}],
 "duplicates": {"total": 10, "items": [{"line": 79, "original": 51}]},
 "malformed": {"total": 11, "expected_fields": 5, "items": [{"line", "fields"}]},
 "profiles": [{"column", "kind", "missing_percent",
               "stats": {"min", "max", "mean", "median"} | null,
               "unique": int, "most_common": {"value", "count"} | null}]}
```
- **`band`** comes from the short verdict: Case closed → `good`, Minor clean-up → `fair`, Needs cleaning → `poor`, Unreliable → `bad`.
- **List limits:** `items` lists hold at most **100** entries, and `total` gives the full count.
- **Sub-score notes** use the same wording as the text report: "% of cells missing", "% of rows duplicated", and "% of numbers invalid" / "% of rows malformed" / "no numeric columns".
- **`suspects`** lists columns where missing, invalid or not_numbers is above 0.

## 6. Screens

One page, no reloads.
- **Top bar:** a magnifier icon (inline SVG) and "Data Detective"; tabs **Case** and **Case board**; a theme button. The theme follows the system until clicked, and the choice is kept in `localStorage`.
- **Sidebar (Case view):**
  - "Evidence locker": each dataset with its size; clicking one opens it, and the selected item is highlighted.
  - A **drop zone** below, "Drop a file or browse": a `<label>` around a hidden file input, so it works from the keyboard too. It accepts any file type.
- **Empty state:** "Open a case" heading; "Choose a dataset from the evidence locker, or drop any file to investigate it."
- **Case header:** the file name, then a meta line: rows · columns · delimiter · encoding. Any warnings appear as amber banners.

**Evidence tab** (shown first when a case opens):
- Metric cards: Rows, Columns, Delimiter, Encoding, Blank lines skipped.
- A note if trailing delimiters were ignored.
- Column chips.
- A preview table (header plus 5 rows), which scrolls sideways; long cells are cut with an ellipsis and show the full value on hover.
- The primary button **Run investigation**, which switches to Findings when done.

**Findings tab:**
- A score card: the score `/100`, the verdict badge coloured by band, and "Case file #… · <time>".
- Three sub-score cards, each with a thin bar coloured by its own score: ≥95 good, ≥85 fair, ≥70 poor, otherwise bad.
- Tables:
  - **Suspects:** column, type, missing, invalid / not numbers, examples as `value (line N)`.
  - **Duplicates:** "line N duplicates line M", then "…and N more".
  - **Malformed rows:** line, fields, expected.
  - **Column profiles:** column, type, missing %, summary. Headers can be clicked to sort.
- Empty tables say "None found".
- Actions: **Download .txt** (secondary) and **Save to reports/** (primary). A save shows a confirmation, "Saved to reports/x_report.txt", adding "(replaced the previous report)" if a file was overwritten.

**Case board view:**
- The **Investigate all datasets** button.
- A ranked table: rank, dataset, rows, a score bar with its number, and the verdict badge. Clicking a row opens that case.
- A "Couldn't open" list: name — reason.
- **Save all reports**, which confirms "Saved N case reports and leaderboard.txt to reports/".

**Loading:**
- Buttons show a spinner and are kept from double submission.
- Long tasks show a status line, e.g. "Investigating messy_sales.csv…".
- An `aria-live="polite"` region announces status messages and errors.

## 7. Visual design

**Colour tokens:**

| Token | Light | Dark |
|---|---|---|
| `--bg` | `#F7F7F5` | `#1A1A19` |
| `--surface` | `#FFFFFF` | `#232322` |
| `--surface-2` | `#F1EFE8` | `#2C2C2A` |
| `--border` | `#E2E0D8` | `#3A3A37` |
| `--text` | `#1F1F1D` | `#ECEBE6` |
| `--text-2` | `#5F5E5A` | `#B4B2A9` |
| `--muted` | `#888780` | `#888780` |
| `--accent` | `#0F6E56` | `#5DCAA5` |
| `--accent-soft` | `#E1F5EE` | `#0B3B2E` |
| `--accent-text` (on accent) | `#FFFFFF` | `#0B2A21` |

**Band colours** (text / background):

| Band | Light | Dark |
|---|---|---|
| good | `#27500A` / `#EAF3DE` | `#C0DD97` / `#1F3A0B` |
| fair | `#633806` / `#FAEEDA` | `#FAC775` / `#3D2A08` |
| poor | `#712B13` / `#FAECE7` | `#F5C4B3` / `#45200F` |
| bad | `#791F1F` / `#FCEBEB` | `#F7C1C1` / `#4A1515` |

Banners use the `fair` colours for warnings and the `bad` colours for errors. Bars use the bands' text colours as fills.

**Type and layout:**
- **Fonts:** `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. Values, column names and table data use `ui-monospace, "Cascadia Mono", Consolas, Menlo, monospace`. Two weights only (400 and 600); body 15px; headings 20/16px.
- **Shapes:** cards have an 8px radius and a 1px border, with no shadows and no gradients.
- **Layout:** the sidebar is 240px wide. Below 800px wide, the sidebar stacks above the main area.

## 8. Errors

| Situation | Status | Message |
|---|---|---|
| `DatasetError` (format named, empty, header only, unreadable) | 422 | the program's own message, e.g. "this is a PNG image, not a CSV file", with its first letter capitalised for display |
| `MemoryError` | 413 | "This file is too large for this computer's memory." |
| Upload over 200 MB (from `Content-Length`) | 413 | "Files over 200 MB can't be uploaded." |
| Unknown locker name, or one containing `/`, `\` or `..` | 404 | "There's no dataset called '<name>' in the evidence locker." |
| Unknown case id | 404 | "This case is no longer open. Open it again from the evidence locker." |
| Unknown API path or wrong method | 404 / 405 | "Not found." / "Method not allowed." |
| Saving fails (`OSError`) | 500 | "Couldn't save the report: <reason>" |
| Any other exception | 500 | "Something went wrong. Details are in the terminal." The traceback is printed by the server only |
| The server can't be reached (front end) | — | "Can't reach the Data Detective server. Is it still running?" |

## 9. Security
- The server binds to `127.0.0.1` only.
- Static serving covers exactly `/`, `/index.html`, `/style.css` and `/app.js`. Nothing else is served from disk; there are no directory listings.
- Locker names are checked against `list_csv_files(DATASETS_DIR)`.
- An uploaded file's name is reduced to its base name, and blank or unsafe names become `upload.csv`. It's written into a fresh `tempfile.mkdtemp()` subfolder of the upload directory, which is deleted when the server stops.
- The front end inserts all data with `textContent`, never `innerHTML`, so data can't inject HTML or script.

## 10. Testing
- **`dev_tests/test_web_api.py`** uses `DetectiveApi` directly with temporary folders. It covers:
  - the locker list, `../` names and unknown names;
  - opening from the locker;
  - uploads: a CSV, a PNG (422, the PNG message), and the size limit;
  - evidence for the shared sample fixture (10 rows × 2, preview, header);
  - findings for the fixture: score 48, band `bad`, the duplicate `(11, 2)`, the suspect `bad` at line 9, and two profiles;
  - saving, and the replaced flag;
  - `report.txt` being identical to `Report(findings).to_text()` for the case's cached findings;
  - Investigate ALL ranking and failures;
  - Save all;
  - an unknown case;
  - `MemoryError` → 413;
  - the 21st case dropping the first.
- **`dev_tests/test_web_app.py`** starts the real server on a free port in a background thread. It checks that `GET /` serves the page, the static files load, an unknown path gives 404, a locker open → investigate round trip works over HTTP, the upload endpoint works, and the server binds to 127.0.0.1.
- **The existing documentation test** automatically covers `web_api.py` and `web_app.py`.
- **The front end** is tested by driving the real page in the in-app browser:
  - the empty state;
  - opening a case;
  - both tabs;
  - running an investigation;
  - saving and downloading;
  - the case board and its row click;
  - the theme toggle;
  - the error banner (opening `not_really_a_csv.csv` from the locker);
  - a narrow window;
  - keyboard use.

## 11. Launch and docs
- `python web_app.py [--no-browser]` tries ports 8000–8010 and prints "Data Detective is running at http://127.0.0.1:<port>. Press Ctrl+C to stop." Unless `--no-browser` is given, it opens the browser. Ctrl+C stops the server and deletes the uploads.
- `README.txt` and `README.md` get a "Web UI" section: how to run it, that it uses networking on localhost only, and that it needs a normal Python install rather than Ed.
- The program spec's §4.1 folder list is updated.

## 12. Out of scope
User accounts, opening more than one file at once, editing or cleaning data, charts beyond the score bars, and serving to other machines.
