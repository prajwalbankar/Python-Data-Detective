# Robustness report: 60 kinds of input

**Program:** Python Data Detective at commit `7e46b0f` · **Date:** 29 Oct 2026 · **Python:** 3.10.7, re-run on 3.11.11 with **identical behaviour** for all 60 scenarios

## How it was tested

`stress_tests/make_stress_files.py` builds 60 scenario files (39.5 MB) using only the standard library and a fixed seed. They include real images, audio and video, Office files and archives, databases, programs, text that isn't a CSV, number-only data, and large, messy, realistic CSVs. `stress_tests/run_stress_tests.py` then does three things:

1. Runs each file through the app's own pipeline (`Dataset` → `Investigator` → `Report`), recording the outcome and timing, and checking that no line of the program's own text is wider than 64 characters.
2. Runs the **real program** on each file the way a marker would: `1` → `P` → path → `3` → `0`.
3. Runs **Investigate ALL** on a copy of the app whose `datasets/` folder holds all 60 files mixed together. It also measures peak memory on the biggest files.

To reproduce:
```bash
python stress_tests/make_stress_files.py
python stress_tests/run_stress_tests.py
```

## After the fixes (29 Oct 2026)

Issues 1–7 below were fixed test-first, bringing the suite to 113 tests, and all 60 scenarios were run again. There are still **no crashes, tracebacks, hangs or over-wide lines**, and **37 of the 60 outcomes changed**:

| Input | Before | After |
|---|---|---|
| 19 binary files | *"doesn't look like a plain text CSV"* | **Named:** *"this is a PNG image, not a CSV file"* (also JPEG, GIF, BMP, WAV, MP3, MP4, PDF, SQLite, exe, Parquet, pickle, zip, gzip, xls, docx). Excel adds *"open it in Excel and use Save As > CSV"* |
| `data.json`, `data.ndjson`, `data.xml`, `table.html`, `drawing.svg`, `table.md`, `dump.sql`, `plain_text.pdf` | Scored; 5 got "Case closed" | **Refused by name:** *"this looks like JSON data / XML or HTML markup / an SQL script / a Markdown table, not a CSV table"*, *"this is a PDF document"* |
| `images_base64_large.csv` (200 KB cell) | Whole file refused | **Loads:** 100, Case closed |
| `scientific_and_special.csv` | Bad values hidden in a "text" column | SUSPECTS: **`40 not numbers`**, e.g. `-inf`, `1e400`, `0x1F` |
| `mixed_encodings.csv` | `JosÃ©`, `SÃ£o Paulo`, no warning | **`José`, `São Paulo`**, encoding `utf-8 + cp1252`, with a WARNING |
| `settings.ini`, `server.log`, `fixed_width.txt`, `config.yaml`, `email.eml` | Scored silently | Still scored, but now with a WARNING: *"no delimiter was found … this file may not be a CSV table"* |
| Case board with ≥100,000 rows | Columns pushed out of line | Aligned |
| A file too big for memory | Traceback (`MemoryError`) | *"too large for this computer's memory"*. Tested by simulating the error; a real out-of-memory file wasn't created |

**Still not recognised:**
- `story.txt`: prose split at its commas, 70.
- `source_code.py`: 51.
- `settings.ini`, `server.log` and `fixed_width.txt` can still be "Case closed", but with a warning.

**Known limitations, unchanged (issue 8):**
- Decimal commas, `$`, `%` and `-999` codes aren't understood.
- Leading-zero IDs are profiled as numbers.
- Memory use is still about 30× the file size.

The sections below record the original findings, **before the fixes**.

## Headline (before the fixes)

- **The program never crashed.** Across all 60 scenarios and the mixed Investigate ALL run: 0 crashes, 0 tracebacks, 0 hangs, and every run exited with code 0 and the goodbye message.
- **No line of the program's own text was wider than 64 characters.**
- **25 inputs were refused politely** with a reason. **35 were loaded and scored.**

The problems are about **what it agrees to judge**, not about crashing:

| Group | Scenarios | How the program reacts |
|---|---|---|
| Binary files: images, audio, video, Office, archives, databases, programs | 19 | ✅ All refused: *"doesn't look like a plain text CSV"* (in under 0.03 s). The message doesn't say what the file actually is |
| A folder of images | 1 | ✅ *"'…\image_folder' is a folder, not a file"* |
| Text that isn't a table: JSON, XML/HTML/SVG, a plain-text PDF, logs, prose, code | 15 | ⚠️ **Accepted and scored as if it were a table.** 8 of them got *"Case closed – ready for analysis"* |
| Empty files, or text with one enormous line | 4 | ✅ Refused: *"file is empty"*, *"header but no data rows"* or *"field larger than field limit"* |
| Image data stored as CSV (metadata, pixels, base64) | 4 | ✅ Three handled. ⚠️ One with a 200 KB cell is refused as a whole |
| Number-only and oddly formatted numbers | 8 | ✅ / ⚠️ Matrices, huge values and overflow are handled. Decimal commas, `$`, `%` and `-999` codes aren't understood |
| Large, messy, realistic CSVs (up to 1,000,000 rows) | 9 | ✅ Correct findings. ⚠️ Mixed encodings get garbled; 1M rows needs about 700 MB of memory |

---

## 1. Images and media

| Scenario | What happened |
|---|---|
| `photo.png` (real PNG) | ✅ Refused: doesn't look like a plain text CSV |
| `photo_renamed.csv` (PNG renamed .csv) | ✅ Refused, same message. On the case board it's listed as "Could not open" |
| `photo.jpg`, `pixel.gif`, `bitmap.bmp` | ✅ Refused, same message |
| `tone.wav` (real audio), `song.mp3`, `clip.mp4` | ✅ Refused, same message |
| `image_folder/` (5 PNGs, path given at `P`) | ✅ *"…is a folder, not a file"* |
| `drawing.svg` (SVG is XML **text**) | ⚠️ Loaded as a 3-row × 1-column table and scored 70, "Needs cleaning" |
| `image_metadata.csv` (300 rows describing images) | ✅ 90, "Minor clean-up". Finds the 5.2% missing labels |
| `mnist_like_pixels.csv` (400 images × 784 pixel columns) | ✅ 100, in 0.4 s. All 785 columns are numeric, but the report is **1,594 lines long** |
| `images_base64_small.csv` (thumbnails as base64 text) | ✅ 100. Long base64 values are cut short in the report |
| `images_base64_large.csv` (one 200 KB image in a cell) | ⚠️ **The whole file is refused:** *"couldn't be read as CSV: field larger than field limit (131072)"* |

**Why binary files are refused:** images, audio, Office files and archives all contain zero bytes (`\x00`), which plain text never has. The program checks for them before parsing anything.

**Investigate ALL with images in `datasets/`:** files that don't end in `.csv` (`.png`, `.jpg`, `.wav`, `.xlsx`, `.json`, …) are skipped silently, as is the image folder. Only renamed binaries show up, as "Could not open".

## 2. Documents, archives, databases and programs

| Scenario | What happened |
|---|---|
| `workbook.xlsx`, `workbook_renamed.csv`, `old_excel.xls` | ✅ Refused: doesn't look like a plain text CSV |
| `report.docx`, `archive.zip`, `data.csv.gz` | ✅ Refused, same message |
| `compressed.pdf` (a normal PDF) | ✅ Refused, same message |
| `database.sqlite`, `program.exe` (a copy of python.exe), `data.pkl`, `table.parquet` | ✅ Refused, same message |
| `plain_text.pdf` (a PDF written entirely in ASCII) | ⚠️ Loaded as a 5 × 1 table, **100, "Case closed"** |

The most likely mistake a marker makes is opening an **Excel workbook** instead of a CSV. That is handled safely, but the message doesn't tell them to use *Save As → CSV*.

## 3. Text that isn't a CSV

| Scenario | Read as | Verdict |
|---|---|---|
| `data.json` (JSON array) | 541 × 1, trailing commas ignored | 70, Needs cleaning (355 "duplicate" `},` lines) |
| `data.ndjson` (JSON Lines) | 59 × **5**, split on the commas inside each object | ⚠️ **100, Case closed** |
| `data.xml`, `table.html` | 62 × 1 | ⚠️ **100, Case closed** |
| `table.md` (Markdown table) | 61 × 4, `\|` detected as the delimiter | 58, Unreliable (empty edge columns, a `-----` row) |
| `config.yaml`, `email.eml` | 4–6 × 1 | 70, Needs cleaning |
| `settings.ini`, `server.log`, `fixed_width.txt`, `dump.sql` | 4–499 × 1–2 | ⚠️ **100, Case closed** |
| `story.txt` (English prose) | 14 × 6, split at the commas in sentences | 70, Needs cleaning |
| `source_code.py` (the app's own `main.py`) | 225 × 1, 55 malformed rows | 51, Unreliable |
| `minified.js` (one 60 KB line) | n/a | ✅ Refused: file has a header but no data rows |
| `base64_blob.txt` (one 300 KB line) | n/a | ✅ Refused: field larger than field limit |
| `whitespace_only.txt`, `bom_only.csv` | n/a | ✅ Refused: file is empty |

Here's what the program shows for the JSON Lines file. It's polite, but wrong:
```text
[EVIDENCE]
  59 rows x 5 columns  (delimiter ',')
[SUSPECTS]  columns with problems
  No suspects - every column checks out.
[COLUMN PROFILES]
  {"id": 0      text       0.0% missing
                59 unique, most common '{"id": 1' (1)
VERDICT: 100/100  -  Case closed - ready for analysis
```
**Why:** any text file is a valid "CSV" to Python's `csv` module, because a line with no commas is simply a one-column row. The program checks *encoding* and *structure*, but never asks *"is this actually a table?"*.

## 4. Numbers

| Scenario | What happened |
|---|---|
| `matrix_no_header.csv` (100 × 10 numbers) | ✅ WARNING: *"most column names look like numbers, so the file may have no header row"*. 99 rows, because the first is used as the header |
| `ids_with_leading_zeros.csv` (IDs, postcodes, phone numbers) | ⚠️ 100. All 4 columns count as **numeric**, so it reports a mean and median of customer IDs and phone numbers, which mean nothing, and leading zeros are lost in the stats |
| `european_decimals.csv` (`;`, `3,14`, BOM, CRLF) | ⚠️ 100. All 4 columns count as **text**. Decimal-comma numbers aren't recognised, so nothing is checked |
| `currency_percent.csv` (`$1,200.50`, `45%`, `(300)`) | ⚠️ 100. All columns count as **text**, so nothing is checked |
| `scientific_and_special.csv` (`1.2e-5`, `inf`, `NaN`, `1e400`, `0x1F`) | ⚠️ 56. **About 31% of the values aren't valid numbers, so the column flips to "text" and none of them is flagged as invalid** (see below) |
| `dates_times_booleans.csv` | ✅ 100. Dates and booleans are profiled as text; only `rating` is numeric |
| `huge_numbers.csv` (`1e308`, 30-digit integers) | ✅ Handled, numeric. `1e400` overflows to infinity and counts as invalid |
| `sentinel_values.csv` (`-999` means "missing") | ⚠️ 47. `-999` isn't recognised as missing; it shows up as the column minimum |

The column-flip problem:
```text
[SUSPECTS]  columns with problems
  measurement   text     10 missing        <- the 40 bad numbers aren't flagged
[COLUMN PROFILES]
  measurement   text       7.1% missing
                13 unique, most common '1.2e-5' (10)
```
A column counts as numeric only when at least 80% of its filled values are numbers (spec §5.1). So the more broken a numeric column is, the *less* the program reports about it.

## 5. Large, messy, realistic CSVs

| Scenario | Result | Time |
|---|---|---|
| `ecommerce_100k.csv`: 100,000 orders, multiline reviews, emoji, Chinese, Arabic, Hindi, JSON in cells, about 1% duplicates, ragged rows | ✅ 101,200 × 12. Found **999 duplicates**, **201 malformed rows**, **6,249 invalid numbers** (`$12.50`, `two`) and 7.3% missing. 82, Needs cleaning | 3.5 s |
| `survey_multilingual.csv`: 3,000 answers in 6 languages | ✅ 65, Unreliable (17.7% missing) | 0.04 s |
| `concatenated_exports.csv`: header repeated mid-file | ✅ The repeated headers show up as invalid numbers (`id`, `amount`), with 101 duplicates. 68 | 0.01 s |
| `mixed_encodings.csv`: UTF-8 and Windows lines together | ⚠️ Read as cp1252, so **the UTF-8 half comes out garbled** (`JosÃ©`, `SÃ£o Paulo`) with no warning. 100 | 0.01 s |
| `wide_1000_columns.csv`: 1,000 columns | ✅ 60. The report is **3,023 lines long** | 0.24 s |
| `sparse_90_percent_empty.csv` | ✅ 60, Unreliable (67% missing) | 0.01 s |
| `all_rows_identical.csv`: 500 copies of one row | ✅ 499 duplicates, 70 | 0.01 s |
| `tab_separated_named_csv.csv` | ✅ Tab delimiter detected, 100 | 0.02 s |
| `huge_1m_rows.csv`: 1,000,000 rows (23.6 MB) | ✅ 90, Minor clean-up. **Peak memory about 700 MB** | **18.5 s** (17.6 s on 3.11) |

## Investigate ALL over the mixed folder

All 60 scenarios were copied into `datasets/`, then option 5 was chosen:
- 20 `.csv` files were ranked.
- 4 were listed as "Could not open", each with its reason.
- Every non-`.csv` file and the image folder were ignored.

There was no traceback. One display bug showed up:
```text
  9     tab_separated_named_.. 1,000    100  Case closed
  10    huge_1m_rows.csv      1,000,000     90  Minor clean-up   <- columns pushed out of line
  12    ecommerce_100k.csv    101,200     82  Needs cleaning
```
The Rows column is 6 characters wide, so counts of 100,000 or more push the Score and Verdict to the right.

## Speed and memory

| File | Size | Investigate | Peak memory |
|---|---|---|---|
| 1,000 columns × 200 rows | 0.4 MB | 0.24 s | 29 MB |
| 100,000 rows × 12 messy columns | 13.8 MB | 3.5 s | 231 MB |
| 1,000,000 rows × 5 columns | 23.6 MB | 18.5 s | 702 MB |

Time grows roughly in line with file size. Memory is about **17–30 times the file size**, because every cell becomes its own Python string. A file of a few hundred MB could run out of memory, and a `MemoryError` is not caught, so it would end in a traceback.

---

## What should be improved, most important first

| # | Problem | Effect on a marker | Fix | Status |
|---|---|---|---|---|
| 1 | **Bug:** the board's Rows column is too narrow for ≥100,000 rows | Misaligned leaderboard | Widen the column (now 10 characters, still within 64) | ✅ Fixed |
| 2 | Non-table text (JSON, XML/HTML/SVG, plain-text PDF, logs, prose) is investigated and can get "Case closed" | Looks naive if a marker tries a `.json` or `.html` file | Recognise these formats and refuse them by name. Warn when no delimiter is found | ✅ Fixed (prose and logs only get a warning) |
| 3 | Binary files get one generic message | Fine, but unhelpful for Excel | Name the format from its first bytes | ✅ Fixed |
| 4 | Cells over 131,072 characters make the whole file unreadable | Real image-in-CSV datasets are refused | Raise the csv module's `field_size_limit` | ✅ Fixed |
| 5 | Columns that are 50–79% numbers flip to "text" and hide their bad values | Wrong "no suspects" | List them as *"N not numbers"* in SUSPECTS | ✅ Fixed (the score is unchanged) |
| 6 | Files mixing UTF-8 and Windows lines are garbled silently | Mojibake in the report | Decode line by line, and warn | ✅ Fixed |
| 7 | Very large files: about 17–30× memory, and an uncaught `MemoryError` | A traceback on a huge file | Catch `MemoryError` with a friendly message | ✅ Fixed (memory use not reduced) |
| 8 | Decimal commas, `$`, `%` and `-999` codes aren't understood | Some numeric columns are judged as text | Document as known limitations, or recognise them | ⏸ Not changed |
