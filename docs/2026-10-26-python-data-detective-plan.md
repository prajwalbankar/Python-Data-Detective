# Python Data Detective Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a menu-driven terminal program that loads a CSV, investigates its data quality, scores it, and saves a themed text report, plus a leaderboard across a set of sample datasets.

**Architecture:** Five modules with one job each (`errors`, `dataset`, `investigator`, `report`, `main`), running in a straight line: path → `Dataset` → `Investigator.investigate()` → `Findings` → `Report` → screen or `.txt`. `main.py` only handles input and program flow; all formatting lives in `report.py`. A seeded generator script creates the AI datasets and an answer key, which the integration tests compare against.

**Tech Stack:** Python 3.9+ standard library only (`csv`, `io`, `os`, `collections`, `statistics`, `math`, `datetime`, `random`). Dev tests use `unittest`, `unittest.mock`, `contextlib`, `subprocess`, `tempfile` and `ast`.

**Spec:** `docs/2026-10-26-python-data-detective-design.md`. Read it alongside this plan; section numbers below (e.g. §6.5) refer to it.

## Global Constraints

- **Python 3.9 or newer.** No `match` statements and no `X | Y` type unions; use `Optional[X]` from `typing`. Built-in generics like `list[str]` are fine.
- **Standard library only** inside `python_data_detective/`. Nothing there imports from `dev_tests/` or `docs/`.
- **App imports are plain**, e.g. `from dataset import Dataset`, because `main.py` is run as a script.
- **Paths are built from `__file__`.** `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`.
- **Our own output is ASCII-only, and no output line is longer than 64 characters** (`WIDTH = 64` in `report.py`). Values quoted from the data are printed as they are, but cut to fit.
- **Rule values, copied from the spec:**
  - `MISSING_MARKERS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}`
  - `NUMERIC_THRESHOLD = 0.8`
  - `WEIGHTS = (0.4, 0.3, 0.3)`
  - Verdict bands (minimum score, short verdict, full verdict): 95 "Case closed" / "Case closed - ready for analysis"; 85 "Minor clean-up" / "Minor clean-up needed"; 70 "Needs cleaning" / "Significant cleaning needed"; 0 "Unreliable" / "Unreliable evidence - investigate before use".
- **Style:** PEP 8. Every module starts with a docstring. Every class, function and method has a docstring and full type hints.
- **Tests** live in `dev_tests/` at the project root and are **not submitted**. They use `unittest`. Run them from the project root with `python -m unittest discover -s dev_tests -v`.
- **Commits:** every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Running from another working directory.** The tutor runs `python python_data_detective/main.py` from elsewhere. The program must still find `datasets/` and `reports/`. Covered by subprocess tests in Tasks 7 and 8.
2. **A Windows "Copy as path" pasted with quotes, for a path with spaces** (the user's own vault path has spaces). Option `P` must open it. Covered in Task 7.
3. **CRLF line endings from Excel or Windows.** Line numbers and blank-line counts must still be correct. Covered by a Task 1 test, and `messy_sales.csv` is written with CRLF in Task 4.
4. **Ctrl+C or Ctrl+D inside a nested prompt** (dataset chooser, path prompt, y/n). The program prints the goodbye message with no traceback. Covered in Task 7.
5. **A single-column CSV**, where the Sniffer can't pick a delimiter. It must load as one column, not fail. Covered in Task 1.

---

### Task 1: Project skeleton, errors and `Dataset`

**Files:**
- Create: `.gitignore`, `python_data_detective/errors.py`, `python_data_detective/dataset.py`, `python_data_detective/datasets/.gitkeep`
- Test: `dev_tests/context.py`, `dev_tests/test_dataset.py`

**Interfaces:**
- Produces:
  - `errors.py`: `DatasetError(Exception)`, `UnreadableFileError(DatasetError)`, `EmptyDatasetError(DatasetError)`
  - `dataset.py`: constants `SNIFF_SAMPLE_SIZE = 4096`, `DELIMITERS = ",;\t|"`
  - `Dataset(path: str)`, with attributes `path: str`, `name: str`, `encoding: str` (`"utf-8"` or `"latin-1"`), `delimiter: str`, `header: list[str]`, `rows: list[list[str]]`, `line_numbers: list[int]`, `malformed_rows: list[tuple[int, int]]`, `blank_lines_skipped: int`
  - `Dataset` methods: `num_rows() -> int`, `num_columns() -> int`, `column_values(index: int) -> list[str]`, `preview(n: int = 5) -> list[list[str]]`, `__str__() -> str`
  - `dev_tests/context.py`: `ROOT`, `APP_DIR`, `write_file(content, name="t.csv", encoding="utf-8", folder=None) -> str` (`content` is text or bytes), `make_dataset(text, name="t.csv", encoding="utf-8") -> Dataset`

- [ ] **Step 1: Initialise git and the folders**

Run from the project root: `git init`, then create `.gitignore` containing `__pycache__/` and `python_data_detective/reports/`, plus the empty `python_data_detective/datasets/.gitkeep`.
Expected: `git status` lists `.gitignore`, `docs/`, `Project Instructions.txt` and the `.docx` as untracked.

- [ ] **Step 2: Write `dev_tests/context.py`**

```python
"""Test helpers: put the app on sys.path and build temporary datasets."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "python_data_detective")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.join(APP_DIR, "tools"))


def write_file(content, name="t.csv", encoding="utf-8", folder=None):
    """Write text (newline="" keeps \\r\\n) or bytes; return the path."""
    folder = folder or tempfile.mkdtemp()
    path = os.path.join(folder, name)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
    return path


def make_dataset(text, name="t.csv", encoding="utf-8"):
    """Build a Dataset from CSV text written to a temporary file."""
    from dataset import Dataset
    return Dataset(write_file(text, name, encoding))
```

- [ ] **Step 3: Write the failing tests in `dev_tests/test_dataset.py`**

Each test builds its input with `make_dataset(text)` (or `write_file` for bytes and paths):

| Test | Input | Assertions |
|---|---|---|
| `test_loads_simple_csv` | `"a,b\n1,2\n3,4\n"` | `header == ["a","b"]`, `rows == [["1","2"],["3","4"]]`, `line_numbers == [2,3]`, `delimiter == ","`, `encoding == "utf-8"`, `num_rows() == 2`, `num_columns() == 2`, `str(ds) == "t.csv (2 rows x 2 columns)"` |
| `test_strips_bom` | `"﻿id,name\n1,x\n"` | `header[0] == "id"` |
| `test_detects_semicolon` | `'id;city\n1;"Sydney, NSW"\n2;Perth\n'` | `delimiter == ";"`, `rows[0] == ["1","Sydney, NSW"]` |
| `test_line_break_in_quoted_field` | `'id,note\n1,"two\nlines"\n2,ok\n'` | `rows[0][1] == "two\nlines"`, `line_numbers == [2,4]` |
| `test_skips_blank_lines` | `"a,b\n\n1,2\n   \n3,4\n"` | `num_rows() == 2`, `blank_lines_skipped == 2`, `line_numbers == [3,5]` |
| `test_all_empty_fields_is_data` | `"a,b\n,\n1,2\n"` | `num_rows() == 2` |
| `test_crlf_line_endings` (Review Focus 3) | `"a,b\r\n1,2\r\n\r\n3,4\r\n"` | `line_numbers == [2,4]`, `blank_lines_skipped == 1` |
| `test_single_column` (Review Focus 5) | `"score\n1.5\n2\n3\n"` | `num_columns() == 1`, `delimiter == ","`, `num_rows() == 3` |
| `test_pads_and_trims` | `"a,b,c\n1,2\n1,2,3,4\n"` | `rows == [["1","2",""],["1","2","3"]]`, `malformed_rows == [(2,2),(3,4)]` |
| `test_blank_header_names` | `"id,,score\n1,x,2\n"` | `header == ["id","column_2","score"]` |
| `test_latin1_fallback` | `"name\ncafé\n"` written as `latin-1` | `encoding == "latin-1"`, `rows[0][0] == "café"` |
| `test_empty_file` | `""` | raises `EmptyDatasetError`, `str(err) == "file is empty"` |
| `test_only_blank_lines` | `"\n\n"` | raises `EmptyDatasetError`, `str(err) == "file is empty"` |
| `test_header_only` | `"a,b\n"` | raises `EmptyDatasetError`, `str(err) == "file has a header but no data rows"` |
| `test_binary_file` | bytes `b"\x89PNG\r\n\x1a\n\x00\x00"` | raises `UnreadableFileError`, `str(err) == "doesn't look like a plain text CSV"` |
| `test_missing_file` | path in an empty temp dir | raises `UnreadableFileError`, `str(err) == f"no file at '{path}'"` |
| `test_folder` | a temp dir path | raises `UnreadableFileError`, `str(err) == f"'{path}' is a folder, not a file"` |
| `test_csv_parse_error` | `"a\n" + "x" * 200000 + "\n"` | raises `UnreadableFileError`, `str(err).startswith("couldn't be read as CSV: ")` |
| `test_column_values_and_preview` | `"a,b\n1,x\n2,y\n3,z\n"` | `column_values(1) == ["x","y","z"]`, `preview(2) == [["1","x"],["2","y"]]` |

- [ ] **Step 4: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_dataset -v`
Expected: errors with `ModuleNotFoundError: No module named 'dataset'`.

- [ ] **Step 5: Implement `errors.py` and `Dataset` in `dataset.py`**

Follow spec §4.5. The decisions the tests don't fully determine:
- **Folders first.** Check `os.path.isdir(path)` before opening, because Windows raises `PermissionError` (not `IsADirectoryError`) for folders. `FileNotFoundError` gives `"no file at '<path>'"`, and `PermissionError` gives `"no permission to read '<path>'"`.
- **Reading.** Open with `encoding="utf-8-sig", newline=""` and read the whole text, retrying with `latin-1` on `UnicodeDecodeError`. Check for `"\x00"`, then run the Sniffer on `text[:SNIFF_SAMPLE_SIZE]` with `delimiters=DELIMITERS` (`csv.Error` → `","`). Parse with `csv.reader(io.StringIO(text, newline=""), delimiter=...)`, and turn a `csv.Error` raised during iteration into `UnreadableFileError(f"couldn't be read as CSV: {err}")`.
- **Start line numbers:**
  ```python
  previous_end = 0
  for fields in reader:
      start_line = previous_end + 1
      previous_end = reader.line_num
  ```
- **Blank rows.** A row is blank if `len(fields) == 0`, or if it has exactly one field and that field is empty after `strip()`. Known limitation: in a single-column file, an empty value therefore counts as a blank line rather than a missing value.
- **Malformed rows.** Record `(start_line, len(fields))`, then pad with `""` or trim to the header's length.

- [ ] **Step 6: Run the tests to check they pass**

Run: `python -m unittest dev_tests.test_dataset -v`
Expected: all 19 tests pass.

- [ ] **Step 7: Commit**

```bash
git add .gitignore docs dev_tests python_data_detective "Project Instructions.txt" Python_Data_Detective_Project_Overview.docx
git commit -m "feat: add Dataset loading with custom exceptions"
```

---

### Task 2: Investigator rules and column profiles

**Files:**
- Create: `python_data_detective/investigator.py`
- Test: `dev_tests/test_investigator.py`

**Interfaces:**
- Consumes: `Dataset` (Task 1).
- Produces:
  - `ColumnProfile(name: str)`, with attributes `name: str`, `kind: str` (`"numeric"`, `"text"` or `"empty"`), `missing: int`, `invalid: int`, `invalid_examples: list[tuple[str, int]]`, `stats: Optional[tuple[float, float, float, float]]` (min, max, mean, median), `unique_count: int`, `most_common: Optional[tuple[str, int]]`
  - `Investigator(dataset: Dataset)`, with class variables `MISSING_MARKERS`, `NUMERIC_THRESHOLD`, `WEIGHTS`, `VERDICT_BANDS: list[tuple[int, str, str]]`, `MAX_EXAMPLES = 3`
  - Static methods `is_missing(value: str) -> bool`, `is_number(value: str) -> bool`, `verdict_for(score: int) -> tuple[str, str]` (short, full)
  - `Investigator._profile_column(index: int) -> ColumnProfile`

- [ ] **Step 1: Write the failing tests in `dev_tests/test_investigator.py`**

```python
def test_is_missing(self):
    for v in ["", "  ", "NA", "n/a", "N/A", "null", "NULL", "None", "nan",
              "NaN", "-", "?", " na "]:
        self.assertTrue(Investigator.is_missing(v), v)
    for v in ["0", "--", "N.A.", "none of them", "x"]:
        self.assertFalse(Investigator.is_missing(v), v)

def test_is_number(self):
    for v in ["3.5", "-2", "+5", "1e3", " 42 ", "0"]:
        self.assertTrue(Investigator.is_number(v), v)
    for v in ["inf", "-inf", "nan", "1,204", "$15", "twelve", ""]:
        self.assertFalse(Investigator.is_number(v), v)

def test_verdict_bands(self):
    cases = {100: "Case closed", 95: "Case closed", 94: "Minor clean-up",
             85: "Minor clean-up", 84: "Needs cleaning", 70: "Needs cleaning",
             69: "Unreliable", 0: "Unreliable"}
    for score, short in cases.items():
        self.assertEqual(Investigator.verdict_for(score)[0], short)
    self.assertEqual(Investigator.verdict_for(94)[1], "Minor clean-up needed")
```

Column-profile tests. Each one builds a one-column dataset from `"v\n" + "\n".join(values) + "\n"` and calls `_profile_column(0)`. Blank values must not be used here, because a single-column file skips blank lines (Task 1). Use `"NA"` for missing values instead.

| Test | Values | Assertions |
|---|---|---|
| `test_exactly_80_percent_is_numeric` | `1 2 3 4 x` | `kind == "numeric"`, `invalid == 1`, `invalid_examples == [("x", 6)]`, `stats == (1.0, 4.0, 2.5, 2.5)` |
| `test_below_threshold_is_text` | `1 2 3 x y` | `kind == "text"`, `invalid == 0`, `unique_count == 5`, `most_common == ("1", 1)` (ties go to the value seen first) |
| `test_missing_is_not_invalid` | `1 NA 2 ?` | `kind == "numeric"`, `missing == 2`, `invalid == 0`, `stats == (1.0, 2.0, 1.5, 1.5)` |
| `test_empty_column` | `NA null` | `kind == "empty"`, `missing == 2`, `stats is None`, `most_common is None` |
| `test_examples_capped_in_file_order` | `1`–`20`, then `a b c d` | `invalid == 4`, `len(invalid_examples) == 3`, `invalid_examples[0] == ("a", 22)` |
| `test_text_values_are_stripped` | `North South North " North "` | `unique_count == 2`, `most_common == ("North", 3)` |

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_investigator -v`
Expected: `ModuleNotFoundError: No module named 'investigator'`.

- [ ] **Step 3: Implement `ColumnProfile` and the `Investigator` rules**

- `is_number` checks `math.isfinite(float(value.strip()))` inside `try/except ValueError`.
- Stats use `min`, `max`, `statistics.mean` and `statistics.median` over the valid numbers only.
- `most_common` uses `collections.Counter(...).most_common(1)`, which keeps the first-seen order for ties.
- Example values are stored stripped.
- A numeric column always has at least one valid number because of the threshold, so `stats` is `None` only for text and empty columns. The spec's "no valid numbers" case can't happen and isn't implemented.

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest dev_tests.test_investigator -v`
Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python_data_detective/investigator.py dev_tests/test_investigator.py
git commit -m "feat: add missing/number rules and column profiles"
```

---

### Task 3: `investigate()`, `Findings`, duplicates and scores

**Files:**
- Modify: `python_data_detective/investigator.py`, `dev_tests/context.py` (add `SAMPLE_TEXT`)
- Test: `dev_tests/test_investigator.py` (add a `TestInvestigate` class)

**Interfaces:**
- Consumes: Task 2's `Investigator` and `ColumnProfile`.
- Produces:
  - `Findings(dataset: Dataset)`. The constructor sets defaults, and `investigate()` fills in `profiles: list[ColumnProfile]`, `duplicates: list[tuple[int, int]]` (copy line, original line), `total_cells`, `missing_cells`, `numeric_cells`, `invalid_cells: int`, `completeness`, `uniqueness`, `validity: float` (one decimal place), `overall: int`, `verdict: str`, `short_verdict: str` and `investigated_at: datetime`
  - `Investigator.investigate() -> Findings`
  - `context.SAMPLE_TEXT`, the shared 10-row fixture

- [ ] **Step 1: Add `SAMPLE_TEXT` to `dev_tests/context.py`**

```python
# 10 rows x 2 columns: 2 missing (lines 7, 10), 1 invalid ('bad', line 9),
# 1 duplicate (line 11 copies line 2). Expected overall score: 90.
SAMPLE_TEXT = ("a,b\n1,x\n2,y\n3,z\n4,w\n5,v\n6,\n7,u\nbad,t\nNA,s\n1,x\n")
```

- [ ] **Step 2: Write the failing tests**

```python
def test_sample_scores(self):
    f = Investigator(make_dataset(SAMPLE_TEXT)).investigate()
    self.assertEqual((f.total_cells, f.missing_cells), (20, 2))
    self.assertEqual((f.numeric_cells, f.invalid_cells), (9, 1))
    self.assertEqual(f.duplicates, [(11, 2)])
    self.assertEqual((f.completeness, f.uniqueness, f.validity),
                     (90.0, 90.0, 88.9))
    self.assertEqual(f.overall, 90)
    self.assertEqual(f.short_verdict, "Minor clean-up")
    self.assertEqual(f.verdict, "Minor clean-up needed")
    self.assertIsInstance(f.investigated_at, datetime.datetime)
    self.assertEqual(len(f.profiles), 2)

def test_duplicates_ignore_spaces_but_not_case(self):
    f = Investigator(make_dataset(
        "a,b\n1,x\nNorth,1\n 1 , x \nnorth,1\n")).investigate()
    self.assertEqual(f.duplicates, [(4, 2)])

def test_validity_100_without_numeric_columns(self):
    f = Investigator(make_dataset("name\nAnn\nBob\n")).investigate()
    self.assertEqual((f.numeric_cells, f.validity), (0, 100.0))

def test_overall_rounds_half_up(self):
    # 20 unique rows, 1 invalid number -> 40 + 30 + 28.5 = 98.5 -> 99
    text = "n,id\n" + "".join(f"{i},r{i}\n" for i in range(19)) + "oops,r19\n"
    self.assertEqual(Investigator(make_dataset(text)).investigate().overall, 99)

def test_padded_cells_count_as_missing(self):
    f = Investigator(make_dataset("a,b,c\n1,2\n3,4,5\n")).investigate()
    self.assertEqual(f.missing_cells, 1)
```

- [ ] **Step 3: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_investigator -v`
Expected: `NameError` or `AttributeError` for `investigate` / `Findings`.

- [ ] **Step 4: Implement `Findings` and `investigate()`**

- **Duplicates:** a `dict` maps `tuple(cell.strip() for cell in row)` to the line where that row first appeared.
- **Scores:**
  - Calculate the sub-scores as in spec §5.2 and store each with `round(x, 1)`.
  - Calculate `overall` from the **unrounded** sub-scores, then apply `math.floor(x + 0.5)`.
  - Validity is `100.0` when `numeric_cells == 0`.

- [ ] **Step 5: Run the tests to check they pass**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test so far passes (33).

- [ ] **Step 6: Commit**

```bash
git add python_data_detective/investigator.py dev_tests
git commit -m "feat: add investigation with duplicates and quality scores"
```

---

### Task 4: Dataset generator and answer-key integration test

**Files:**
- Create: `python_data_detective/tools/make_datasets.py`, plus 7 generated files in `python_data_detective/datasets/`
- Test: `dev_tests/test_answer_key.py`

**Interfaces:**
- Consumes: `Dataset`, `Investigator`, and the errors module (Tasks 1–3).
- Produces:
  - `build_datasets(folder: str) -> dict[str, dict]`, which writes the files and returns the answer key
  - `main() -> None`, which writes to `<app>/datasets/` and prints the key
  - **Answer-key format:**
    - Loadable files: `{"rows", "columns", "delimiter", "encoding", "missing", "invalid", "duplicates", "malformed", "blank_lines"}`, plus `"duplicate_lines": list[tuple[int, int]]` for `messy_sales.csv` and `tricky_addresses.csv`.
    - Files that should fail: `{"error": "EmptyDatasetError"}` or `{"error": "UnreadableFileError"}`.

**Generator rules**
- Use `random.Random(9001)` for all randomness. The header comment says the file was written with AI assistance and isn't needed to run the app.
- Base rows are unique by their ID column, and base values are never missing markers.
- **Every key count comes from what was injected, never from re-running the app's rules.**
  - Each injected missing or invalid value goes into a different cell.
  - Malformed rows get no other injections.
  - Duplicates copy only rows with no injections, and each copy is inserted somewhere after its source row.
  - Expected missing = injected missing values + padded cells from short rows.
- **Line tracking.** Write each row with `csv.writer` into its own `io.StringIO`, using the file's line terminator. Count the `"\n"` characters in the result. A row's start line is 1 + the count for the header + the counts for all earlier rows and blank lines.

**What each file contains**

| File | Rows | Columns | Format | What's injected |
|---|---|---|---|---|
| `student_grades.csv` | 120 (119 base + 1 duplicate) | `student_id,name,tutorial,assignment,exam,final_grade` | `,` and `\n` | 4 blanks (`assignment` ×2, `exam` ×1, `tutorial` ×1) |
| `messy_sales.csv` | 200 (190 base + 10 duplicates) | `order_id,region,product,price,qty,rating` | `,` and **`\r\n`** | 40 missing: each of `"" NA N/A null None nan - ?` five times, spread over `region/price/qty/rating`<br>16 invalid: `price` gets `twelve`, `$15`, `1,204`, `15.00 AUD` ×2 each; `rating` gets `5 stars`, `four`, `**`, `N.A.` ×2 each<br>2 blank lines, after the 50th and 120th data rows |
| `tricky_addresses.csv` | 80 (78 base + 2 duplicates) | `id;name;address;city;postcode;notes` | `;`, `\n`, written as `utf-8-sig` | Addresses contain 0–2 commas (varying). Two `name` values contain `;` and sit within the first 10 rows (this lets the Sniffer find `;`). 3 `notes` contain `\n`. 3 `notes` are blank. One duplicate's source comes after a `notes` value containing a line break |
| `old_export_latin1.csv` | 30 | `customer_id,name,city,spend` | `,`, `\n`, written as `latin-1` | Names and cities with `é ë ü ã` (José, Zoë, Müller, São Paulo). 2 blank `city` values. 1 invalid `spend` (`abc`) |
| `broken_rows.csv` | 60 (45 base + 15 duplicates) | `sensor_id,,reading,unit,status` (2nd name blank) | `,` and `\n` | 6 rows with an extra field `EXTRA`; 5 rows with only 3 fields (+10 padded missing). 30 injected missing, at most 5 in `reading`. 6 invalid `reading` values: `ERR`, `--`, `high` ×2 each |
| `empty.csv` | — | — | 0 bytes | — |
| `not_really_a_csv.csv` | — | — | bytes: `b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"` + `rng.randbytes(64)` | — |

Expected keys for the loadable files:
- `student_grades.csv`: missing 4, invalid 0, duplicates 1, malformed 0, blank lines 0
- `messy_sales.csv`: missing 40, invalid 16, duplicates 10, malformed 0, blank lines 2
- `tricky_addresses.csv`: missing 3, invalid 0, duplicates 2, malformed 0, blank lines 0
- `old_export_latin1.csv`: missing 2, invalid 1, duplicates 0, malformed 0, blank lines 0
- `broken_rows.csv`: missing 40, invalid 6, duplicates 15, malformed 11, blank lines 0

`encoding` is `"latin-1"` for the latin-1 file and `"utf-8"` for every other file.

- [ ] **Step 1: Write the failing tests in `dev_tests/test_answer_key.py`**

```python
def test_every_dataset_matches_answer_key(self):
    folder = tempfile.mkdtemp()
    for name, key in make_datasets.build_datasets(folder).items():
        with self.subTest(name):
            path = os.path.join(folder, name)
            if "error" in key:
                with self.assertRaises(getattr(errors, key["error"])):
                    Dataset(path)
                continue
            ds = Dataset(path)
            f = Investigator(ds).investigate()
            got = {"rows": ds.num_rows(), "columns": ds.num_columns(),
                   "delimiter": ds.delimiter, "encoding": ds.encoding,
                   "missing": f.missing_cells, "invalid": f.invalid_cells,
                   "duplicates": len(f.duplicates),
                   "malformed": len(ds.malformed_rows),
                   "blank_lines": ds.blank_lines_skipped}
            if "duplicate_lines" in key:
                got["duplicate_lines"] = f.duplicates
            self.assertEqual(got, key)

def test_generator_is_deterministic(self):
    a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
    make_datasets.build_datasets(a)
    make_datasets.build_datasets(b)
    for name in os.listdir(a):
        with open(os.path.join(a, name), "rb") as x, \
             open(os.path.join(b, name), "rb") as y:
            self.assertEqual(x.read(), y.read(), name)
```

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_answer_key -v`
Expected: `ModuleNotFoundError: No module named 'make_datasets'`.

- [ ] **Step 3: Implement `make_datasets.py`, following the rules and table above**

If the Sniffer picks the wrong delimiter for a file, fix the generated data within these rules. Never special-case a file name in `Dataset`.

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest dev_tests.test_answer_key -v`
Expected: 2 tests pass, and every subtest passes.

- [ ] **Step 5: Generate the real files**

Run: `python python_data_detective/tools/make_datasets.py`
Expected: 7 files appear in `python_data_detective/datasets/`, and the answer key is printed.

- [ ] **Step 6: Commit**

```bash
git add python_data_detective/tools python_data_detective/datasets dev_tests/test_answer_key.py
git commit -m "feat: add seeded dataset generator with answer key"
```

---

### Task 5: `Report`: case report, saving and the evidence screen

**Files:**
- Create: `python_data_detective/report.py`
- Test: `dev_tests/test_report.py`

**Interfaces:**
- Consumes: `Findings`, `Dataset`, and `make_datasets.build_datasets` (for test data only).
- Produces:
  - Constants: `WIDTH = 64`, `MAX_LISTED = 10`, `CELL_WIDTH = 12`, `VALUE_WIDTH = 15`, `NAME_WIDTH = 14`, `PREVIEW_ROWS = 5`, and `DELIMITER_NAMES = {",": "','", ";": "';'", "\t": "tab", "|": "'|'"}`
  - Helpers: `shorten(text: str, width: int) -> str` (cut to `width - 2` characters + `".."`), `format_stat(value: float) -> str` (1 decimal place, with a trailing `.0` dropped)
  - `Report(findings: Findings)`, with `to_text() -> str` and `save(folder: str) -> tuple[str, bool]`
  - `@staticmethod Report.evidence_text(dataset: Dataset) -> str`

**Layout:** follow spec §6.5. Column names in SUSPECTS and COLUMN PROFILES use `NAME_WIDTH` (14) and are cut with `shorten`.
- **EVIDENCE line:** `f"  {rows:,} rows x {cols} columns  ({details})"`. `details` joins these parts with `", "`: `f"delimiter {DELIMITER_NAMES[d]}"`, then `f"{n} blank line(s) skipped"` if `n > 0`, then `f"encoding {enc}"` if the encoding isn't UTF-8.
- **Singular and plural:** `"1 duplicate row"` / `"N duplicate rows"`, and the same pattern for malformed rows and blank lines.
- **Line breaks in data values:** before printing any value from the data, replace `\n` and `\r` with a space, then cut it to fit.
- **`evidence_text` layout:**
  ```
  [EVIDENCE] <name>
    Rows: <rows:,>   Columns: <cols>
    Delimiter: <DELIMITER_NAMES[d]>   Encoding: <enc>   Blank lines skipped: <n>
    Columns: <names joined by ", ", wrapped to WIDTH with 4-space indent>
    Preview (first 5 rows):
    <header and up to PREVIEW_ROWS rows, cells shortened to CELL_WIDTH and
     joined by " | "; add columns while the line fits WIDTH, then
     "(+N more columns)" on its own line>
  ```

- [ ] **Step 1: Write the failing tests in `dev_tests/test_report.py`**

```python
def test_shorten_and_format_stat(self):
    self.assertEqual(shorten("abcdefghijklmnop", 12), "abcdefghij..")
    self.assertEqual(shorten("short", 12), "short")
    self.assertEqual([format_stat(v) for v in (1.0, 100.5, 24.13, 2.0)],
                     ["1", "100.5", "24.1", "2"])

def test_sample_report_lines(self):
    text = Report(Investigator(make_dataset(SAMPLE_TEXT)).investigate()).to_text()
    for line in ["[EVIDENCE]", "  10 rows x 2 columns  (delimiter ',')",
                 "[SUSPECTS]  columns with problems",
                 "[DUPLICATES]  1 duplicate row", "  line 11 duplicates line 2",
                 "[MALFORMED ROWS]  none found", "[COLUMN PROFILES]",
                 "  Completeness  90.0%  (2 of 20 cells missing)",
                 "  Uniqueness    90.0%  (1 of 10 rows duplicated)",
                 "  Validity      88.9%  (1 of 9 numeric values invalid)",
                 "VERDICT: 90/100  -  Minor clean-up needed"]:
        self.assertIn(line, text.splitlines())
    self.assertIn("'bad' (line 9)", text)
    self.assertRegex(text, r"CASE FILE #\d{8}-\d{4}")
    self.assertTrue(text.isascii())

def test_clean_report_messages(self):
    text = Report(Investigator(make_dataset("a,b\n1,x\n2,y\n")).investigate()).to_text()
    self.assertIn("No suspects - every column checks out.", text)
    self.assertIn("[DUPLICATES]  none found", text)

def test_lines_fit_width(self):
    folder = tempfile.mkdtemp()
    make_datasets.build_datasets(folder)
    long_text = ("a_really_long_column_name_that_goes_on,b\n"
                 + "1,x\n" * 9 + ("y" * 40) + ",z\n")
    texts = [Report(Investigator(make_dataset(long_text)).investigate()).to_text()]
    for name in ["messy_sales.csv", "broken_rows.csv", "tricky_addresses.csv"]:
        ds = Dataset(os.path.join(folder, name))
        texts.append(Report(Investigator(ds).investigate()).to_text())
        texts.append(Report.evidence_text(ds))
    for text in texts:
        for line in text.splitlines():
            self.assertLessEqual(len(line), WIDTH, line)

def test_save_and_replace(self):
    report = Report(Investigator(make_dataset(SAMPLE_TEXT)).investigate())
    folder = os.path.join(tempfile.mkdtemp(), "new")
    path, replaced = report.save(folder)
    self.assertTrue(path.endswith("t_report.txt"))
    self.assertFalse(replaced)
    with open(path, encoding="utf-8") as f:
        self.assertEqual(f.read(), report.to_text())
    self.assertTrue(report.save(folder)[1])

def test_evidence_preview(self):
    wide = ",".join(f"col{i}" for i in range(8)) + "\n" + \
           ("".join("x" * 20 + "," for _ in range(7)) + "end\n") * 7
    text = Report.evidence_text(make_dataset(wide))
    self.assertIn("more columns)", text)
    self.assertIn("xxxxxxxxxx..", text)
    self.assertNotIn("end", text.split("Preview")[-1])  # extra columns cut off
    latin = make_dataset("name\ncafé\n", encoding="latin-1")
    self.assertIn("Encoding: latin-1", Report.evidence_text(latin))

def test_line_breaks_in_values_are_flattened(self):
    ds = make_dataset('id,note\n1,"top\nbottom"\n2,"top\nbottom"\n')
    self.assertIn("top bottom", Report.evidence_text(ds))
    self.assertIn("'top bottom'", Report(Investigator(ds).investigate()).to_text())
```

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_report -v`
Expected: `ModuleNotFoundError: No module named 'report'`.

- [ ] **Step 3: Implement `report.py`, following spec §6.3 and §6.5 plus the layout notes above**

`save` uses `os.makedirs(folder, exist_ok=True)` and names the file with `os.path.splitext(dataset.name)[0] + "_report.txt"`. It checks `os.path.exists` before writing to work out `replaced`.

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest dev_tests.test_report -v`
Expected: 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python_data_detective/report.py dev_tests/test_report.py
git commit -m "feat: add themed case report, saving and evidence screen"
```

---

### Task 6: Leaderboard text

**Files:**
- Modify: `python_data_detective/report.py`
- Test: `dev_tests/test_report.py` (add a `TestLeaderboard` class)

**Interfaces:**
- Produces: constant `BOARD_NAME_WIDTH = 22`, and `@staticmethod Report.leaderboard_text(findings_list: list[Findings], failures: list[tuple[str, str]]) -> str`. The layout follows spec §6.6. Dataset names are cut to `BOARD_NAME_WIDTH`, and each failure-reason line is cut to `WIDTH`.

- [ ] **Step 1: Write the failing tests**

```python
def _findings(self, name, score, short):
    f = Findings(make_dataset("a\n1\n", name=name))
    f.overall, f.short_verdict = score, short
    return f

def test_sorted_by_score_then_name(self):
    text = Report.leaderboard_text(
        [self._findings("b.csv", 90, "Minor clean-up"),
         self._findings("C.csv", 97, "Case closed"),
         self._findings("a.csv", 90, "Minor clean-up")], [])
    order = [l.split()[1] for l in text.splitlines() if l[:3].strip().isdigit()]
    self.assertEqual(order, ["C.csv", "a.csv", "b.csv"])

def test_failures_last_with_reasons(self):
    text = Report.leaderboard_text([self._findings("a.csv", 90, "Minor clean-up")],
                                   [("empty.csv", "file is empty")])
    lines = text.splitlines()
    fail_row = next(l for l in lines if "empty.csv" in l and "Could not open" in l)
    self.assertTrue(fail_row.strip().startswith("--"))
    self.assertIn("  empty.csv: file is empty", lines)

def test_leaderboard_fits_width(self):
    text = Report.leaderboard_text(
        [self._findings("x" * 30 + ".csv", 50, "Unreliable")],
        [("y" * 30 + ".csv", "couldn't be read as CSV: " + "z" * 80)])
    for line in text.splitlines():
        self.assertLessEqual(len(line), WIDTH, line)
```

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_report -v`
Expected: `AttributeError: type object 'Report' has no attribute 'leaderboard_text'`.

- [ ] **Step 3: Implement `leaderboard_text`**

Sort with `sorted(findings_list, key=lambda f: (-f.overall, f.dataset.name.lower()))`. Rows use thousands separators.

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest dev_tests.test_report -v`
Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add python_data_detective/report.py dev_tests/test_report.py
git commit -m "feat: add leaderboard text"
```

---

### Task 7: `main.py`: menu, opening a case, inspecting, investigating, saving, quitting

**Files:**
- Create: `python_data_detective/main.py`
- Test: `dev_tests/test_main.py`

**Interfaces:**
- Consumes: `Dataset`, `DatasetError`, `Investigator`, `Findings`, `Report`, `DELIMITER_NAMES`.
- Produces:
  - Module globals `BASE_DIR`, `DATASETS_DIR`, `REPORTS_DIR`. Functions read these **when called**, not through default arguments, so the tests can patch them.
  - `list_csv_files(folder: str) -> list[str]`
  - `ask_yes_no(prompt: str) -> bool`
  - `choose_dataset() -> Optional[Dataset]`
  - `show_menu(current: Optional[Dataset]) -> None`
  - `save_report(findings: Findings) -> None`
  - `main() -> None`

**Exact messages:**

| Situation | Text |
|---|---|
| Bad menu input | `Please enter a number from 0 to 5` |
| Option 2–4 with no case | `No case open - choose option 1 first` |
| Status line | `  Current case: none` / `  Current case: <str(dataset)>` |
| Case opened | `Opening case... <name> (<rows> rows x <cols> columns, delimiter <DELIMITER_NAMES[d]>)` |
| Case failed | `Could not open case: <reason>` |
| No CSVs | `The evidence locker is empty` |
| Bad chooser input | `Please enter a number from 1 to <n>, P or B` (or `Please enter P or B` when there are no files) |
| Path prompt | `Path to a CSV file: ` (strip spaces, then one pair of surrounding `"` or `'`) |
| Saved | `Report saved to <os.path.relpath(path, BASE_DIR)>`, plus ` (replaced the previous report)` if a file was overwritten |
| Save failed | `Could not save report: <err>` |
| Bad y/n input | `Please enter y or n` (accepts `y/yes/n/no` in any case) |
| Goodbye (printed in `finally`) | `Case closed. Goodbye, detective.` |

The first line of `main.py` is the comment `# RUN THIS FILE: python main.py  (Python Data Detective)`.

- [ ] **Step 1: Write the failing tests in `dev_tests/test_main.py`**

Helper: `run(inputs)` patches `main.DATASETS_DIR` and `main.REPORTS_DIR` to temp folders, patches `builtins.input` with `side_effect=inputs`, captures stdout with `contextlib.redirect_stdout`, calls `main.main()` and returns the output. `setUp` puts `t.csv` (`SAMPLE_TEXT`) into the temp datasets folder.

| Test | Inputs | Assertions |
|---|---|---|
| `test_list_csv_files` | folder with `b.CSV`, `a.csv`, `notes.txt` | `== ["a.csv", "b.CSV"]`; a missing folder gives `[]` |
| `test_ask_yes_no` | `["maybe", "Y"]`, then `["no"]` | `True` with `Please enter y or n` printed; then `False` |
| `test_bad_menu_input` | `["9", "abc", "", "0"]` | `out.count("Please enter a number from 0 to 5") == 3`; `out.rstrip().endswith("Case closed. Goodbye, detective.")`; `out.isascii()` |
| `test_chooser_bad_input` | `["1", "7", "x", "b", "0"]` | `out.count("Please enter a number from 1 to 1, P or B") == 2`; lowercase `b` goes back to the menu |
| `test_needs_open_case` | `["2", "3", "4", "0"]` | `out.count("No case open - choose option 1 first") == 3` |
| `test_open_run_save` | `["1", "1", "3", "4", "4", "0"]` | contains `Opening case... t.csv (10 rows x 2 columns, delimiter ',')`, `VERDICT: 90/100`, `Report saved to`, `(replaced the previous report)`; `t_report.txt` exists |
| `test_save_runs_investigation` | `["1", "1", "4", "0"]` | `t_report.txt` exists |
| `test_bad_dataset_reason` | `e.csv` (empty) added; `["1", "1", "0"]` | contains `Could not open case: file is empty` |
| `test_quoted_path_with_spaces` (Review Focus 2) | `x y.csv` in a temp `my data/` folder; `["1", "P", f'"{path}"', "0"]` | contains `Opening case... x y.csv` |
| `test_empty_locker` | empty datasets folder; `["1", "B", "0"]` | contains `The evidence locker is empty` |
| `test_eof_in_chooser` (Review Focus 4) | `["1", EOFError()]` | no exception; ends with the goodbye message |
| `test_ctrl_c_at_menu` (Review Focus 4) | `[KeyboardInterrupt()]` | no exception; ends with the goodbye message |
| `test_save_error_reported` | `REPORTS_DIR` points to an existing *file*; `["1", "1", "4", "0"]` | contains `Could not save report:` |
| `test_runs_from_other_directory` (Review Focus 1) | `subprocess.run([sys.executable, main_path], input="1\n1\n3\n0\n", cwd=tempfile.mkdtemp(), capture_output=True, text=True, timeout=60, env={**os.environ, "PYTHONIOENCODING": "utf-8"})` | `returncode == 0`, `"VERDICT:" in stdout`, `"Traceback" not in stderr` |

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_main -v`
Expected: `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Implement `main.py`, following spec §4.8, §6.1–§6.4 and §6.7**

Wrap the menu loop in `try: ... except (KeyboardInterrupt, EOFError): print() ... finally: print("Case closed. Goodbye, detective.")`. Use `break` on `0`, and `continue` after bad input. End the file with `if __name__ == "__main__": main()`. Opening a new case clears the current findings. Option 4 runs the investigation silently if it hasn't been run.

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test so far passes.

- [ ] **Step 5: Commit**

```bash
git add python_data_detective/main.py dev_tests/test_main.py
git commit -m "feat: add menu-driven case desk"
```

---

### Task 8: Investigate ALL

**Files:**
- Modify: `python_data_detective/main.py`
- Test: `dev_tests/test_main.py` (add tests)

**Interfaces:**
- Produces: `investigate_all() -> None`, called by menu option `5`. It reads every file from `list_csv_files(DATASETS_DIR)`, collects `Findings` and failures `(name, str(err))`, prints `Report.leaderboard_text`, then asks `Save a report for every dataset? (y/n): `. On `y`, it saves each report plus `REPORTS_DIR/leaderboard.txt`. An `OSError` prints `Could not save report: <err>` and stops the saving. The current case doesn't change.

- [ ] **Step 1: Write the failing tests**

| Test | Setup and inputs | Assertions |
|---|---|---|
| `test_all_board_and_save` | `good.csv` (`"a,b\n1,x\n2,y\n"`), `t.csv`, `e.csv` (empty); `["5", "y", "0"]` | contains `CASE BOARD` and `  e.csv: file is empty`; the reports folder holds exactly `good_report.txt`, `t_report.txt` and `leaderboard.txt` |
| `test_all_no_save` | `["5", "n", "0"]` | the reports folder is missing or empty |
| `test_all_keeps_current_case` | `["1", "1", "5", "n", "0"]` | the last `Current case:` line printed shows `t.csv (10 rows x 2 columns)` |
| `test_all_empty_locker` | empty datasets folder; `["5", "0"]` | contains `The evidence locker is empty`; the y/n prompt doesn't appear |
| `test_all_from_other_directory` (Review Focus 1) | subprocess as in Task 7, with `input="5\nn\n0\n"` | `returncode == 0`, `"CASE BOARD" in stdout`, `"Traceback" not in stderr` |

- [ ] **Step 2: Run the tests to check they fail**

Run: `python -m unittest dev_tests.test_main -v`
Expected: the new tests fail (option 5 is treated as bad input, or is missing).

- [ ] **Step 3: Implement `investigate_all` and connect it to option 5**

- [ ] **Step 4: Run the tests to check they pass**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test passes.

- [ ] **Step 5: Commit**

```bash
git add python_data_detective/main.py dev_tests/test_main.py
git commit -m "feat: add investigate-all leaderboard"
```

---

### Task 9: Real datasets and score calibration

**Files:**
- Create: `python_data_detective/datasets/iris.csv`, `python_data_detective/datasets/penguins.csv`
- Modify (only if the user approves new bands): `investigator.py` `VERDICT_BANDS`, `dev_tests/test_investigator.py::test_verdict_bands`, spec §5.2
- Test: `dev_tests/test_answer_key.py` (add `test_real_datasets_load`)

- [ ] **Step 1: Ask the user's permission to download.** Don't continue without a clear yes. State:
  - `iris.data` (about 4.5 KB) from `https://archive.ics.uci.edu/ml/machine-learning-databases/iris/iris.data`, licence CC BY 4.0
  - `penguins.csv` (about 15 KB) from `https://raw.githubusercontent.com/allisonhorst/palmerpenguins/main/inst/extdata/penguins.csv`, licence CC0

- [ ] **Step 2: Download into a new, empty scratchpad folder and inspect it**

Check the size, line count, first lines and last lines. Then copy into `datasets/`:
- `iris.csv` = the header line `sepal_length,sepal_width,petal_length,petal_width,species` + the contents of `iris.data`, unchanged (keep any trailing blank lines; they're a real-world finding).
- `penguins.csv`, unchanged.

- [ ] **Step 3: Write and run `test_real_datasets_load`**

Assert:
- `iris.csv`: 150 rows, 5 columns.
- `penguins.csv`: 344 rows, 8 columns, `missing_cells > 0`.
- Record the duplicate count Iris actually shows, which settles the spec's "to confirm" note.

Run: `python -m unittest dev_tests.test_answer_key -v`
Expected: passes.

- [ ] **Step 4: Calibrate the bands**

Run: `python python_data_detective/main.py` and choose `5`, then `n`, then `0`. Write down each dataset's score and verdict, and compare them with spec §8's expectations. **Gate:** show the user the table. If messy datasets land too high, propose new cut-offs and change `VERDICT_BANDS`, its test and spec §5.2 only after the user approves.

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test passes.

- [ ] **Step 6: Commit**

```bash
git add python_data_detective/datasets dev_tests docs python_data_detective/investigator.py
git commit -m "feat: add real Iris and Palmer Penguins datasets"
```

---

### Task 10: README, documentation check and final verification

**Files:**
- Create: `python_data_detective/README.txt`
- Test: `dev_tests/test_docs.py`

- [ ] **Step 1: Write the failing test `test_every_definition_documented` in `dev_tests/test_docs.py`**

Use `ast` to parse every `.py` file in `python_data_detective/`, including `tools/`. Assert that:
- each module has a docstring;
- every `ClassDef`, `FunctionDef` and method has a docstring;
- every function has a return annotation, and every argument other than `self` has an annotation.

In each failure message, name the file, the line and the definition.

- [ ] **Step 2: Run it**

Run: `python -m unittest dev_tests.test_docs -v`
Expected: PASS if Tasks 1–8 kept to the style constraint. Otherwise, fix each reported definition until it passes.

- [ ] **Step 3: Write `README.txt`**

Use these headings in this order:
1. `PYTHON DATA DETECTIVE`: 2–3 sentences describing what it does and who it's for.
2. `HOW TO RUN`: `python main.py` (or `python3 main.py` on Ed or macOS), run inside this folder or from anywhere; reports appear in `reports/`.
3. `REQUIREMENTS`: Python 3.9 or newer; no libraries to install.
4. `WHAT'S IN THE FOLDER`: one line per file and folder, from spec §4.1.
5. `DATASETS AND SOURCES`:
   - Fisher, R. A. (1936). *Iris* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C56C76 (CC BY 4.0; header row added).
   - Horst, A. M., Hill, A. P., & Gorman, K. B. (2020). *palmerpenguins* (CC0). Data collected by Dr. Kristen Gorman and the Palmer Station LTER.
   - Files 3–9 are AI-generated by `tools/make_datasets.py`.
6. `AI USE ACKNOWLEDGEMENT`: draft wording saying the code and the dataset generator were written with help from Claude (Anthropic) and that datasets 3–9 are AI-generated. Mark the draft for the user to check against the COMP9001 AI policy.
7. `CONCEPTS BEYOND THE LECTURES`: the spec §9 list, one line each.

- [ ] **Step 4: Check that the submission folder works on its own**

Copy `python_data_detective/` to a new temp folder and delete `reports/` from the copy. From a different directory, run `python <copy>/main.py` and enter `5`, `y`, `0`.
Expected: the leaderboard is printed, `<copy>/reports/` holds 7 reports plus `leaderboard.txt`, and there's no traceback.

- [ ] **Step 5: Do the manual run-through in a real terminal (spec §10.3)**

Tick each item:
- each menu option;
- letters, out-of-range numbers and blank input at every prompt;
- `P` with a bad path, and with a quoted path containing spaces;
- Ctrl+C at the menu, the chooser, the path prompt and the y/n prompt;
- opening all 9 datasets and inspecting each one;
- investigate-all with `y` and with `n`;
- saving twice;
- reading one saved report in a text editor.

Report any failure as a bug, with a test, before fixing it.

- [ ] **Step 6: Run the full suite one last time**

Run: `python -m unittest discover -s dev_tests -v`
Expected: every test passes, with 0 failures and 0 errors.

- [ ] **Step 7: Commit, and hand the Ed check to the user**

```bash
git add python_data_detective/README.txt dev_tests/test_docs.py python_data_detective
git commit -m "docs: add README and documentation check"
```

Tell the user the step only they can do (spec §10.4): upload `python_data_detective/` to Ed, confirm `python3 --version` is 3.9 or newer, and run options 1, 3 and 5 once before submitting.
