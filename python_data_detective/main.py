# RUN THIS FILE: python main.py  (Python Data Detective)
"""Python Data Detective: the menu-driven case desk.

Open a CSV file, inspect it, investigate its data quality and save a
detective-themed report. Start the program with:

    python main.py        (or python3 main.py on Ed or macOS)

This file only handles the menu, the user's input and the program's
flow. The other modules do the real work:
    dataset.py       loads and tidies a CSV file
    investigator.py  checks its quality and scores it
    report.py        formats everything the user reads
    errors.py        the program's own exception types
"""
import os
import sys
from typing import Optional

from dataset import Dataset
from errors import DatasetError
from investigator import Findings, Investigator
from report import DELIMITER_NAMES, WIDTH, Report, shorten

# Folders are found from this file's location, so the program works
# whichever folder it is started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

MENU = [("1", "Open a case", "choose a dataset"),
        ("2", "Inspect the evidence", "size, columns, preview"),
        ("3", "Run the investigation", "quality checks + score"),
        ("4", "Save the case report", "writes a .txt file"),
        ("5", "Investigate ALL", "leaderboard of every dataset"),
        ("0", "Close the office", "quit")]


def list_csv_files(folder: str) -> list[str]:
    """Return the names of the CSV files in folder, alphabetically."""
    if not os.path.isdir(folder):
        return []
    names = []
    for name in os.listdir(folder):
        is_file = os.path.isfile(os.path.join(folder, name))
        if is_file and name.lower().endswith(".csv"):
            names.append(name)
    return sorted(names, key=str.lower)


def ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question until the user answers y or n."""
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please enter y or n")


def clean_path(text: str) -> str:
    """Strip spaces and one pair of quotes from a typed or pasted path."""
    path = text.strip()
    # Windows "Copy as path" wraps the path in double quotes.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in "\"'":
        path = path[1:-1]
    return path


def open_case(path: str) -> Optional[Dataset]:
    """Load the dataset at path, or explain why it couldn't be opened."""
    try:
        dataset = Dataset(path)
    except DatasetError as err:
        print(f"Could not open case: {err}")
        return None
    details = (f"({dataset.num_rows():,} rows x {dataset.num_columns():,} "
               f"columns, delimiter {DELIMITER_NAMES[dataset.delimiter]})")
    line = f"Opening case... {dataset.name} {details}"
    if len(line) <= WIDTH:
        print(line)
    else:
        print(f"Opening case... {shorten(dataset.name, WIDTH - 16)}")
        print("  " + details)
    return dataset


def choose_dataset() -> Optional[Dataset]:
    """Let the user pick a dataset from datasets/ or type a path."""
    files = list_csv_files(DATASETS_DIR)
    print()
    print("EVIDENCE LOCKER  (datasets/)")
    if not files:
        print("  The evidence locker is empty")
    for number, name in enumerate(files, start=1):
        print(f"  {number}. {shorten(name, WIDTH - 6)}")
    print("  P. Enter another file path")
    print("  B. Back")

    while True:
        choice = input("Choose a dataset: ").strip().upper()
        if choice == "B":
            return None
        if choice == "P":
            return open_case(clean_path(input("Path to a CSV file: ")))
        # isdecimal, not isdigit: '²' is a "digit" that int() rejects.
        if choice.isdecimal() and 1 <= int(choice) <= len(files):
            return open_case(os.path.join(DATASETS_DIR,
                                          files[int(choice) - 1]))
        if files:
            print(f"Please enter a number from 1 to {len(files)}, P or B")
        else:
            print("Please enter P or B")


def show_menu(current: Optional[Dataset]) -> None:
    """Print the main menu with the case that is currently open."""
    case = "none" if current is None else str(current)
    print()
    print("=" * WIDTH)
    print("PYTHON DATA DETECTIVE  -  Case Desk".center(WIDTH).rstrip())
    print("=" * WIDTH)
    print(f"  Current case: {shorten(case, WIDTH - 16)}")
    print()
    for key, title, hint in MENU:
        print(f"  {key}. {title:<23}{hint}")
    print("-" * WIDTH)


def shown_path(path: str) -> str:
    """Return path relative to the program folder, for messages."""
    try:
        return os.path.relpath(path, BASE_DIR)
    except ValueError:  # on Windows, a path on another drive
        return path


def save_report(findings: Findings) -> None:
    """Save the case report into reports/ and say where it went."""
    try:
        path, replaced = Report(findings).save(REPORTS_DIR)
    except OSError as err:
        print(f"Could not save report: {err}")
        return
    print(f"Report saved to {shown_path(path)}")
    if replaced:
        print("  (replaced the previous report)")


def investigate_all() -> None:
    """Investigate every dataset in datasets/ and show the CASE BOARD."""
    files = list_csv_files(DATASETS_DIR)
    if not files:
        print("The evidence locker is empty")
        return
    findings_list = []
    failures = []   # (file name, reason) for files that couldn't open
    for name in files:
        try:
            dataset = Dataset(os.path.join(DATASETS_DIR, name))
        except DatasetError as err:
            failures.append((name, str(err)))
            continue
        findings_list.append(Investigator(dataset).investigate())

    board = Report.leaderboard_text(findings_list, failures)
    print()
    print(board, end="")
    if ask_yes_no("Save a report for every dataset? (y/n): "):
        save_all(findings_list, board)


def save_all(findings_list: list[Findings], board: str) -> None:
    """Save every case report plus the leaderboard into reports/."""
    try:
        for findings in findings_list:
            Report(findings).save(REPORTS_DIR)
        os.makedirs(REPORTS_DIR, exist_ok=True)
        with open(os.path.join(REPORTS_DIR, "leaderboard.txt"), "w",
                  encoding="utf-8") as file:
            file.write(board)
    except OSError as err:
        print(f"Could not save report: {err}")
        return
    print(f"Saved {len(findings_list)} case reports and leaderboard.txt "
          f"to {shown_path(REPORTS_DIR)}")


def handle_case_option(choice: str, current: Optional[Dataset],
                       findings: Optional[Findings]) -> Optional[Findings]:
    """Run option 2, 3 or 4 on the open case; return the findings."""
    if current is None:
        print("No case open - choose option 1 first")
        return findings
    if choice == "2":
        print()
        print(Report.evidence_text(current), end="")
    elif choice == "3":
        findings = Investigator(current).investigate()
        print()
        print(Report(findings).to_text(), end="")
    else:
        if findings is None:
            findings = Investigator(current).investigate()
        save_report(findings)
    return findings


def main() -> None:
    """Run the case desk until the user chooses to quit."""
    # If the output can't show a character from the data (e.g. Chinese
    # text with Windows output redirected to a file), print '?' instead
    # of crashing.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    current: Optional[Dataset] = None
    findings: Optional[Findings] = None
    try:
        while True:
            show_menu(current)
            choice = input("Choose an option: ").strip()
            if choice == "0":
                break
            if choice == "1":
                dataset = choose_dataset()
                if dataset is not None:
                    current = dataset
                    findings = None     # old findings belong to old case
            elif choice in ("2", "3", "4"):
                findings = handle_case_option(choice, current, findings)
            elif choice == "5":
                investigate_all()
            else:
                print("Please enter a number from 0 to 5")
    except (KeyboardInterrupt, EOFError):
        print()     # Ctrl+C or Ctrl+D: finish on a fresh line
    finally:
        print("Case closed. Goodbye, detective.")


if __name__ == "__main__":
    main()
