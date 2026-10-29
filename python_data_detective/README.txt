PYTHON DATA DETECTIVE
=====================

Python Data Detective is a terminal program that investigates the
quality of a CSV dataset before you analyse it. It finds missing values,
duplicate rows, invalid numbers and badly shaped rows, profiles every
column, scores the dataset out of 100 and saves a detective-themed case
report. It is made for students and beginner data analysts who want a
quick, plain-language answer to "is this data ready to use?".


HOW TO RUN
----------
    python main.py          (Windows)
    python3 main.py         (Ed, macOS, Linux)

Run it from inside this folder, or from anywhere with the full path, for
example  python python_data_detective/main.py . The program finds its
datasets/ and reports/ folders by itself.

Menu options:
    1  Open a case            choose a dataset from datasets/, or type
                              (or paste) the path to any CSV file
    2  Inspect the evidence   size, delimiter, encoding, columns, preview
    3  Run the investigation  the full case report and quality score
    4  Save the case report   writes reports/<dataset>_report.txt
    5  Investigate ALL        ranks every dataset on a CASE BOARD and can
                              save every report plus reports/leaderboard.txt
    0  Close the office       quit (Ctrl+C also quits cleanly)


WEB UI (OPTIONAL)
-----------------
The same detective also has a web page, for demonstrations:

    python web_app.py                 (python3 web_app.py on macOS, Linux)
    python web_app.py --no-browser    (just print the address)

It starts a small web server on this computer only (localhost, port
8000, or the next free port up to 8010) and opens the page in your
browser. Press Ctrl+C in the terminal to stop it. Every menu option is
there: the evidence locker (or drop in any file), the evidence, the
findings and score, saving or downloading the report, and the case
board with Save all. Saved reports go to the same reports/ folder.

It needs a normal Python install on your own computer: Ed can't run it,
because it uses networking. The terminal program (main.py) is the main
version of the project.


REQUIREMENTS
------------
Python 3.9 or newer. Only Python's standard library is used, so there
is nothing to install. The terminal program uses no graphics, audio or
network access, so it runs in Ed's terminal.


WHAT'S IN THE FOLDER
--------------------
    main.py               RUN THIS. The menu, user input and program flow.
    dataset.py            Dataset: loads a CSV file and tidies its rows.
    investigator.py       Investigator, Findings, ColumnProfile: the
                          quality checks, column profiles and scores.
    report.py             Report: all the text the user reads (case
                          report, evidence screen, leaderboard).
    errors.py             DatasetError and its subclasses.
    file_types.py         Recognises files that aren't CSVs (images,
                          Excel, PDF, JSON, HTML...) and names them.
    web_app.py            Optional web UI: runs the local web server.
    web_api.py            The web UI's JSON API, using the classes above.
    web/                  The web page: index.html, style.css, app.js.
    datasets/             9 sample CSV files (see below).
    reports/              Created the first time a report is saved.
    tools/make_datasets.py
                          Generates the AI-made datasets and prints an
                          answer key. NOT needed to run the program.
    README.txt            This file.


HOW THE SCORE WORKS
-------------------
Three sub-scores each start at 100 and lose 5 points for every 1% of the
data with that problem (never going below 0):
    Completeness  - cells that are missing (blank, NA, N/A, null, ...)
    Uniqueness    - rows that repeat an earlier row
    Validity      - non-numbers inside a numeric column (e.g. "twelve"),
                    plus rows with the wrong number of fields
Overall = 40% Completeness + 30% Uniqueness + 30% Validity, rounded.

    95-100  Case closed - ready for analysis
    85-94   Minor clean-up needed
    70-84   Significant cleaning needed
    0-69    Unreliable evidence - investigate before use

A column counts as numeric when at least 80% of its filled cells are
numbers. Rows with too many or too few fields are reported, then
trimmed or padded with blanks (the blanks count as missing).
Trailing delimiters at the ends of lines ("a,b," / "1,2,") are ignored.

The program reads UTF-8, UTF-16, Windows cp1252 and latin-1 files, and
files that mix UTF-8 and cp1252 lines. It warns about a quote that is
never closed, a header row that looks like data (a file with no header),
a title line above the header, and a file with no delimiter at all. A
text column that is mostly numbers has its non-numbers listed.

Files that aren't CSVs are refused by name instead of being misread:
images (PNG, JPEG, GIF, BMP), audio and video, Excel and Word files,
zip/gzip archives, PDFs, databases, programs, JSON, XML/HTML, SQL
scripts and Markdown tables. Excel users are told to use Save As > CSV.
A file too big for the computer's memory gives a message, not a crash.


DATASETS AND SOURCES
--------------------
Real public datasets:
    1. iris.csv
       Fisher, R. A. (1936). Iris [Dataset]. UCI Machine Learning
       Repository. https://doi.org/10.24432/C56C76
       Licence: CC BY 4.0. A header row was added; the data is
       otherwise unchanged. (It really does contain 3 duplicate rows.)
    2. penguins.csv
       Horst, A. M., Hill, A. P., & Gorman, K. B. (2020). palmerpenguins:
       Palmer Archipelago (Antarctica) penguin data.
       https://allisonhorst.github.io/palmerpenguins/
       Licence: CC0 (public domain). Data collected by Dr. Kristen Gorman
       and the Palmer Station Long Term Ecological Research Network.

AI-generated datasets (made by tools/make_datasets.py, fixed seed 9001):
    3. student_grades.csv      nearly clean: 4 blanks, 1 duplicate
    4. messy_sales.csv         every missing marker, invalid numbers,
                               duplicates, blank lines, Windows line endings
    5. tricky_addresses.csv    ';' delimiter, Excel BOM, commas and line
                               breaks inside quoted values
    6. old_export_latin1.csv   saved as latin-1 instead of UTF-8
    7. broken_rows.csv         ragged rows, many duplicates, a blank
                               column name
    8. empty.csv               an empty file (shows a friendly error)
    9. not_really_a_csv.csv    binary data renamed .csv (friendly error)


AI USE ACKNOWLEDGEMENT
----------------------
[DRAFT - check this wording against the COMP9001 / University of Sydney
AI policy before submitting, and edit it to describe your own work.]

This project was built with the help of Claude (Anthropic), an AI
assistant. Claude helped to plan the design, write and test the Python
code (including tools/make_datasets.py), and draft this README. Datasets
3 to 9 listed above are AI-generated: they were created by
tools/make_datasets.py, which was written with Claude's help.


CONCEPTS BEYOND THE LECTURES
----------------------------
    csv module (reader, writer, Sniffer)  - parses quoted commas and line
                                            breaks; detects , ; tab |
    io.StringIO                           - parse text already in memory
    with open(..., "rb") and bytes.decode - safe file handling; UTF-8
                                            (and Excel's BOM), UTF-16,
                                            cp1252 and latin-1
    codecs (BOM constants)                - recognise UTF-16 files
    textwrap                              - wrap long messages to fit
    json                                  - recognise JSON files
    "Magic numbers" (bytes.startswith)    - recognise images, Excel...
    csv.field_size_limit                  - allow very large cells
    Custom exceptions via inheritance     - DatasetError and subclasses
    Tuples as dict keys                   - fast duplicate-row detection
    collections.Counter                   - most common value in a column
    statistics (mean, median)             - column profile numbers
    math.isfinite                         - rejects 'inf' as a number
    datetime and strftime                 - case number and timestamp
    sorted(..., key=lambda ...)           - leaderboard ranking
    enumerate, zip                        - line numbers, value pairing
    f-string format specs (:<14 :.1f :,)  - aligned, readable tables
    __file__, os.path, os.makedirs        - folders found from the script
    @staticmethod decorator               - helpers that don't need self
    typing.Optional                       - "a Dataset or None" type hints
    List comprehensions                   - only where they read clearly
    random.Random (tools only)            - reproducible generated data
    http.server (ThreadingHTTPServer)     - the web UI's local server
    threading.Lock                        - one request at a time
    urllib.parse, tempfile, shutil        - URLs, upload folder clean-up
    webbrowser                            - opens the page for you
    HTML, CSS and JavaScript (web/)       - the web page itself
