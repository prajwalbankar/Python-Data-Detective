"""Load a CSV file into memory as a tidy grid of text values.

The Dataset class reads a file once, works out its encoding and
delimiter, skips blank lines, and makes every row the same length as the
header, so the investigator can treat the data as a neat grid.
"""
import csv
import io
import os

from errors import EmptyDatasetError, UnreadableFileError

# How much of the file the delimiter detector looks at.
SNIFF_SAMPLE_SIZE = 4096
# The delimiters we're willing to detect: comma, semicolon, tab, pipe.
DELIMITERS = ",;\t|"


class Dataset:
    """A CSV file loaded into memory as a header and a list of rows."""

    def __init__(self, path: str) -> None:
        """Load the CSV file at path.

        Raises UnreadableFileError if the file can't be opened or parsed,
        and EmptyDatasetError if it has no data rows.
        """
        self.path = path
        self.name = os.path.basename(path)
        self.encoding = "utf-8"
        self.delimiter = ","
        self.header: list[str] = []
        self.rows: list[list[str]] = []
        self.line_numbers: list[int] = []
        self.malformed_rows: list[tuple[int, int]] = []
        self.blank_lines_skipped = 0

        text = self._read_text()
        self.delimiter = self._detect_delimiter(text)
        self._parse(text)

    def num_rows(self) -> int:
        """Return the number of data rows (the header isn't counted)."""
        return len(self.rows)

    def num_columns(self) -> int:
        """Return the number of columns in the header."""
        return len(self.header)

    def column_values(self, index: int) -> list[str]:
        """Return every value in one column, top to bottom."""
        # One value from each row, taken at the column's position.
        return [row[index] for row in self.rows]

    def preview(self, n: int = 5) -> list[list[str]]:
        """Return the first n data rows."""
        return self.rows[:n]

    def __str__(self) -> str:
        """Describe the dataset, e.g. 'sales.csv (200 rows x 6 columns)'."""
        return (f"{self.name} ({self.num_rows():,} rows x "
                f"{self.num_columns()} columns)")

    def _read_text(self) -> str:
        """Read the whole file as text, falling back to latin-1."""
        # Windows raises PermissionError for folders, so check first.
        if os.path.isdir(self.path):
            raise UnreadableFileError(
                f"'{self.path}' is a folder, not a file")
        try:
            # utf-8-sig also removes the BOM that Excel adds.
            text = self._read_with("utf-8-sig")
        except UnicodeDecodeError:
            # latin-1 can decode any bytes, so this read always succeeds.
            self.encoding = "latin-1"
            text = self._read_with("latin-1")
        if "\x00" in text:
            raise UnreadableFileError("doesn't look like a plain text CSV")
        return text

    def _read_with(self, encoding: str) -> str:
        """Read the file with one encoding, turning OS errors into ours."""
        try:
            # newline="" leaves line endings for the csv module to handle.
            with open(self.path, encoding=encoding, newline="") as file:
                return file.read()
        except FileNotFoundError:
            raise UnreadableFileError(f"no file at '{self.path}'")
        except PermissionError:
            raise UnreadableFileError(
                f"no permission to read '{self.path}'")

    @staticmethod
    def _detect_delimiter(text: str) -> str:
        """Guess the delimiter from the start of the file; default ','."""
        try:
            dialect = csv.Sniffer().sniff(text[:SNIFF_SAMPLE_SIZE],
                                          delimiters=DELIMITERS)
            return dialect.delimiter
        except csv.Error:
            return ","

    def _parse(self, text: str) -> None:
        """Split the text into a header and rows, noting any problems."""
        reader = csv.reader(io.StringIO(text, newline=""),
                            delimiter=self.delimiter)
        previous_end = 0
        try:
            for fields in reader:
                # A quoted field can span lines, so remember where the
                # row starts: one line after the previous row ended.
                start_line = previous_end + 1
                previous_end = reader.line_num
                if self._is_blank(fields):
                    self.blank_lines_skipped += 1
                    continue
                if not self.header:
                    self.header = self._clean_header(fields)
                    continue
                self._add_row(fields, start_line)
        except csv.Error as err:
            raise UnreadableFileError(f"couldn't be read as CSV: {err}")

        if not self.header:
            raise EmptyDatasetError("file is empty")
        if not self.rows:
            raise EmptyDatasetError("file has a header but no data rows")

    @staticmethod
    def _is_blank(fields: list[str]) -> bool:
        """Return True for a line with nothing on it but spaces."""
        if len(fields) == 0:
            return True
        return len(fields) == 1 and fields[0].strip() == ""

    @staticmethod
    def _clean_header(fields: list[str]) -> list[str]:
        """Strip column names and name any blank ones 'column_N'."""
        header = []
        for position, name in enumerate(fields, start=1):
            name = name.strip()
            if name == "":
                name = f"column_{position}"
            header.append(name)
        return header

    def _add_row(self, fields: list[str], start_line: int) -> None:
        """Store a data row, padding or trimming it to the header width."""
        width = len(self.header)
        if len(fields) != width:
            self.malformed_rows.append((start_line, len(fields)))
            if len(fields) < width:
                fields = fields + [""] * (width - len(fields))
            else:
                fields = fields[:width]
        self.rows.append(fields)
        self.line_numbers.append(start_line)
