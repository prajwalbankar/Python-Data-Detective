"""Generate stress-test inputs for Python Data Detective.

Builds about 60 files in stress_tests/files/: real images, audio and
documents, text that isn't a CSV, number-only data, and large, messy,
realistic CSVs. Everything is made with the standard library and a fixed
random seed, so the files are the same on every run. Not part of the
submission.

    python stress_tests/make_stress_files.py
"""
import base64
import csv
import gzip
import io
import json
import math
import os
import pickle
import random
import shutil
import sqlite3
import struct
import sys
import wave
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "files")
rng = random.Random(2026)

# (file name, category, description) for every scenario, in report order.
SCENARIOS = []


def add(name: str, category: str, description: str, content) -> None:
    """Write one scenario file (bytes or text) and remember it."""
    path = os.path.join(OUT, name)
    if isinstance(content, bytes):
        with open(path, "wb") as file:
            file.write(content)
    else:
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(content)
    SCENARIOS.append((name, category, description))


def rows_to_csv(rows: list, delimiter: str = ",",
                terminator: str = "\n") -> str:
    """Render rows with the csv module (quoting where needed)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator=terminator)
    writer.writerows(rows)
    return buffer.getvalue()


# ------------------------------------------------------------- images/media

def png(width: int, height: int) -> bytes:
    """A real, valid PNG image with a colour gradient."""
    raw = b""
    for y in range(height):
        raw += b"\x00" + b"".join(
            bytes(((x * 4) % 256, (y * 4) % 256, 128)) for x in range(width))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def bmp(width: int, height: int) -> bytes:
    """A real 24-bit BMP image."""
    row_size = (width * 3 + 3) // 4 * 4
    pixels = b""
    for y in range(height):
        row = b"".join(bytes((x * 60 % 256, y * 60 % 256, 200))
                       for x in range(width))
        pixels += row + b"\x00" * (row_size - len(row))
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0,
                       len(pixels), 2835, 2835, 0, 0)
    return header + info + pixels


def wav_tone() -> bytes:
    """A real WAV file: half a second of a 440 Hz tone."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(
            2 * math.pi * 440 * i / 8000))) for i in range(4000))
        sound.writeframes(frames)
    return buffer.getvalue()


def make_images_and_media() -> None:
    """Images, audio and video in their real binary formats."""
    cat = "Images & media"
    add("photo.png", cat, "real 64x64 PNG image", png(64, 64))
    add("photo_renamed.csv", cat, "the same PNG renamed to .csv", png(64, 64))
    add("photo.jpg", cat, "JPEG (JFIF header + compressed-looking bytes)",
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + rng.randbytes(3000) + b"\xff\xd9")
    add("pixel.gif", cat, "real 1x1 GIF",
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9"
        b"\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
        b"\x02D\x01\x00;")
    add("bitmap.bmp", cat, "real 8x8 BMP image", bmp(8, 8))
    add("drawing.svg", cat, "SVG vector image (XML text)",
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">\n'
        '  <circle cx="50" cy="50" r="40" stroke="green" fill="yellow"/>\n'
        '  <text x="20" y="55">Hello, detective</text>\n</svg>\n')
    add("tone.wav", cat, "real WAV audio, 440 Hz tone", wav_tone())
    add("song.mp3", cat, "MP3 (ID3 header + frame-like bytes)",
        b"ID3\x03\x00\x00\x00\x00\x00\x0a" + rng.randbytes(4000))
    add("clip.mp4", cat, "MP4 video (ftyp box + media-like bytes)",
        struct.pack(">I", 24) + b"ftypisom\x00\x00\x02\x00isomiso2"
        + rng.randbytes(4000))

    folder = os.path.join(OUT, "image_folder")
    os.makedirs(folder, exist_ok=True)
    for index in range(5):
        with open(os.path.join(folder, f"img_{index}.png"), "wb") as file:
            file.write(png(16 + index, 16))
    SCENARIOS.append(("image_folder", cat,
                      "a folder of 5 PNG images (path given at option P)"))

    # Image datasets as they usually reach analysts: CSVs about images.
    labels = ["cat", "dog", "bird", "car", "tree"]
    rows = [["filename", "width", "height", "format", "size_kb", "label"]]
    for index in range(300):
        rows.append([f"img_{index:04d}.jpg", rng.choice([224, 256, 512]),
                     rng.choice([224, 256, 512]),
                     rng.choice(["jpg", "png"]),
                     round(rng.uniform(5, 900), 1),
                     rng.choice(labels + ["", "NA"])])
    add("image_metadata.csv", cat,
        "CSV describing 300 images (sizes, formats, labels)",
        rows_to_csv(rows))

    rows = [["label"] + [f"pixel{i}" for i in range(784)]]
    for _ in range(400):
        rows.append([rng.randint(0, 9)]
                    + [rng.choice([0, 0, 0, rng.randint(0, 255)])
                       for _ in range(784)])
    add("mnist_like_pixels.csv", cat,
        "MNIST-style: 400 images as 784 pixel columns each",
        rows_to_csv(rows))

    rows = [["id", "filename", "thumbnail_base64"]]
    for index in range(40):
        rows.append([index, f"thumb_{index}.png",
                     base64.b64encode(png(24, 24)).decode()])
    add("images_base64_small.csv", cat,
        "40 small PNG thumbnails embedded as base64 text", rows_to_csv(rows))
    add("images_base64_large.csv", cat,
        "one 200 KB image embedded as base64 in a cell",
        rows_to_csv([["id", "image_base64"],
                     [1, base64.b64encode(rng.randbytes(150_000)).decode()]]))


# ------------------------------------------------------ documents/archives

def make_documents_and_archives() -> None:
    """Office files, archives, databases and other binary formats."""
    cat = "Documents & archives"

    def zipped(files: dict) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, text in files.items():
                archive.writestr(name, text)
        return buffer.getvalue()

    add("workbook.xlsx", cat, "Excel workbook (zip of XML sheets)", zipped({
        "[Content_Types].xml": "<Types/>",
        "xl/workbook.xml": "<workbook><sheets><sheet name='Sales'/></sheets>"
                           "</workbook>",
        "xl/worksheets/sheet1.xml": "<worksheet><sheetData><row><c><v>1</v>"
                                    "</c></row></sheetData></worksheet>"}))
    add("workbook_renamed.csv", cat, "the same .xlsx renamed to .csv",
        zipped({"[Content_Types].xml": "<Types/>",
                "xl/workbook.xml": "<workbook/>"}))
    add("old_excel.xls", cat, "legacy Excel .xls (OLE2 compound file)",
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504
        + rng.randbytes(2000))
    add("report.docx", cat, "Word document (zip of XML)", zipped({
        "[Content_Types].xml": "<Types/>",
        "word/document.xml": "<w:document><w:body><w:p><w:r><w:t>Hello"
                             "</w:t></w:r></w:p></w:body></w:document>"}))
    add("archive.zip", cat, "zip archive containing a CSV",
        zipped({"inner.csv": "a,b\n1,2\n3,4\n"}))
    add("data.csv.gz", cat, "gzip-compressed CSV",
        gzip.compress(b"a,b\n1,2\n3,4\n" * 200))
    add("plain_text.pdf", cat, "PDF written entirely in plain text",
        "%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        "trailer << /Root 1 0 R >>\n%%EOF\n")
    add("compressed.pdf", cat, "PDF with a compressed (binary) stream",
        b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n4 0 obj << /Filter /FlateDecode >>\n"
        b"stream\n" + zlib.compress(b"BT /F1 12 Tf (Hello) Tj ET" * 50)
        + b"\nendstream\nendobj\n%%EOF\n")

    db_path = os.path.join(OUT, "database.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE sales (id INTEGER, amount REAL)")
    connection.executemany("INSERT INTO sales VALUES (?, ?)",
                           [(i, i * 1.5) for i in range(100)])
    connection.commit()
    connection.close()
    SCENARIOS.append(("database.sqlite", cat, "real SQLite database"))

    shutil.copyfile(sys.executable, os.path.join(OUT, "program.exe"))
    SCENARIOS.append(("program.exe", cat,
                      "a real program (a copy of python.exe)"))
    add("data.pkl", cat, "Python pickle file",
        pickle.dumps({"rows": list(range(500)), "name": "test"}))
    add("table.parquet", cat, "Parquet-style columnar file (PAR1 magic)",
        b"PAR1" + rng.randbytes(3000) + b"PAR1")


# ------------------------------------------------------ text, not a table

def make_text_not_csv() -> None:
    """Text files in formats that are not comma-separated tables."""
    cat = "Text that isn't a CSV"
    people = [{"id": i, "name": f"Person {i}", "tags": ["a", "b"],
               "score": round(rng.uniform(0, 100), 2)} for i in range(60)]
    add("data.json", cat, "JSON array of objects",
        json.dumps(people, indent=2))
    add("data.ndjson", cat, "JSON Lines (one object per line)",
        "\n".join(json.dumps(person) for person in people) + "\n")
    add("data.xml", cat, "XML records", "<?xml version='1.0'?>\n<people>\n"
        + "".join(f"  <person id='{p['id']}'><name>{p['name']}</name>"
                  f"<score>{p['score']}</score></person>\n" for p in people)
        + "</people>\n")
    add("table.html", cat, "HTML page with a table",
        "<html><body><table>\n<tr><th>Name</th><th>Score</th></tr>\n"
        + "".join(f"<tr><td>{p['name']}</td><td>{p['score']}</td></tr>\n"
                  for p in people) + "</table></body></html>\n")
    add("table.md", cat, "Markdown table (pipe-separated)",
        "| Name | Score | City |\n|------|-------|------|\n"
        + "".join(f"| {p['name']} | {p['score']} | Sydney |\n"
                  for p in people))
    add("config.yaml", cat, "YAML configuration",
        "app: detective\nversion: 2\nsettings:\n  width: 64\n"
        "  colours: [red, green]\n")
    add("settings.ini", cat, "INI settings file",
        "[display]\nwidth = 64\ntheme = dark\n\n[data]\nfolder = datasets\n")
    story = ("It was a dark and stormy night, and the dataset was missing "
             "half its values. The detective, tired but determined, opened "
             "the file again. Rows, columns, quotes and commas everywhere; "
             "nothing lined up.\n\n") * 15
    add("story.txt", cat, "plain English prose", story)
    with open(os.path.join(os.path.dirname(HERE), "python_data_detective",
                           "main.py"), encoding="utf-8") as file:
        add("source_code.py", cat, "Python source code (the app's main.py)",
            file.read())
    log_lines = []
    for i in range(500):
        log_lines.append(
            f'192.168.0.{rng.randint(1, 254)} - - [29/Oct/2026:10:{i % 60:02d}'
            f':00 +1100] "GET /page/{i} HTTP/1.1" '
            f'{rng.choice([200, 200, 404, 500])} {rng.randint(100, 9000)} '
            f'"-" "Mozilla/5.0 (Windows NT 10.0)"')
    add("server.log", cat, "web server access log (space separated)",
        "\n".join(log_lines) + "\n")
    add("fixed_width.txt", cat, "fixed-width columns padded with spaces",
        "NAME        AGE  CITY      \n"
        + "".join(f"{('Person' + str(i)):<12}{rng.randint(18, 90):<5}"
                  f"{rng.choice(['Sydney', 'Perth']):<10}\n"
                  for i in range(100)))
    add("dump.sql", cat, "SQL dump with INSERT statements",
        "CREATE TABLE t (id INT, name TEXT);\n"
        + "".join(f"INSERT INTO t VALUES ({i}, 'name {i}');\n"
                  for i in range(100)))
    add("email.eml", cat, "an email message",
        "From: tutor@example.com\nTo: student@example.com\n"
        "Subject: Your project, feedback\n\nHi,\nGreat work, "
        "but please add more tests.\nThanks,\nTutor\n")
    add("base64_blob.txt", cat, "one 300 KB line of base64, no delimiters",
        base64.b64encode(rng.randbytes(225_000)).decode() + "\n")
    add("minified.js", cat, "minified JavaScript on one 60 KB line",
        "var a=[" + ",".join(str(rng.randint(0, 999)) for _ in range(15000))
        + "];function f(x){return x*2}\n")
    add("whitespace_only.txt", cat, "only spaces, tabs and blank lines",
        "   \n\t\n\n     \n")
    add("bom_only.csv", cat, "a UTF-8 BOM and nothing else",
        b"\xef\xbb\xbf")


# ---------------------------------------------------------- numbers only

def make_numbers() -> None:
    """Number-only data and numbers written in tricky ways."""
    cat = "Numbers"
    rows = [[round(rng.gauss(0, 10), 4) for _ in range(10)]
            for _ in range(100)]
    add("matrix_no_header.csv", cat,
        "100x10 matrix of numbers, no header row", rows_to_csv(rows))
    rows = [["customer_id", "zip_code", "phone", "card_last4"]]
    for i in range(200):
        rows.append([f"{rng.randint(1, 99999):07d}",
                     f"{rng.randint(1000, 9999):05d}",
                     f"04{rng.randint(10000000, 99999999)}",
                     f"{rng.randint(0, 9999):04d}"])
    add("ids_with_leading_zeros.csv", cat,
        "IDs, postcodes and phone numbers with leading zeros",
        rows_to_csv(rows))
    rows = [["product", "price", "weight_kg", "total"]]
    for i in range(150):
        price = f"{rng.uniform(1, 2000):.2f}".replace(".", ",")
        rows.append([f"Item {i}", price,
                     f"{rng.uniform(0.1, 20):.3f}".replace(".", ","),
                     f"{rng.randint(1, 9)}.{rng.randint(100, 999)},50"])
    add("european_decimals.csv", cat,
        "Excel EU export: ';' delimiter, decimal commas, BOM, CRLF",
        ("﻿" + rows_to_csv(rows, ";", "\r\n")).encode("utf-8"))
    rows = [["item", "price", "discount", "balance"]]
    for i in range(150):
        rows.append([f"Item {i}", f"${rng.uniform(1, 5000):,.2f}",
                     f"{rng.randint(0, 50)}%",
                     rng.choice([f"{rng.randint(1, 900)}",
                                 f"({rng.randint(1, 900)})"])])
    add("currency_percent.csv", cat,
        "currency symbols, thousands separators, %, (accounting) negatives",
        rows_to_csv(rows))
    rows = [["measurement"]] + [[value] for value in
                                ["1.2e-5", "6.02e23", "-inf", "NaN", "1e400",
                                 "-0.0", "0.1", "3", "+5", ".5", "1_000",
                                 "0x1F", "Infinity", "1e-400"] * 10]
    add("scientific_and_special.csv", cat,
        "scientific notation, inf, NaN, overflow, underflow",
        rows_to_csv(rows))
    rows = [["created", "time", "active", "rating"]]
    for i in range(120):
        rows.append([rng.choice(["2026-10-29", "29/10/2026", "Oct 29 2026"]),
                     f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
                     rng.choice(["TRUE", "False", "yes", "0", "1"]),
                     rng.randint(1, 5)])
    add("dates_times_booleans.csv", cat,
        "dates in 3 formats, times, booleans written 5 ways",
        rows_to_csv(rows))
    rows = [["value"]] + [[value] for value in
                          ["1e308", str(10 ** 30), "0.30000000000000004",
                           "-1e308", "123456789012345678901234567890"] * 20]
    add("huge_numbers.csv", cat,
        "numbers near float limits and 30-digit integers", rows_to_csv(rows))
    rows = [["station", "temp_c", "humidity"]]
    for i in range(2000):
        rows.append([f"S{i % 20}", rng.choice([round(rng.uniform(5, 35), 1),
                                               -999]),
                     rng.choice([rng.randint(20, 90), -999, ""])])
    add("sentinel_values.csv", cat,
        "sensor data using -999 to mean 'missing'", rows_to_csv(rows))


# ------------------------------------------------------- complex CSVs

def make_complex_csvs() -> None:
    """Large, messy, realistic CSV files."""
    cat = "Complex CSVs"
    words = ["great", "broken", "fast", "late", "café", "naïve", "👍", "😡",
             "王小明", "مرحبا", "नमस्ते", 'said "wow"', "a, b and c"]
    header = ["order_id", "timestamp", "customer", "country", "price",
              "qty", "discount", "status", "rating", "review", "tags",
              "metadata"]
    rows = [header]
    for i in range(100_000):
        review = " ".join(rng.choice(words) for _ in range(rng.randint(0, 8)))
        if rng.random() < 0.01:
            review += "\nsecond line of the review"
        row = [i, f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}T"
               f"{rng.randint(0, 23):02d}:00:00",
               f"C{rng.randint(1, 20000)}",
               rng.choice(["AU", "NZ", "IN", "CN", "US", "UK"]),
               rng.choice([f"{rng.uniform(1, 500):.2f}"] * 30 + ["$12.50",
                                                                "N/A", ""]),
               rng.choice([str(rng.randint(1, 10))] * 30 + ["two", "-"]),
               rng.choice(["0", "0.1", "0.25", ""]),
               rng.choice(["shipped", "pending", "refunded", "NULL"]),
               rng.choice(["1", "2", "3", "4", "5", "?"]), review,
               ";".join(rng.sample(["new", "sale", "gift", "bulk"], 2)),
               json.dumps({"device": rng.choice(["ios", "web"]),
                           "ab": rng.randint(0, 1)})]
        rows.append(row)
        if rng.random() < 0.01:
            rows.append(list(row))                  # duplicate row
        if rng.random() < 0.002:
            rows.append(row[:rng.randint(3, 10)])   # ragged row
    add("ecommerce_100k.csv", cat,
        "100k orders: multiline text, emoji, JSON cells, 1% duplicates, "
        "ragged rows", rows_to_csv(rows))

    rows = [["respondent", "country", "q1", "q2", "q3", "comment"]]
    comments = ["很好", "ممتاز", "बहुत अच्छा", "Très bien", "😀😀😀",
                "Sehr gut, danke", "", "NA", "Great; would recommend",
                "Line one\nline two"]
    for i in range(3000):
        rows.append([i, rng.choice(["CN", "EG", "IN", "FR", "DE", "AU"])]
                    + [rng.choice(["1", "2", "3", "4", "5", "NA", ""])
                       for _ in range(3)] + [rng.choice(comments)])
    add("survey_multilingual.csv", cat,
        "3,000 survey answers in 6 languages and emoji", rows_to_csv(rows))

    part = [["id", "amount", "region"]] + [[i, i * 2.5, "North"]
                                           for i in range(50)]
    add("concatenated_exports.csv", cat,
        "three exports pasted together (header repeated mid-file)",
        rows_to_csv(part) + rows_to_csv(part) + rows_to_csv(part))

    utf8_part = "name,city\nJosé,São Paulo\nZoë,Zürich\n".encode("utf-8")
    cp1252_part = "Renée,Montréal\n“Smart” Ltd,Köln\n".encode("cp1252")
    add("mixed_encodings.csv", cat,
        "UTF-8 lines and Windows cp1252 lines in one file",
        utf8_part + cp1252_part)

    rows = [[f"col_{i}" for i in range(1000)]]
    for _ in range(200):
        rows.append([rng.choice(["", str(rng.randint(0, 99)), "x"])
                     for _ in range(1000)])
    add("wide_1000_columns.csv", cat, "1,000 columns x 200 rows",
        rows_to_csv(rows))

    rows = [["id", "a", "b", "c"]]
    for i in range(400):
        rows.append([i] + [rng.choice(["", "", "", "", "", "", "", "", "",
                                        str(rng.randint(1, 9))])
                           for _ in range(3)])
    add("sparse_90_percent_empty.csv", cat, "90% of cells empty",
        rows_to_csv(rows))
    add("all_rows_identical.csv", cat, "500 copies of the same row",
        "a,b,c\n" + "1,2,3\n" * 500)
    rows = [["id", "value"]] + [[i, rng.random()] for i in range(1000)]
    add("tab_separated_named_csv.csv", cat, "tab-separated file named .csv",
        rows_to_csv(rows, "\t"))

    path = os.path.join(OUT, "huge_1m_rows.csv")
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write("id,sensor,reading,flag,note\n")
        for i in range(1_000_000):
            file.write(f"{i},S{i % 50},{rng.uniform(0, 100):.3f},"
                       f"{rng.choice(['ok', 'ok', 'warn', ''])},n{i % 7}\n")
    SCENARIOS.append(("huge_1m_rows.csv", cat,
                      "1,000,000 rows (about 24 MB)"))


def main() -> None:
    """Build every scenario and write the index the runner reads."""
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    make_images_and_media()
    make_documents_and_archives()
    make_text_not_csv()
    make_numbers()
    make_complex_csvs()
    with open(os.path.join(OUT, "_index.json"), "w", encoding="utf-8") as f:
        json.dump(SCENARIOS, f, ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(OUT, name))
                for name in os.listdir(OUT)
                if os.path.isfile(os.path.join(OUT, name)))
    print(f"{len(SCENARIOS)} scenarios, {total / 1e6:.1f} MB in {OUT}")


if __name__ == "__main__":
    main()
