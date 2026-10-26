# Python Data Detective: Design Spec

**Course:** COMP9001 Final Project (University of Sydney, 2026 S2)
**Due:** 1 November 2026, 11:59pm
**Status:** Design agreed section by section on 26 Oct 2026; this written spec is awaiting review.

---

## 1. Summary

Python Data Detective is a menu-driven terminal program. It loads a CSV file, checks its basic data quality and writes a short investigation report to a text file. It's for students and beginner data analysts who want to know quickly whether a dataset is fit for further analysis.

**Core features (from the approved overview):**
1. **Load & inspect:** row and column counts, column names and a preview.
2. **Quality investigation:** missing values, duplicate rows, invalid numbers and an overall quality score.
3. **Investigation report:** findings and score saved to a `.txt` file.

**Extras (agreed 26 Oct):**
4. **Per-column profile:** each column's type and missing %, plus number stats for numeric columns or the unique count and most common value for text columns.
5. **Investigate all:** runs every dataset in `datasets/` and prints a leaderboard ranked by quality score.

**Tutor feedback this design responds to:** "see your app working for a number of datasets of varying complexity". AI-generated data is allowed if acknowledged. The report is saved to a text file.

### Success criteria
- The tutor runs `python main.py` on Ed or their laptop with nothing extra installed.
- All 9 sample datasets give either a full report or a friendly "could not open" message. No input or file ever ends in a traceback.
- For every AI-generated dataset, the counts the app reports (missing, invalid, duplicates, malformed rows) match the generator's answer key exactly.
- Scores put the datasets in sensible verdict bands: clean ones near 100, broken ones clearly lower.
- The whole feature set can be demonstrated in a 3-minute presentation.

---

## 2. Constraints

- **Standard library only:** no pandas or matplotlib. Python **3.9 or newer**, because type hints use `list[str]`. Developed on Python 3.10.7.
- **Terminal only:** a GUI is out of scope for now and may be considered later if time allows.
- **Output:** our own text is **ASCII-only** (no emoji, no `×`) and lines are **at most 64 characters**, so it displays correctly on Ed, Windows cmd and macOS and stays readable on a projector. Values quoted from the data (e.g. `café`) are printed as they are.
- **Paths:** worked out from the script's own folder, so the program runs from any working directory.
- **Advanced topics:** at least 2 from the Ed list. The design uses classes and objects, file I/O, exception handling (custom exceptions, `raise`, `try/except/finally`) and advanced flow control (`break`, `continue`, early `return`, returning several values).
- **Out-of-syllabus concepts:** allowed. Each one is listed with its reason in section 9.
- **AI use:** acknowledged in the README, covering both the AI-generated datasets and help with the code. Check the COMP9001 / University AI policy for the required wording.

---

## 3. Decisions log (26 Oct 2026)

| Topic | Decision |
|---|---|
| Datasets | 2 real public datasets plus 7 AI-generated ones, ordered from clean to edge cases |
| Extras | Per-column profile; investigate-all leaderboard |
| Left out | Exporting a cleaned CSV; automated test file in the submission |
| Theme | Light touch: themed headings (CASE FILE, EVIDENCE, SUSPECTS, VERDICT) with plain findings underneath |
| Score | Three sub-scores combined as Completeness 40%, Uniqueness 30%, Validity 30% |
| Structure | Option A: one class per job |

---

## 4. Architecture

### 4.1 Folder layout
```
ITP Data Project/
├── docs/                         this spec (not submitted)
└── python_data_detective/        the submission folder
    ├── main.py                   RUN THIS: menu loop, input and program flow
    ├── dataset.py                Dataset
    ├── investigator.py           Investigator, Findings, ColumnProfile
    ├── report.py                 Report (all text formatting)
    ├── errors.py                 DatasetError and its subclasses
    ├── datasets/                 9 sample CSVs
    ├── reports/                  created on first save
    ├── tools/
    │   └── make_datasets.py      generates the AI datasets and prints the answer key
    └── README.txt                how to run, AI-use acknowledgement, data sources
```
`tools/make_datasets.py` isn't needed to run the app. It's submitted anyway because the instructions ask for every Python file used in the project.

### 4.2 Dependencies (no cycles)
```
main.py ──► dataset.py ──► errors.py
   │
   ├──────► investigator.py ──► (works on a Dataset)
   │
   └──────► report.py ──► (formats Findings and Dataset)
```

### 4.3 Data flow
```
file path ─► Dataset ─► Investigator.investigate() ─► Findings ─► Report.to_text() ─► screen / .txt
```

### 4.4 `errors.py`
```python
class DatasetError(Exception)            # base: an expected problem with a data file
class UnreadableFileError(DatasetError)  # missing, folder, no permission, binary, unparseable
class EmptyDatasetError(DatasetError)    # no rows at all, or a header with no data rows
```
`main.py` catches `DatasetError`. Anything else is a genuine bug and isn't caught by it.

### 4.5 `dataset.py`: `Dataset`
Builds itself from a path and raises a `DatasetError` subclass if the file can't be used.

**Attributes**
| Name | Type | Meaning |
|---|---|---|
| `path` | `str` | path as given |
| `name` | `str` | file name, e.g. `messy_sales.csv` |
| `encoding` | `str` | `"utf-8"` or `"latin-1"` |
| `delimiter` | `str` | one of `, ; \t \|` |
| `header` | `list[str]` | column names, stripped; blank names become `column_N` (counting from 1) |
| `rows` | `list[list[str]]` | data rows, each exactly `len(header)` long after padding or trimming |
| `line_numbers` | `list[int]` | file line on which each data row **starts** |
| `malformed_rows` | `list[tuple[int, int]]` | `(line, field_count)` for each row with the wrong number of fields |
| `blank_lines_skipped` | `int` | number of fully blank lines ignored |

**Methods:** `num_rows()`, `num_columns()`, `column_values(index) -> list[str]`, `preview(n=5) -> list[list[str]]`, and `__str__`, which gives `"messy_sales.csv (200 rows x 6 columns)"`.

**Loading steps**
1. Open with `encoding="utf-8-sig"` and `newline=""`, then read the whole text. If that raises `UnicodeDecodeError`, re-read with `latin-1`. `utf-8-sig` removes Excel's BOM.
2. If the text contains a null character (`\x00`), raise `UnreadableFileError("doesn't look like a plain text CSV")`.
3. Detect the delimiter with `csv.Sniffer().sniff(sample, delimiters=",;\t|")` on the first 4096 characters. If that raises `csv.Error`, use `","`.
4. Parse with `csv.reader(io.StringIO(text, newline=""), delimiter=...)`. A `csv.Error` while parsing becomes `UnreadableFileError("couldn't be read as CSV: ...")`.
5. Skip blank rows (`continue`) and count them. The first non-blank row is the header.
6. No header: raise `EmptyDatasetError("file is empty")`. A header but no data rows: raise `EmptyDatasetError("file has a header but no data rows")`.
7. A row with too many fields is trimmed (extra fields are dropped and not analysed). A row with too few is padded with `""`. Either way, `(line, field_count)` is recorded.
8. `FileNotFoundError`, `IsADirectoryError` and `PermissionError` become `UnreadableFileError` with a plain message such as `"no file at 'x.csv'"`.

### 4.6 `investigator.py`

**`ColumnProfile`**: the results for one column.
| Attribute | Meaning |
|---|---|
| `name` | column name |
| `kind` | `"numeric"`, `"text"` or `"empty"` (every value missing) |
| `missing` | count of missing cells |
| `invalid` | count of invalid numbers (numeric columns only, otherwise 0) |
| `invalid_examples` | up to 3 `(value, line)` pairs |
| `stats` | for numeric columns: `(min, max, mean, median)` over valid numbers only, or `None` if there are none |
| `unique_count`, `most_common` | for text columns: number of distinct filled values, and `(value, count)` |

**`Findings`**: everything about one investigated dataset. It holds the `Dataset`; `profiles`; `duplicates` (a list of `(line, original_line)`); `total_cells`, `missing_cells`, `numeric_cells` (filled cells in numeric columns), `invalid_cells`; `completeness`, `uniqueness`, `validity` (each 0–100, one decimal place); `overall` (an int from 0–100); `verdict` and `short_verdict` (str); and `investigated_at` (datetime).

**`Investigator`**
- **Class variables** (each rule is one line to change):
  - `MISSING_MARKERS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}`
  - `NUMERIC_THRESHOLD = 0.8`
  - `WEIGHTS = (0.4, 0.3, 0.3)`
  - `VERDICT_BANDS`: a list of `(minimum score, short verdict, full verdict)`, highest band first. See the table in 5.2.
- **Static methods:**
  - `is_missing(value) -> bool`
  - `is_number(value) -> bool`
  - `verdict_for(score) -> tuple[str, str]`, which returns `(short, full)`
- **`__init__(self, dataset)`**
- **`investigate() -> Findings`**: profiles each column, finds duplicates and works out the scores.

### 4.7 `report.py`: `Report`
- `WIDTH = 64` (module constant)
- `__init__(self, findings)`
- `to_text() -> str`: the full themed report. The terminal and the file use the same text.
- `save(folder) -> tuple[str, bool]`: writes `<folder>/<file name without its extension>_report.txt` as UTF-8 and returns `(path, replaced_existing)`. It creates the folder if needed. `OSError` is left for `main.py` to handle.
- `@staticmethod evidence_text(dataset) -> str`: the screen for menu option 2.
- `@staticmethod leaderboard_text(findings_list, failures) -> str`: `failures` is a list of `(file name, reason)`.

### 4.8 `main.py`
- `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`, with `DATASETS_DIR` and `REPORTS_DIR` built from it.
- `main()`: the menu loop is wrapped as `try: ... except (KeyboardInterrupt, EOFError): ... finally: print goodbye`.
- **State:** `current_dataset` (Dataset or None) and `current_findings` (Findings or None). Opening a new case clears `current_findings`.
- **Helpers:** `list_csv_files(folder)`, `choose_dataset()`, `ask_yes_no(prompt)`, `investigate_all()` and one handler per menu option.
- `main.py` only handles input and program flow. All formatting lives in `report.py`.
- The guard `if __name__ == "__main__": main()` at the bottom starts the program.

---

## 5. Detection rules and scoring

### 5.1 Rules
- **Missing:** after removing surrounding spaces and ignoring case, the value is in `MISSING_MARKERS`.
- **Number-like:** `float(value.strip())` succeeds and the result is finite. So `3.5`, `-2`, `+5` and `1e3` count as numbers, while `inf`, `1,204` and `$15` don't.
- **Column type:**
  - `empty` if it has no filled cells.
  - `numeric` if at least 80% of its filled cells are number-like.
  - `text` otherwise.
- **Invalid number:** a filled cell in a numeric column that isn't number-like. Text columns never have invalid values.
- **Duplicate row:** every cell equal to an earlier row's cell after removing surrounding spaces. The comparison is case-sensitive (`North` and `north` differ). The first occurrence is the original, and each later copy counts as one duplicate. Detection uses a `dict` that maps each row (as a tuple) to the line where it first appeared.
- **All rows are analysed**, duplicates included, for the missing and invalid counts.
- **Malformed rows** appear as a warning and don't lower the score directly. Blanks added by padding count as missing.

### 5.2 Scores
```
completeness = 100 x (1 - missing_cells / total_cells)        total_cells = rows x columns
uniqueness   = 100 x (1 - duplicate_rows / rows)
validity     = 100 x (1 - invalid_cells / numeric_cells)      = 100 if numeric_cells == 0
overall      = 0.4 x completeness + 0.3 x uniqueness + 0.3 x validity
               rounded to a whole number (halves round up)
```
The verdict comes from `VERDICT_BANDS`, using `overall`. The short form is used on the leaderboard:

| Overall | Full verdict (report) | Short verdict (leaderboard) |
|---|---|---|
| 95–100 | Case closed - ready for analysis | Case closed |
| 85–94 | Minor clean-up needed | Minor clean-up |
| 70–84 | Significant cleaning needed | Needs cleaning |
| 0–69 | Unreliable evidence - investigate before use | Unreliable |

**Calibration step:** once all datasets exist, check that the messy ones land in sensible bands. If they don't, propose new cut-offs to the user before changing them.

---

## 6. User interface

### 6.1 Main menu
```
================================================================
              PYTHON DATA DETECTIVE  -  Case Desk
================================================================
  Current case: messy_sales.csv (200 rows x 6 columns)

  1. Open a case             choose a dataset
  2. Inspect the evidence    size, columns, preview
  3. Run the investigation   quality checks + score
  4. Save the case report    writes a .txt file
  5. Investigate ALL         leaderboard of every dataset
  0. Close the office        quit
----------------------------------------------------------------
Choose an option:
```
- With no case open, the status line reads `Current case: none`.
- Any input other than `0`–`5` gives `Please enter a number from 0 to 5` and the menu again.
- Options 2–4 with no case open give `No case open - choose option 1 first` (an early return).

### 6.2 Option 1: Open a case
- Lists the `.csv` files in `datasets/` in alphabetical order (the extension check ignores case), numbered from 1.
- `P` asks for a path. Surrounding quotes are removed, because Windows "Copy as path" adds them. Relative paths are taken from the current working directory. Reports are always saved in the program's own `reports/` folder, wherever the dataset came from.
- `B` goes back. `P` and `B` can be typed in either case.
- Invalid input re-prompts.
- If the folder is missing or empty, it shows `The evidence locker is empty`, and `P` and `B` still work.
- **On success:** `Opening case... messy_sales.csv (200 rows x 6 columns, delimiter ',')`.
- **On a `DatasetError`:** `Could not open case: <reason>`, then back to the menu.

### 6.3 Option 2: Inspect the evidence
- Shows the size, delimiter and encoding, and the number of blank lines skipped.
- Lists all column names, wrapped to the width limit.
- Previews the first 5 rows as a table:
  - Cells are cut to 12 characters (10 characters + `..`).
  - Columns are added while the line fits in 64 characters, then `(+N more columns)`.

### 6.4 Option 3 (run) and option 4 (save)
- Option 3 runs the investigation and prints `Report.to_text()`.
- Option 4 saves the report, running the investigation first if it hasn't been run.
  - It prints `Report saved to reports/messy_sales_report.txt`, adding `(replaced the previous report)` if a file was overwritten.
  - An `OSError` gives `Could not save report: <reason>` and the program carries on.

### 6.5 Report layout
```
================================================================
CASE FILE #20261026-1432                PYTHON DATA DETECTIVE
Dataset : messy_sales.csv
Opened  : 26 Oct 2026, 14:32
================================================================
[EVIDENCE]
  200 rows x 6 columns  (delimiter ',', 2 blank lines skipped)

[SUSPECTS]  columns with problems
  price    numeric  41 missing  19 invalid
           e.g. 'twelve' (line 44), '$15' (line 97)
  region   text     22 missing
  rating   numeric  33 missing   9 invalid
           e.g. '5 stars' (line 188)

[DUPLICATES]  10 duplicate rows
  line 17 duplicates line 3
  line 88 duplicates line 52
  ...

[MALFORMED ROWS]  2 rows with the wrong number of fields
  line 131: 7 fields (expected 6) - extra field dropped
  line 155: 4 fields (expected 6) - padded with blanks

[COLUMN PROFILES]
  order_id  numeric   0.0% missing
            min 1  max 200  mean 100.5  median 100.5
  region    text     11.0% missing
            4 unique, most common 'North' (61)
  ...

[SUB-SCORES]
  Completeness  92.0%  (96 of 1,200 cells missing)
  Uniqueness    95.0%  (10 of 200 rows duplicated)
  Validity      96.1%  (28 of 726 numeric values invalid)
================================================================
VERDICT: 94/100  -  Minor clean-up needed
================================================================
```
- The mockup is shortened with `...` in places. The real report lists every entry up to the limits below.
- The case number is `#YYYYMMDD-HHMM`, taken from `investigated_at`.
- The EVIDENCE line also gives the encoding when it isn't UTF-8, e.g. `(delimiter ';', encoding latin-1)`.
- **SUSPECTS** lists only columns with at least one missing or invalid value, and shows up to 3 examples (wrapping if needed). If there are none: `No suspects - every column checks out.`
- **DUPLICATES** and **MALFORMED ROWS** show at most 10 entries, then `... and N more`. If there are none: `none found`.
- **COLUMN PROFILES** uses two lines per column:
  - Numeric: `min max mean median`, or `no valid numbers`.
  - Text: the unique count and most common value (the value cut to 15 characters).
  - Empty: `all values missing`.
- Numbers use thousands separators (`1,200`). Percentages and stats are shown to 1 decimal place, with trailing `.0` dropped for whole-number stats.

### 6.6 Option 5: Investigate ALL
```
================================================================
  CASE BOARD  -  every dataset in datasets/
================================================================
  Rank  Dataset                 Rows  Score  Verdict
  1     iris.csv                 150    100  Case closed
  2     student_grades.csv       120     97  Case closed
  3     messy_sales.csv          200     94  Minor clean-up
  4     broken_rows.csv           60     71  Needs cleaning
  --    empty.csv                  -      -  Could not open
  --    not_really_a_csv.csv       -      -  Could not open
----------------------------------------------------------------
  empty.csv: file is empty
  not_really_a_csv.csv: doesn't look like a plain text CSV
----------------------------------------------------------------
Save a report for every dataset? (y/n):
```
- Rows are sorted by score (highest first), then by name.
- Files that couldn't be opened go last, with `--` as their rank. Their reasons are listed underneath, which keeps every line within 64 characters. This is a small change from the section 2 mockup.
- Dataset names longer than 22 characters are cut with `..`.
- The y/n prompt accepts `y`, `yes`, `n` and `no` in any case, and re-prompts otherwise. `y` saves each dataset's report plus `reports/leaderboard.txt`. An `OSError` stops the saving and shows `Could not save report: <reason>`.
- The current case is left unchanged.

### 6.7 Quitting
`0`, Ctrl+C or Ctrl+D always ends with `Case closed. Goodbye, detective.`, printed from the `finally` block.

---

## 7. Error handling

| Situation | Where | Handling | User sees |
|---|---|---|---|
| Path missing, is a folder, or no permission | `Dataset` | OS error → `UnreadableFileError` | `Could not open case: no file at 'x.csv'` |
| Binary file | `Dataset` | null-byte check → `UnreadableFileError` | `...doesn't look like a plain text CSV` |
| Not UTF-8 | `Dataset` | retry as `latin-1` | `encoding: latin-1` in the evidence |
| Empty, or header only | `Dataset` | `EmptyDatasetError` | `...file is empty` / `...has a header but no data rows` |
| csv module can't parse | `Dataset` | `csv.Error` → `UnreadableFileError` | `...couldn't be read as CSV` |
| Delimiter not detectable | `Dataset` | default `,` | nothing |
| Ragged rows, blank lines, blank column names | `Dataset` | pad/trim, skip, `column_N` | listed in the report |
| No valid numbers in a numeric column | `Investigator` | `stats = None` | `no valid numbers` |
| Report can't be written | `main` | catch `OSError` | `Could not save report: ...` |
| `datasets/` missing or empty | `main` | message | `The evidence locker is empty` |
| Bad menu or y/n input | `main` | re-prompt | `Please enter ...` |
| Ctrl+C / Ctrl+D | `main` | catch `KeyboardInterrupt`, `EOFError` | goodbye message |

---

## 8. Datasets

| # | File | Source | Shows | Expected |
|---|---|---|---|---|
| 1 | `iris.csv` | Real: UCI Iris, CC BY 4.0 (header row added) | a clean dataset; reportedly has one duplicate row, which would make a nice real-world finding (to confirm) | about 100 |
| 2 | `penguins.csv` | Real: Palmer Penguins, CC0 | genuine `NA` missing values | high 90s |
| 3 | `student_grades.csv` | AI-generated | a few blanks, 1 duplicate | high 90s |
| 4 | `messy_sales.csv` | AI-generated | every missing marker, duplicates, `twelve`, `$15`, `5 stars`, blank lines | low–mid 90s |
| 5 | `tricky_addresses.csv` | AI-generated | `;` delimiter, UTF-8 BOM, quoted commas, line break inside a quoted field | high; must parse correctly |
| 6 | `old_export_latin1.csv` | AI-generated | latin-1 encoding (`café`, `José`) | parses using the fallback |
| 7 | `broken_rows.csv` | AI-generated | ragged rows, many duplicates, a blank column name | low |
| 8 | `empty.csv` | AI-generated | 0 bytes | Could not open |
| 9 | `not_really_a_csv.csv` | AI-generated | binary bytes, including null bytes | Could not open |

- `tools/make_datasets.py` uses a fixed random seed. It writes datasets 3–9 and prints an **answer key** with the exact injected counts for each file.
- The two real datasets are downloaded only after the user gives permission (file, source and size are stated first). Both are credited in the README.

---

## 9. Out-of-syllabus concepts used

| Concept | Why |
|---|---|
| `csv` module (`reader`, `Sniffer`) | Splits rows correctly when fields contain commas or line breaks; detects `, ; \t \|` delimiters |
| `io.StringIO` | Lets the csv module parse text already read into memory, so the file is read once for the null-byte check, delimiter detection and parsing |
| `with open(...)`, `encoding=`, `newline=""` | Closes files automatically; handles the Excel BOM and latin-1 files; `newline=""` is what the csv module needs |
| Custom exceptions through inheritance | Expected file problems get friendly messages while genuine bugs still surface; shows inheritance (beyond L7) |
| `dict` / `set` with tuple keys | Fast duplicate detection; tuples work as keys because they can't change (L4) |
| `collections.Counter` | Unique count and most common value for text columns |
| `statistics` (`mean`, `median`) | Correct, readable statistics for the per-column profile |
| `math.isfinite` | Rejects `inf` as a number |
| `datetime` | Report timestamp and case number |
| `sorted(..., key=lambda ...)` | Leaderboard ranking |
| `enumerate`, `zip` | Line numbers and value-to-column pairing |
| f-string format specs (`:>10`, `:.1f`, `:,`) | Aligned, readable tables |
| `__file__`, `os.path`, `os.makedirs` | Script-relative paths; `reports/` created when needed |
| `@staticmethod` decorator | Marks helpers like `is_number` that don't need `self` (L7 covered the idea, not the decorator) |
| List and dict comprehensions | Only where clearer, with a comment |

**Only if time is left:** coloured verdicts using ANSI codes, with one on/off constant.
**Not used:** pandas, matplotlib (break the no-libraries rule); argparse (the menu is enough); dataclasses (would hide the `__init__` OOP being assessed); generators (the files are small); unittest (left out of scope).

---

## 10. Testing and verification

The submission has no automated test file (an agreed decision). Verification during development:
1. **Answer-key checks:** throwaway scripts in Claude's scratchpad (not submitted) compare each module's counts with the generator's answer key.
2. **Score calibration:** see section 5.2.
3. **Manual run-through checklist:**
   - every menu option
   - bad inputs (letters, out of range, blank, `P` with a bad path)
   - Ctrl+C at each prompt
   - opening each of the 9 datasets
   - investigate-all with y and n
   - saving twice (the "replaced" message)
   - running from a different working directory
   - Python 3.10.7 locally
4. **On Ed, done by the user:** upload the folder, check `python3 --version` is 3.9 or newer, and run through the main options once before submitting.

---

## 11. Rubric mapping

| Criterion (marks) | How the design addresses it |
|---|---|
| Functionality (3) | Three core features plus two extras; never crashes; tested on 9 datasets |
| Structure & Documentation (2) | Five focused modules with no circular imports; docstrings and type hints throughout; README with run steps, sources and AI acknowledgement |
| Advanced Concepts (3) | Classes and objects (5 classes plus 3 exception classes, instance and static methods, class variables, `__str__`); file I/O (read CSV, write reports); exception handling (custom exception classes, `raise`, `try/except/finally`); `break`, `continue`, early `return`, multiple return values |
| Creativity & Originality (3) | Detective theme; leaderboard across datasets; line-number evidence |
| Padlet & Presentation (4) | Demo flow: open a case, investigate, save, investigate all. The leaderboard makes the closing shot |

---

## 12. Out of scope
Exporting a cleaned CSV, automated tests in the submission, a GUI, charts, coloured output (unless time is left), command-line arguments, very large files (everything is read into memory, which is fine for the sample sizes).

## 13. Open items and risks
- **Verdict bands may be too generous.** Covered by the calibration step.
- **Ed's Python version** is unknown until the user checks; the code needs 3.9 or newer.
- **Ed's advanced-topics list** hasn't been seen. If it includes something unexpected (e.g. recursion), tell Claude and it will be worked in.
- **The AI-acknowledgement wording** should follow the course policy; the user to confirm.
