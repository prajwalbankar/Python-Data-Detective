"""Turn findings into the detective-themed text the user reads.

Everything the program prints about a dataset is built here, so the
terminal and the saved .txt report always show exactly the same text.
Our own text is plain ASCII and no line is wider than WIDTH characters,
so it displays properly in any terminal and on a projector.
"""
import os

from dataset import Dataset
from investigator import Findings

WIDTH = 64            # widest line we ever print
MAX_LISTED = 10       # duplicates / malformed rows listed before "... more"
CELL_WIDTH = 12       # widest cell in the evidence preview table
VALUE_WIDTH = 15      # widest data value quoted in the report
NAME_WIDTH = 14       # column-name column in SUSPECTS and PROFILES
BOARD_NAME_WIDTH = 22  # dataset-name column on the leaderboard
DETAIL_INDENT = 2 + NAME_WIDTH   # where the detail lines start
PREVIEW_ROWS = 5
DELIMITER_NAMES = {",": "','", ";": "';'", "\t": "tab", "|": "'|'"}


def shorten(text: str, width: int) -> str:
    """Cut text to width characters, ending with '..' if it was cut."""
    if len(text) <= width:
        return text
    return text[:width - 2] + ".."


def format_stat(value: float) -> str:
    """Show a number readably: '1,204', '24.1', '0.035' or '2e+300'.

    Whole numbers have no decimals, and other numbers get one decimal
    place. Very small and very large numbers use 3 significant figures
    so they don't round to 0 or print as a wall of digits.
    """
    size = abs(value)
    if size >= 1e15 or 0 < size < 0.1:
        return f"{value:.3g}"
    if value.is_integer():
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def flatten(value: str) -> str:
    """Replace line breaks inside a data value with spaces."""
    return value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def quote_value(value: str) -> str:
    """Show a data value in quotes, flattened and cut to VALUE_WIDTH."""
    return f"'{shorten(flatten(value), VALUE_WIDTH)}'"


def plural(count: int, word: str) -> str:
    """Return e.g. '1 duplicate row' or '3 duplicate rows'."""
    if count == 1:
        return f"{count:,} {word}"
    return f"{count:,} {word}s"


def wrap_parts(parts: list[str], first_prefix: str, indent: int,
               separator: str = "  ") -> list[str]:
    """Join parts into lines no wider than WIDTH.

    The first line starts with first_prefix; later lines start with
    indent spaces. A part too long for any line is shortened.
    """
    room = WIDTH - max(len(first_prefix), indent)
    lines = []
    current = first_prefix
    has_part = False
    for part in parts:
        part = shorten(part, room)
        candidate = current + (separator if has_part else "") + part
        if has_part and len(candidate) > WIDTH:
            lines.append(current)
            current = " " * indent + part
        else:
            current = candidate
        has_part = True
    lines.append(current)
    return lines


def name_column(name: str) -> str:
    """Return a column name cut and padded to NAME_WIDTH."""
    return shorten(flatten(name), NAME_WIDTH - 1).ljust(NAME_WIDTH)


def quote_warning(dataset: Dataset) -> list[str]:
    """Return the warning lines for a quote that is never closed."""
    if dataset.unclosed_quote_line is None:
        return []
    return [f"  WARNING: a quote opened on line "
            f"{dataset.unclosed_quote_line} is never closed,",
            "  so everything after it was read as a single value."]


def board_row(rank: str, name: str, rows: str, score: str,
              verdict: str) -> str:
    """Lay out one row of the leaderboard in fixed-width columns."""
    name = shorten(name, BOARD_NAME_WIDTH)
    return (f"  {rank:<4}  {name:<{BOARD_NAME_WIDTH}}"
            f"{rows:>6}{score:>7}  {verdict}")


class Report:
    """The themed case report for one investigated dataset."""

    def __init__(self, findings: Findings) -> None:
        """Prepare a report for findings."""
        self.findings = findings

    def to_text(self) -> str:
        """Return the whole case report as text."""
        lines = (self._header_lines() + self._evidence_lines()
                 + self._suspect_lines() + self._duplicate_lines()
                 + self._malformed_lines() + self._profile_lines()
                 + self._score_lines())
        return "\n".join(lines) + "\n"

    def save(self, folder: str) -> tuple[str, bool]:
        """Write the report into folder.

        Returns (path of the file, whether an older report was replaced).
        """
        os.makedirs(folder, exist_ok=True)
        base_name = os.path.splitext(self.findings.dataset.name)[0]
        path = os.path.join(folder, base_name + "_report.txt")
        replaced = os.path.exists(path)
        with open(path, "w", encoding="utf-8") as file:
            file.write(self.to_text())
        return path, replaced

    @staticmethod
    def evidence_text(dataset: Dataset) -> str:
        """Return the 'inspect the evidence' screen for a dataset."""
        lines = [f"[EVIDENCE] {shorten(dataset.name, WIDTH - 11)}",
                 f"  Rows: {dataset.num_rows():,}   "
                 f"Columns: {dataset.num_columns():,}",
                 f"  Delimiter: {DELIMITER_NAMES[dataset.delimiter]}   "
                 f"Encoding: {dataset.encoding}   "
                 f"Blank lines skipped: {dataset.blank_lines_skipped:,}"]
        lines += quote_warning(dataset)
        # Every name but the last gets a trailing comma.
        names = [flatten(name) + "," for name in dataset.header[:-1]]
        names.append(flatten(dataset.header[-1]))
        lines += wrap_parts(names, "  Columns: ", 4, separator=" ")
        lines.append("")
        lines.append(f"  Preview (first {PREVIEW_ROWS} rows):")
        lines += Report._preview_table(dataset)
        return "\n".join(lines) + "\n"

    @staticmethod
    def leaderboard_text(findings_list: list[Findings],
                         failures: list[tuple[str, str]]) -> str:
        """Return the CASE BOARD ranking several datasets by score.

        failures holds (file name, reason) for files that couldn't open.
        """
        lines = ["=" * WIDTH,
                 "  CASE BOARD  -  every dataset in datasets/",
                 "=" * WIDTH,
                 board_row("Rank", "Dataset", "Rows", "Score", "Verdict")]
        # Highest score first; equal scores in alphabetical order.
        ranked = sorted(findings_list,
                        key=lambda f: (-f.overall, f.dataset.name.lower()))
        for rank, findings in enumerate(ranked, start=1):
            lines.append(board_row(str(rank), findings.dataset.name,
                                   f"{findings.dataset.num_rows():,}",
                                   str(findings.overall),
                                   findings.short_verdict))
        for name, reason in failures:
            lines.append(board_row("--", name, "-", "-", "Could not open"))
        lines.append("-" * WIDTH)
        if failures:
            for name, reason in failures:
                lines.append(shorten(f"  {name}: {reason}", WIDTH))
            lines.append("-" * WIDTH)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _preview_table(dataset: Dataset) -> list[str]:
        """Return the header and first rows as a table that fits WIDTH."""
        table = [dataset.header] + dataset.preview(PREVIEW_ROWS)
        cells = []
        for row in table:
            cells.append([shorten(flatten(cell), CELL_WIDTH)
                          for cell in row])

        widths = []
        line_length = 2
        for column in range(dataset.num_columns()):
            width = max(len(row[column]) for row in cells)
            extra = width if column == 0 else width + 3  # " | "
            if line_length + extra > WIDTH:
                break
            widths.append(width)
            line_length += extra

        lines = []
        for row in cells:
            padded = []
            for column, width in enumerate(widths):
                padded.append(row[column].ljust(width))
            lines.append(("  " + " | ".join(padded)).rstrip())
        hidden = dataset.num_columns() - len(widths)
        if hidden > 0:
            lines.append(f"  (+{plural(hidden, 'more column')})")
        return lines

    def _header_lines(self) -> list[str]:
        """Return the CASE FILE banner."""
        when = self.findings.investigated_at
        case = f"CASE FILE #{when:%Y%m%d-%H%M}"
        title = "PYTHON DATA DETECTIVE"
        return ["=" * WIDTH,
                case + title.rjust(WIDTH - len(case)),
                f"Dataset : {shorten(self.findings.dataset.name, WIDTH - 10)}",
                f"Opened  : {when:%d %b %Y, %H:%M}",
                "=" * WIDTH]

    def _evidence_lines(self) -> list[str]:
        """Return the size of the dataset and how it was read."""
        dataset = self.findings.dataset
        details = [f"delimiter {DELIMITER_NAMES[dataset.delimiter]}"]
        if dataset.blank_lines_skipped > 0:
            details.append(
                plural(dataset.blank_lines_skipped, "blank line")
                + " skipped")
        if dataset.encoding != "utf-8":
            details.append(f"encoding {dataset.encoding}")
        size = (f"  {dataset.num_rows():,} rows x "
                f"{dataset.num_columns():,} columns")
        detail_text = "(" + ", ".join(details) + ")"
        lines = ["[EVIDENCE]"]
        if len(size) + 2 + len(detail_text) <= WIDTH:
            lines.append(size + "  " + detail_text)
        else:
            lines += [size, "  " + detail_text]
        return lines + quote_warning(dataset) + [""]

    def _suspect_lines(self) -> list[str]:
        """Return the columns with missing or invalid values."""
        lines = ["[SUSPECTS]  columns with problems"]
        for profile in self.findings.profiles:
            if profile.missing == 0 and profile.invalid == 0:
                continue
            problems = f"{profile.missing:,} missing"
            if profile.invalid > 0:
                problems += f"  {profile.invalid:,} invalid"
            lines.append("  " + name_column(profile.name)
                         + f"{profile.kind:<9}{problems}")
            if profile.invalid_examples:
                examples = []
                for value, line in profile.invalid_examples:
                    examples.append(f"{quote_value(value)} (line {line}),")
                examples[-1] = examples[-1].rstrip(",")
                lines += wrap_parts(examples,
                                    " " * DETAIL_INDENT + "e.g. ",
                                    DETAIL_INDENT + 5, separator=" ")
        if len(lines) == 1:
            lines.append("  No suspects - every column checks out.")
        return lines + [""]

    def _duplicate_lines(self) -> list[str]:
        """Return the duplicate rows found, up to MAX_LISTED of them."""
        duplicates = self.findings.duplicates
        if not duplicates:
            return ["[DUPLICATES]  none found", ""]
        lines = [f"[DUPLICATES]  {plural(len(duplicates), 'duplicate row')}"]
        for copy_line, original_line in duplicates[:MAX_LISTED]:
            lines.append(f"  line {copy_line} duplicates line "
                         f"{original_line}")
        if len(duplicates) > MAX_LISTED:
            lines.append(f"  ... and {len(duplicates) - MAX_LISTED:,} more")
        return lines + [""]

    def _malformed_lines(self) -> list[str]:
        """Return the rows that had the wrong number of fields."""
        dataset = self.findings.dataset
        malformed = dataset.malformed_rows
        if not malformed:
            return ["[MALFORMED ROWS]  none found", ""]
        lines = [f"[MALFORMED ROWS]  {plural(len(malformed), 'row')} "
                 "with the wrong number of fields"]
        expected = dataset.num_columns()
        for line, count in malformed[:MAX_LISTED]:
            if count > expected:
                fix = "extra field dropped"
                if count - expected > 1:
                    fix = "extra fields dropped"
            else:
                fix = "padded with blanks"
            lines.append(f"  line {line}: {count} fields "
                         f"(expected {expected}) - {fix}")
        if len(malformed) > MAX_LISTED:
            lines.append(f"  ... and {len(malformed) - MAX_LISTED:,} more")
        return lines + [""]

    def _profile_lines(self) -> list[str]:
        """Return a two-line summary of every column."""
        rows = self.findings.dataset.num_rows()
        indent = " " * DETAIL_INDENT
        lines = ["[COLUMN PROFILES]"]
        for profile in self.findings.profiles:
            percent = 100 * profile.missing / rows
            lines.append("  " + name_column(profile.name)
                         + f"{profile.kind:<9}{percent:5.1f}% missing")
            if profile.kind == "numeric":
                low, high, mean, median = profile.stats
                parts = [f"min {format_stat(low)}",
                         f"max {format_stat(high)}",
                         f"mean {format_stat(mean)}",
                         f"median {format_stat(median)}"]
                lines += wrap_parts(parts, indent, DETAIL_INDENT)
            elif profile.kind == "text":
                value, count = profile.most_common
                parts = [f"{profile.unique_count:,} unique,",
                         f"most common {quote_value(value)} ({count:,})"]
                lines += wrap_parts(parts, indent, DETAIL_INDENT,
                                    separator=" ")
            else:
                lines.append(indent + "all values missing")
        return lines + [""]

    def _score_lines(self) -> list[str]:
        """Return the three sub-scores and the verdict."""
        f = self.findings
        if f.numeric_cells == 0:
            validity_note = "(no numeric columns)"
        else:
            validity_note = f"({f.invalid_percent:.1f}% of numbers invalid)"
        scores = [
            ("Completeness", f.completeness,
             f"({f.missing_percent:.1f}% of cells missing)"),
            ("Uniqueness", f.uniqueness,
             f"({f.duplicate_percent:.1f}% of rows duplicated)"),
            ("Validity", f.validity, validity_note),
        ]
        lines = ["[SUB-SCORES]  100 - 5 points per 1% of problem data"]
        for label, score, note in scores:
            line = f"  {label:<14}{score:.1f}"
            if len(line) + 2 + len(note) <= WIDTH:
                lines.append(line + "  " + note)
            else:
                lines += [line, " " * DETAIL_INDENT + note]
        return lines + ["=" * WIDTH,
                        f"VERDICT: {f.overall}/100  -  {f.verdict}",
                        "=" * WIDTH]
