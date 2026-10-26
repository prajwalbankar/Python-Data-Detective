"""Generate the AI-made sample datasets and print their answer key.

Written with AI assistance (Claude, by Anthropic); see the README's AI
use acknowledgement. This script is NOT needed to run Python Data
Detective, because the files it makes are already in datasets/. To make
them again, run:  python tools/make_datasets.py

Every number in the answer key comes from what this script deliberately
put into each file (missing values, invalid numbers, duplicate rows and
so on), so the app's findings can be checked against a known truth.
"""
import csv
import io
import os
import random

SEED = 9001
HERE = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(os.path.dirname(HERE), "datasets")

# Every spelling of "missing" the app should recognise.
MISSING_MARKERS = ["", "NA", "N/A", "null", "None", "nan", "-", "?"]
FIRST_NAMES = ["Ava", "Noah", "Mia", "Leo", "Zara", "Ethan", "Isla",
               "Liam", "Chloe", "Arjun", "Mei", "Oscar", "Priya", "Sam"]
LAST_NAMES = ["Nguyen", "Smith", "Patel", "Chen", "Brown", "Wilson",
              "Kumar", "Taylor", "Lee", "Martin", "Singh", "White"]


# ---------------------------------------------------------------- helpers

def to_csv_line(fields: list[str], delimiter: str, terminator: str) -> str:
    """Return one row as CSV text, quoted where the csv module needs."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter,
                        lineterminator=terminator)
    writer.writerow(fields)
    return buffer.getvalue()


def render(header: list[str], rows: list[list[str]], delimiter: str = ",",
           terminator: str = "\n",
           blank_after: tuple = ()) -> tuple[str, list[int]]:
    """Turn rows into CSV text and return (text, start line of each row).

    blank_after lists data-row counts after which a blank line is added.
    """
    text = to_csv_line(header, delimiter, terminator)
    line = 1 + text.count("\n")
    start_lines = []
    for number, row in enumerate(rows, start=1):
        piece = to_csv_line(row, delimiter, terminator)
        start_lines.append(line)
        text += piece
        line += piece.count("\n")  # a quoted value can hold line breaks
        if number in blank_after:
            text += terminator
            line += 1
    return text, start_lines


def pick_cells(rng: random.Random, row_indexes: list[int],
               columns: list[int], count: int,
               taken: set) -> list[tuple[int, int]]:
    """Choose count distinct (row, column) cells not already taken."""
    free = []
    for row in row_indexes:
        for column in columns:
            if (row, column) not in taken:
                free.append((row, column))
    chosen = rng.sample(free, count)
    taken.update(chosen)
    return chosen


def position_of(rows: list[list[str]], target: list[str]) -> int:
    """Return where target sits in rows, matching the object itself."""
    for position, row in enumerate(rows):
        if row is target:
            return position
    raise ValueError("row not found")


def add_duplicates(rng: random.Random, rows: list[list[str]],
                   sources: list[list[str]],
                   count: int) -> list[tuple[list[str], list[str]]]:
    """Insert count copies of source rows, each after its source.

    Returns (copy, source) pairs so their lines can be found later.
    """
    pairs = []
    for _ in range(count):
        source = rng.choice(sources)
        position = rng.randint(position_of(rows, source) + 1, len(rows))
        copy = list(source)
        rows.insert(position, copy)
        pairs.append((copy, source))
    return pairs


def duplicate_lines(rows: list[list[str]], start_lines: list[int],
                    pairs: list[tuple[list[str], list[str]]]
                    ) -> list[tuple[int, int]]:
    """Return (copy line, original line) for each copy, in file order."""
    lines = []
    for copy, source in pairs:
        lines.append((start_lines[position_of(rows, copy)],
                      start_lines[position_of(rows, source)]))
    return sorted(lines)


def answer(rows: list[list[str]], header: list[str], delimiter: str,
           encoding: str, missing: int, invalid: int, duplicates: int,
           malformed: int = 0, blank_lines: int = 0) -> dict:
    """Build one answer-key entry from the injected counts."""
    return {"rows": len(rows), "columns": len(header),
            "delimiter": delimiter, "encoding": encoding,
            "missing": missing, "invalid": invalid,
            "duplicates": duplicates, "malformed": malformed,
            "blank_lines": blank_lines}


def random_name(rng: random.Random) -> str:
    """Return a random 'First Last' name."""
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def grade_for(total: float) -> str:
    """Return the USyd-style grade for a mark out of 100."""
    if total >= 85:
        return "HD"
    elif total >= 75:
        return "D"
    elif total >= 65:
        return "CR"
    elif total >= 50:
        return "P"
    return "F"


# --------------------------------------------------------------- datasets

def student_grades(rng: random.Random) -> tuple[str, str, dict]:
    """Nearly clean: 4 blank cells and 1 duplicate row."""
    header = ["student_id", "name", "tutorial", "assignment", "exam",
              "final_grade"]
    rows = []
    for number in range(1, 120):
        assignment = rng.randint(40, 100)
        exam = rng.randint(30, 100)
        rows.append([f"S{number:03d}", random_name(rng),
                     f"T{rng.randint(1, 8):02d}", str(assignment),
                     str(exam), grade_for((assignment + exam) / 2)])

    taken = set()
    all_rows = list(range(len(rows)))
    blanks = (pick_cells(rng, all_rows, [3], 2, taken)
              + pick_cells(rng, all_rows, [4], 1, taken)
              + pick_cells(rng, all_rows, [2], 1, taken))
    for row, column in blanks:
        rows[row][column] = ""

    dirty = {row for row, column in taken}
    clean = [rows[i] for i in all_rows if i not in dirty]
    add_duplicates(rng, rows, clean, 1)

    text, _ = render(header, rows)
    return text, "utf-8", answer(rows, header, ",", "utf-8",
                                 missing=4, invalid=0, duplicates=1)


def messy_sales(rng: random.Random) -> tuple[str, str, dict]:
    """Every missing marker, invalid numbers, duplicates, CRLF, blanks."""
    header = ["order_id", "region", "product", "price", "qty", "rating"]
    products = ["Desk lamp", "Notebook", "USB cable", "Mug", "Backpack",
                "Headphones", "Stapler", "Water bottle"]
    rows = []
    for number in range(1, 191):
        rows.append([str(number),
                     rng.choice(["North", "South", "East", "West"]),
                     rng.choice(products),
                     f"{rng.uniform(2.5, 89.0):.2f}",
                     str(rng.randint(1, 20)), str(rng.randint(1, 5))])

    taken = set()
    all_rows = list(range(len(rows)))
    missing_cells = pick_cells(rng, all_rows, [1, 3, 4, 5], 40, taken)
    for (row, column), marker in zip(missing_cells, MISSING_MARKERS * 5):
        rows[row][column] = marker
    bad_prices = ["twelve", "$15", "1,204", "15.00 AUD"] * 2
    for (row, column), value in zip(
            pick_cells(rng, all_rows, [3], 8, taken), bad_prices):
        rows[row][column] = value
    bad_ratings = ["5 stars", "four", "**", "N.A."] * 2
    for (row, column), value in zip(
            pick_cells(rng, all_rows, [5], 8, taken), bad_ratings):
        rows[row][column] = value

    dirty = {row for row, column in taken}
    clean = [rows[i] for i in all_rows if i not in dirty]
    pairs = add_duplicates(rng, rows, clean, 10)

    text, start_lines = render(header, rows, terminator="\r\n",
                               blank_after=(50, 120))
    key = answer(rows, header, ",", "utf-8", missing=40, invalid=16,
                 duplicates=10, blank_lines=2)
    key["duplicate_lines"] = duplicate_lines(rows, start_lines, pairs)
    return text, "utf-8", key


def tricky_addresses(rng: random.Random) -> tuple[str, str, dict]:
    """Semicolons, a BOM, commas and line breaks inside values."""
    header = ["id", "name", "address", "city", "postcode", "notes"]
    streets = ["George St", "King St", "Pitt St", "Oxford St", "Crown St",
               "Bourke St", "Queen St", "Hay St"]
    cities = [("Sydney", "2000"), ("Melbourne", "3000"),
              ("Brisbane", "4000"), ("Perth", "6000"),
              ("Adelaide", "5000"), ("Darwin", "0800")]
    notes = ["Leave at door", "Call on arrival", "Fragile",
             "Back entrance", "Ring twice"]
    rows = []
    for number in range(1, 79):
        street = f"{rng.randint(1, 300)} {rng.choice(streets)}"
        commas = rng.choice([0, 1, 2])  # varies so ',' never looks
        if commas >= 1:                 # like the delimiter
            street = f"Unit {rng.randint(1, 40)}, {street}"
        if commas == 2:
            street = f"{street}, Rear"
        city, postcode = rng.choice(cities)
        rows.append([str(number), random_name(rng), street, city,
                     postcode, rng.choice(notes)])

    # Names containing ';' get quoted, which lets the Sniffer spot ';'.
    rows[1][1] = "Smith; Jones & Co"
    rows[5][1] = "Lee; Park Pty Ltd"
    note_rows = [12, 33, 57]
    for row in note_rows:
        rows[row][5] = "Call first\nGate code 1234"
    blank_rows = rng.sample([i for i in range(len(rows))
                             if i not in note_rows and i not in (1, 5)], 3)
    for row in blank_rows:
        rows[row][5] = ""

    special = set(note_rows) | set(blank_rows) | {1, 5}
    after_break = [rows[i] for i in range(note_rows[0] + 1, len(rows))
                   if i not in special]
    anywhere = [rows[i] for i in range(len(rows)) if i not in special]
    pairs = (add_duplicates(rng, rows, after_break, 1)
             + add_duplicates(rng, rows, anywhere, 1))

    text, start_lines = render(header, rows, delimiter=";")
    key = answer(rows, header, ";", "utf-8", missing=3, invalid=0,
                 duplicates=2)
    key["duplicate_lines"] = duplicate_lines(rows, start_lines, pairs)
    return text, "utf-8-sig", key


def old_export_latin1(rng: random.Random) -> tuple[str, str, dict]:
    """An old export saved as latin-1 instead of UTF-8."""
    header = ["customer_id", "name", "city", "spend"]
    names = ["José Álvarez", "Zoë Martin", "Jürgen Müller", "Renée Dubois",
             "Ana Simões", "Björn Larsen", "Chloé Bernard", "Andrés Peña"]
    cities = ["São Paulo", "Montréal", "Zürich", "Köln", "Málaga",
              "Göteborg"]
    rows = []
    for number in range(1, 31):
        rows.append([f"C{number:03d}", rng.choice(names),
                     rng.choice(cities), f"{rng.uniform(5, 500):.2f}"])
    taken = set()
    all_rows = list(range(len(rows)))
    for row, column in pick_cells(rng, all_rows, [2], 2, taken):
        rows[row][column] = ""
    for row, column in pick_cells(rng, all_rows, [3], 1, taken):
        rows[row][column] = "abc"

    text, _ = render(header, rows)
    return text, "latin-1", answer(rows, header, ",", "latin-1",
                                   missing=2, invalid=1, duplicates=0)


def broken_rows(rng: random.Random) -> tuple[str, str, dict]:
    """Ragged rows, many duplicates and a blank column name."""
    header = ["sensor_id", "", "reading", "unit", "status"]
    rows = []
    for number in range(1, 46):
        rows.append([f"S{number:03d}",
                     rng.choice(["Lab A", "Lab B", "Roof", "Basement"]),
                     f"{rng.uniform(15, 35):.1f}", "C",
                     rng.choice(["ok", "ok", "ok", "warn"])])

    order = list(range(len(rows)))
    rng.shuffle(order)
    long_rows, short_rows = order[:6], order[6:11]
    dirty_rows, clean_rows = order[11:31], order[31:]

    taken = set()
    for row, column in pick_cells(rng, dirty_rows, [2], 5, taken):
        rows[row][column] = rng.choice(MISSING_MARKERS)
    for row, column in pick_cells(rng, dirty_rows, [1, 3, 4], 25, taken):
        rows[row][column] = rng.choice(MISSING_MARKERS)
    bad_readings = ["ERR", "--", "high"] * 2
    for (row, column), value in zip(
            pick_cells(rng, dirty_rows, [2], 6, taken), bad_readings):
        rows[row][column] = value

    long_targets = [rows[i] for i in long_rows]
    short_targets = [rows[i] for i in short_rows]
    add_duplicates(rng, rows, [rows[i] for i in clean_rows], 15)
    for row in long_targets:
        row.append("EXTRA")       # one field too many
    for row in short_targets:
        del row[3:]               # keeps sensor_id, location, reading

    text, _ = render(header, rows)
    padded = 2 * len(short_rows)
    return text, "utf-8", answer(rows, header, ",", "utf-8",
                                 missing=30 + padded, invalid=6,
                                 duplicates=15, malformed=11)


# ------------------------------------------------------------ build / main

def build_datasets(folder: str) -> dict[str, dict]:
    """Write every generated file into folder and return the answer key."""
    os.makedirs(folder, exist_ok=True)
    rng = random.Random(SEED)
    key = {}
    builders = [("student_grades.csv", student_grades),
                ("messy_sales.csv", messy_sales),
                ("tricky_addresses.csv", tricky_addresses),
                ("old_export_latin1.csv", old_export_latin1),
                ("broken_rows.csv", broken_rows)]
    for name, builder in builders:
        text, encoding, entry = builder(rng)
        with open(os.path.join(folder, name), "w", encoding=encoding,
                  newline="") as file:
            file.write(text)
        key[name] = entry

    with open(os.path.join(folder, "empty.csv"), "wb") as file:
        file.write(b"")
    key["empty.csv"] = {"error": "EmptyDatasetError"}

    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + rng.randbytes(64)
    with open(os.path.join(folder, "not_really_a_csv.csv"), "wb") as file:
        file.write(fake_png)
    key["not_really_a_csv.csv"] = {"error": "UnreadableFileError"}
    return key


def main() -> None:
    """Generate the datasets into datasets/ and print the answer key."""
    key = build_datasets(DATASETS_DIR)
    print(f"Wrote {len(key)} files to {DATASETS_DIR}\n")
    print("ANSWER KEY")
    for name, entry in key.items():
        print(f"  {name}")
        for field, value in entry.items():
            print(f"      {field}: {value}")


if __name__ == "__main__":
    main()
