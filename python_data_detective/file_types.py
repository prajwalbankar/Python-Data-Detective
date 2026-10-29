"""Recognise files that aren't CSV tables, so the user is told what they are.

A marker might open an image, an Excel workbook or a JSON file by mistake.
Instead of a vague "can't read this", the program names the format: from
the first few bytes of a binary file (its "magic number"), or from the
way a text file starts.
"""
import json
from typing import Optional

# (first bytes of the file, what kind of file it is)
SIGNATURES = [
    (b"\x89PNG", "a PNG image"),
    (b"\xff\xd8\xff", "a JPEG image"),
    (b"GIF8", "a GIF image"),
    (b"BM", "a BMP image"),
    (b"ID3", "an MP3 audio file"),
    (b"\xff\xfb", "an MP3 audio file"),
    (b"%PDF", "a PDF document"),
    (b"\xd0\xcf\x11\xe0", "an old Office file (.xls or .doc)"),
    (b"\x1f\x8b", "a gzip-compressed file"),
    (b"SQLite format 3", "an SQLite database"),
    (b"MZ", "a Windows program (.exe)"),
    (b"\x7fELF", "a Linux program"),
    (b"PAR1", "a Parquet file"),
    (b"7z\xbc\xaf", "a 7-Zip archive"),
    (b"Rar!", "a RAR archive"),
]
# RIFF files say what they hold in bytes 8-11.
RIFF_KINDS = {b"WAVE": "a WAV audio file", b"AVI ": "an AVI video",
              b"WEBP": "a WebP image"}
# Office files are zip archives; the folder names inside give them away.
ZIP_KINDS = [(b"xl/", "an Excel workbook (.xlsx)"),
             (b"word/", "a Word document (.docx)"),
             (b"ppt/", "a PowerPoint file (.pptx)")]
# The first words of a line that starts an SQL script.
SQL_STARTS = ("CREATE TABLE", "INSERT INTO", "DROP TABLE", "PRAGMA ",
              "BEGIN TRANSACTION")


def binary_kind(data: bytes) -> Optional[str]:
    """Name a binary file's format from its first bytes, if known."""
    if data.startswith(b"RIFF"):
        return RIFF_KINDS.get(data[8:12])
    if data[4:8] == b"ftyp":
        return "an MP4 or MOV video"
    if data.startswith(b"PK\x03\x04"):
        for marker, kind in ZIP_KINDS:
            if marker in data:
                return kind
        return "a zip archive"
    if data[:1] == b"\x80" and data[1:2] in (b"\x02", b"\x03", b"\x04",
                                              b"\x05"):
        return "a Python pickle file"
    for start, kind in SIGNATURES:
        if data.startswith(start):
            return kind
    return None


def describe_binary(data: bytes) -> str:
    """Return the message explaining why a binary file can't be read."""
    kind = binary_kind(data)
    if kind is None:
        return "doesn't look like a plain text CSV"
    message = f"this is {kind}, not a CSV file"
    if "Excel" in kind:
        message += " - open it in Excel and use Save As > CSV"
    return message


def describe_text_format(text: str) -> Optional[str]:
    """Return a message if the text is a known format that isn't a CSV."""
    start = text.lstrip()[:5000]
    lines = start.splitlines()
    first_line = lines[0].strip() if lines else ""
    if start.startswith("%PDF"):
        return "this is a PDF document, not a CSV file"
    if start[:1] in ("[", "{"):
        kind = json_kind(text, first_line)
        if kind:
            return f"this looks like {kind}, not a CSV table"
    # Markup has closing tags; a CSV header like "<id>,name" doesn't.
    if start.startswith("<") and ("</" in start or "/>" in start):
        return "this looks like XML or HTML markup, not a CSV table"
    if first_line.upper().startswith(SQL_STARTS):
        return "this looks like an SQL script, not a CSV table"
    if len(lines) >= 2 and first_line.startswith("|"):
        divider = lines[1].strip()
        if "-" in divider and set(divider) <= set("|-: "):
            return "this looks like a Markdown table, not a CSV file"
    return None


def json_kind(text: str, first_line: str) -> Optional[str]:
    """Return 'JSON data' or 'JSON Lines data' if the text really is."""
    try:
        json.loads(text)
        return "JSON data"
    except ValueError:
        pass
    try:
        # JSON Lines: one JSON object on every line.
        if isinstance(json.loads(first_line), (dict, list)):
            return "JSON Lines data"
    except ValueError:
        pass
    return None
