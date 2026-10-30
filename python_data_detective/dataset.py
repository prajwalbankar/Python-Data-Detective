"""Load a CSV file into memory as a tidy grid of text values.

The Dataset class reads a file once, works out its encoding and
delimiter, skips blank lines and any notes above the header, and makes
every row the same length as the header, so the investigator can treat
the data as a neat grid.
"""
import codecs
import csv
import io
import os
from collections import Counter
from typing import Optional

from errors import EmptyDatasetError, UnreadableFileError
from file_types import describe_binary, describe_text_format

# How much of the file the delimiter detector looks at.
SNIFF_SAMPLE_SIZE = 4096
# The delimiters we're willing to detect: comma, semicolon, tab, pipe.
DELIMITERS = ",;\t|"
# Notes above the header (as in World Bank downloads) are only skipped
# when a blank line within this many lines separates them from it.
NOTES_SEARCH_LINES = 10
# The csv module refuses any cell over 131,072 characters by default, but
# real datasets sometimes hold whole documents or base64 images in a cell.
# 2**31 - 1 is the largest limit every platform accepts.
csv.field_size_limit(2**31 - 1)


def plural(count: int, word: str) -> str:
    """Return e.g. '1 row' or '3 rows'."""
    if count == 1:
        return f"{count:,} {word}"
    return f"{count:,} {word}s"


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
        # True if lines end with extra, empty fields (e.g. "1,2,").
        self.trailing_delimiters = False
        # Line where a quote opens and is never closed, if there is one.
        self.unclosed_quote_line: Optional[int] = None
        # Sentences describing problems with the file's structure.
        self.warnings: list[str] = []
        # The line the column names are on, and how many lines above it
        # were skipped as notes (0 when the header is the first line).
        self.header_line = 1
        self.notes_lines = 0

        text = self._read_text()
        named = self._separator_line(text)
        detected = named or self._detect_delimiter(text)
        # With no delimiter found, each line is read as a single value.
        self.delimiter_found = detected is not None
        self.delimiter = detected or ","
        self._parse(text, separator_line=named is not None)
        self.unclosed_quote_line = self._find_unclosed_quote(text)
        self.warnings = self._find_warnings()

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
        return (f"{self.name} ({plural(self.num_rows(), 'row')} x "
                f"{plural(self.num_columns(), 'column')})")

    def _read_text(self) -> str:
        """Read the whole file and decode it into text."""
        # Windows raises PermissionError for folders, so check first.
        if os.path.isdir(self.path):
            raise UnreadableFileError(
                f"'{self.path}' is a folder, not a file")
        # Only read ordinary files: opening a device such as Windows'
        # CON would wait for keyboard input forever.
        if not os.path.isfile(self.path):
            raise UnreadableFileError(f"no file at '{self.path}'")
        data = self._read_bytes()
        text = self._decode(data)
        # Plain text never contains zero bytes; images, Office files
        # and programs almost always do.
        if "\x00" in text:
            raise UnreadableFileError(describe_binary(data))
        other_format = describe_text_format(text)
        if other_format:
            raise UnreadableFileError(other_format)
        return text

    def _decode(self, data: bytes) -> str:
        """Turn the file's bytes into text, trying likely encodings."""
        utf16 = self._utf16_kind(data)
        if utf16:
            self.encoding = "utf-16"
            return data.decode(utf16, errors="replace")
        try:
            # utf-8-sig also removes the BOM that Excel adds.
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
        mixed = self._decode_line_by_line(data)
        if mixed is not None:
            self.encoding = "utf-8 + cp1252"
            return mixed
        # latin-1 can decode any bytes, so this always succeeds.
        self.encoding = "latin-1"
        text = data.decode("latin-1")
        # Characters 0x80-0x9F are invisible control codes in latin-1 but
        # curly quotes, dashes and the euro sign in Excel's cp1252.
        if any("\x80" <= char <= "\x9f" for char in text):
            try:
                text = data.decode("cp1252")
                self.encoding = "cp1252"
            except UnicodeDecodeError:
                pass
        return text

    @staticmethod
    def _decode_line_by_line(data: bytes) -> Optional[str]:
        """Decode a file whose lines use different encodings.

        Files pasted together from different sources can have some lines
        in UTF-8 and others in Windows cp1252. Returns the text if both
        kinds are present, otherwise None.
        """
        pieces = []
        has_utf8 = False     # a line with non-ASCII characters in UTF-8
        has_other = False    # a line that isn't valid UTF-8
        for line in data.splitlines(keepends=True):
            try:
                piece = line.decode("utf-8")
                if not piece.isascii():
                    has_utf8 = True
            except UnicodeDecodeError:
                has_other = True
                try:
                    piece = line.decode("cp1252")
                except UnicodeDecodeError:
                    piece = line.decode("latin-1")
            pieces.append(piece)
        if not (has_utf8 and has_other):
            return None
        text = "".join(pieces)
        if text.startswith("﻿"):
            text = text[1:]          # the BOM Excel puts at the start
        return text

    @staticmethod
    def _utf16_kind(data: bytes) -> Optional[str]:
        """Return the codec name if the bytes look like UTF-16."""
        if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return "utf-16"     # the BOM says which byte order
        # Without a BOM, ASCII text in UTF-16 has a zero in every other
        # byte: the odd bytes for little-endian, the even ones for big.
        sample = data[:200]
        if len(sample) >= 4 and len(sample) % 2 == 0:
            if set(sample[1::2]) == {0}:
                return "utf-16-le"
            if set(sample[0::2]) == {0}:
                return "utf-16-be"
        return None

    def _read_bytes(self) -> bytes:
        """Read the raw bytes of the file, turning OS errors into ours."""
        try:
            with open(self.path, "rb") as file:
                return file.read()
        except FileNotFoundError:
            raise UnreadableFileError(f"no file at '{self.path}'")
        except PermissionError:
            raise UnreadableFileError(
                f"no permission to read '{self.path}'")
        except OSError as err:
            # Anything else the OS rejects, e.g. a name containing ? or *
            # on Windows, or a name that is far too long.
            reason = err.strerror or str(err)
            raise UnreadableFileError(
                f"couldn't open '{self.path}' ({reason})")

    @staticmethod
    def _detect_delimiter(text: str) -> Optional[str]:
        """Guess the delimiter from the start of the file, or None."""
        try:
            dialect = csv.Sniffer().sniff(text[:SNIFF_SAMPLE_SIZE],
                                          delimiters=DELIMITERS)
            return dialect.delimiter
        except csv.Error:
            return None

    @staticmethod
    def _separator_line(text: str) -> Optional[str]:
        """Return the delimiter an Excel "sep=;" first line names, if any."""
        lines = text[:8].splitlines()
        first = lines[0] if lines else ""
        if (len(first) == 5 and first.startswith("sep=")
                and first[4] in DELIMITERS):
            return first[4]
        return None

    def _parse(self, text: str, separator_line: bool) -> None:
        """Split the text into a header and rows, noting any problems."""
        reader = csv.reader(io.StringIO(text, newline=""),
                            delimiter=self.delimiter)
        records = []        # (start line, fields) for every non-blank line
        early_blanks = []   # blank lines near the top, where notes end
        previous_end = 0
        try:
            for fields in reader:
                # A quoted field can span lines, so remember where the
                # row starts: one line after the previous row ended.
                start_line = previous_end + 1
                previous_end = reader.line_num
                if self._is_blank(fields):
                    self.blank_lines_skipped += 1
                    if start_line <= NOTES_SEARCH_LINES:
                        early_blanks.append(start_line)
                    continue
                records.append((start_line, fields))
        except csv.Error as err:
            raise UnreadableFileError(f"couldn't be read as CSV: {err}")

        # Excel's "sep=;" line only names the delimiter: it isn't data.
        first = 1 if separator_line else 0
        if len(records) <= first:
            raise EmptyDatasetError("file is empty")
        position = self._header_position(records, first, early_blanks)
        self.header_line, header_fields = records[position]
        if position > first:
            self.notes_lines = self.header_line - 1
        raw_rows = records[position + 1:]
        if not raw_rows:
            raise EmptyDatasetError("file has a header but no data rows")

        width = self._width_without_trailing_blanks(header_fields, raw_rows)
        self.header = self._clean_header(header_fields[:width])
        for start_line, fields in raw_rows:
            self._add_row(fields, start_line)

    @staticmethod
    def _header_position(records: list[tuple[int, list[str]]], first: int,
                         early_blanks: list[int]) -> int:
        """Return the position in records of the line with the column names.

        Usually that's the first line. Downloads such as the World Bank's
        start with notes instead: lines with at most half as many filled
        fields as most rows have, then a blank line. The header is then
        the first wider line, as long as a blank line comes right before
        it near the top. Otherwise (a title directly above the header, or
        rows broken by stray commas) the first line stays the header.
        """
        if not early_blanks:
            return first
        widths = Counter(len(fields) for _, fields in records)
        usual = widths.most_common(1)[0][0]
        position = first
        while position < len(records):
            line, fields = records[position]
            filled = sum(1 for value in fields if value.strip())
            if filled * 2 > usual or line > NOTES_SEARCH_LINES + 1:
                break
            position += 1
        if position == len(records) or position == first:
            return first
        if records[position][0] - 1 in early_blanks:
            return position
        return first

    def _width_without_trailing_blanks(
            self, header_fields: list[str],
            raw_rows: list[tuple[int, list[str]]]) -> int:
        """Return the header width, ignoring empty unnamed end columns.

        A trailing delimiter on every line ("a,b," / "1,2,") makes an
        extra column with no name and no data. That's an export quirk,
        not a real column, so it isn't counted.
        """
        width = len(header_fields)
        while width > 1 and header_fields[width - 1].strip() == "":
            column_has_data = False
            for _, fields in raw_rows:
                if len(fields) >= width and fields[width - 1].strip():
                    column_has_data = True
                    break
            if column_has_data:
                break
            width -= 1
            self.trailing_delimiters = True
        return width

    def _find_unclosed_quote(self, text: str) -> Optional[int]:
        """Return the line where a never-closed quote starts, if any.

        The normal, forgiving reader quietly treats everything after such
        a quote as one value. A strict second read reports "unexpected
        end of data" in exactly that case, so we can warn the user.
        """
        reader = csv.reader(io.StringIO(text, newline=""),
                            delimiter=self.delimiter, strict=True)
        previous_end = 0
        try:
            for _ in reader:
                previous_end = reader.line_num
        except csv.Error as err:
            if "unexpected end of data" in str(err):
                return previous_end + 1
        return None

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
        extra = fields[width:]
        if extra and all(value.strip() == "" for value in extra):
            # Only empty fields past the end: a trailing delimiter.
            fields = fields[:width]
            self.trailing_delimiters = True
        elif len(fields) != width:
            self.malformed_rows.append((start_line, len(fields)))
            if len(fields) < width:
                fields = fields + [""] * (width - len(fields))
            else:
                fields = fields[:width]
        self.rows.append(fields)
        self.line_numbers.append(start_line)

    def _find_warnings(self) -> list[str]:
        """Return sentences about problems with the file's structure."""
        warnings = []
        if self.notes_lines:
            warnings.append(
                f"the {plural(self.notes_lines, 'line')} above the header on "
                f"line {self.header_line} look like notes rather than data, "
                "so they were skipped.")
        if self.unclosed_quote_line is not None:
            warnings.append(
                f"a quote opened on line {self.unclosed_quote_line} is "
                "never closed, so everything after it was read as a "
                "single value.")
        numeric_names = 0
        for name in self.header:
            try:
                float(name)
                numeric_names += 1
            except ValueError:
                pass
        # A header found below notes was recognised by its width, so
        # years as column names (as in World Bank files) don't make it data.
        if numeric_names * 2 >= len(self.header) and not self.notes_lines:
            warnings.append(
                "most column names look like numbers, so the file may "
                "have no header row (its first row is being used as the "
                "column names).")
        long_rows = 0
        for line, count in self.malformed_rows:
            if count > len(self.header):
                long_rows += 1
        if long_rows * 2 > self.num_rows():
            warnings.append(
                f"most rows have more fields than the header's "
                f"{len(self.header)}, so the first line may be a title "
                "rather than the column names.")
        if self.encoding == "utf-8 + cp1252":
            warnings.append(
                "lines use different encodings (UTF-8 and Windows "
                "cp1252), so each line was decoded separately; check "
                "accented letters.")
        if not self.delimiter_found and self.num_columns() == 1:
            warnings.append(
                "no delimiter was found, so each line was read as a single "
                "value. That's fine for a one-column list; otherwise this "
                "file may not be a CSV table.")
        return warnings
