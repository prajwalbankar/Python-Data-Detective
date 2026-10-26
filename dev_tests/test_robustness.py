"""Robustness tests: awkward files, random files and random typing.

Whatever a marker throws at the program, it must either work or explain
the problem politely: no traceback, and no line of our own text wider
than WIDTH.
"""
import contextlib
import io
import os
import random
import tempfile
import unittest
from unittest import mock

from context import APP_DIR, SAMPLE_TEXT, write_file
import main
import make_datasets
from dataset import Dataset
from errors import DatasetError
from investigator import Investigator
from report import WIDTH, Report

# Awkward but realistic files. Each one must load and report cleanly,
# or be refused with a DatasetError.
EDGE_CASES = {
    "trailing_delimiter": "a,b,\n1,2,\n3,4,\n",
    "duplicate_headers": "a,a,b\n1,2,3\n4,5,6\n",
    "all_blank_header": ",,,\n1,2,3,4\n",
    "bom_semicolon": "﻿a;b\n1;2\n",
    "tab": "a\tb\n1\t2\n3\t4\n",
    "pipe": "a|b\n1|2\n3|4\n",
    "cr_only_line_endings": "a,b\r1,2\r\r3,4\r",
    "no_trailing_newline": "a,b\n1,2",
    "escaped_quotes": 'a,b\n1,"He said ""hi"""\n2,"x"\n',
    "odd_numbers": "n\n1e400\n-0\n+.5\n.5\n5.\n0x1A\n1_000\n 3 \nNaN\n"
                   "Infinity\n-inf\n١٢٣\n",
    "300_columns": ",".join(f"c{i}" for i in range(300)) + "\n"
                   + ",".join(str(i) for i in range(300)) + "\n",
    "long_values": "a,b\n" + "x" * 5000 + ",1\n" + "y" * 5000 + ",2\n",
    "long_header_name": "z" * 10000 + ",b\n1,2\n",
    "emoji_cjk_rtl": "名前,\U0001F600,שם\n"
                     "王小明,\U0001F600,שלום\n",
    "single_cell": "a\n1\n",
    "all_identical_rows": "a,b\n" + "1,2\n" * 100,
    "all_missing": "a,b\nNA,\n,null\n?,-\n",
    "booleans_dates_percent": "f,d,p\nTrue,2024-01-01,50%\nfalse,1/2/24,1%\n",
    "header_then_blank_lines": "a,b\n\n\n\n",
    "utf16": "a,b\r\n1,2\r\n".encode("utf-16"),
    "cp1252": "n\n“q” €\n".encode("cp1252"),
    "utf8_with_bad_byte": "n\ncafé\n".encode("utf-8") + b"\xff\n",
    "nul_byte": b"a,b\n1,2\x00\n",
    "mixed_delimiters": "a,b;c\n1,2;3\n4;5,6\n",
    "many_multiline_values": "id,n\n" + "".join(f'{i},"l1\nl2"\n'
                                                 for i in range(50)),
    "huge_field": "a\n" + "q" * 200000 + "\n",
    "multiline_header": '"head\ner",b\n1,2\n',
    "only_delimiters": "a,b,c\n,,\n,,\n",
    "headerless": "5.1,3.5,1.4,0.2,Iris-setosa\n4.9,3.0,1.4,0.2,Iris-setosa\n",
    "title_line": "# exported by tool v2\nid,name,score\n1,a,5\n2,b,6\n",
    "unclosed_quote_at_end": 'a,b\n1,2\n3,"oops',
    "negative_zero": "v\n-0.0\n-0.0\n",
    "tiny_and_huge": "v\n1e-300\n1e300\n-1e300\n",
    "control_characters": "a\n\x1b[31mred\x07\n",
}

MISSING = ["", "NA", "n/a", "null", "None", "nan", "-", "?"]
NUMBERS = ["1", "-2.5", "3e4", "+7", " 8 ", "1,204", "$15", "inf", "0x1F"]
WORDS = ["North", "Café", "王", "\U0001F600", "a b", "x;y", "q|r",
         'say "hi"', "line\nbreak", "\t", "  "]


def check_pipeline(test, path):
    """Load, investigate and report path; assert it's handled politely."""
    try:
        dataset = Dataset(path)
    except DatasetError:
        return None
    findings = Investigator(dataset).investigate()
    for text in (Report(findings).to_text(), Report.evidence_text(dataset),
                 Report.leaderboard_text([findings], [("x.csv", "why")])):
        for line in text.splitlines():
            test.assertLessEqual(len(line), WIDTH, f"{path}: {line!r}")
    test.assertTrue(0 <= findings.overall <= 100)
    return findings


def random_csv(rng):
    """Build a random, often broken, CSV file as bytes."""
    delimiter = rng.choice([",", ";", "\t", "|"])
    terminator = rng.choice(["\n", "\r\n", "\r"])
    columns = rng.randint(1, 6)
    lines = [delimiter.join(rng.choice(["id", "name", "", "2020", "x y"])
                            for _ in range(columns))]
    for _ in range(rng.randint(0, 25)):
        width = columns + rng.choice([0, 0, 0, -1, 1, 3])
        cells = []
        for _ in range(max(width, 0)):
            cell = rng.choice([rng.choice(MISSING), rng.choice(NUMBERS),
                               rng.choice(WORDS)])
            if rng.random() < 0.2:
                cell = '"' + cell.replace('"', '""') + '"'
            if rng.random() < 0.03:
                cell = '"' + cell     # a stray, never-closed quote
            cells.append(cell)
        lines.append(delimiter.join(cells))
        if rng.random() < 0.1:
            lines.append("")
    text = terminator.join(lines) + rng.choice(["", terminator])
    encoding = rng.choice(["utf-8", "utf-8-sig", "utf-16", "cp1252"])
    data = text.encode(encoding, errors="replace")
    if rng.random() < 0.03:
        data += b"\x00"
    return data


class TestEdgeCases(unittest.TestCase):

    def test_every_edge_case_is_handled(self):
        folder = tempfile.mkdtemp()
        for name, content in EDGE_CASES.items():
            with self.subTest(name):
                check_pipeline(self, write_file(content, name + ".csv",
                                                folder=folder))

    def test_edge_case_verdicts(self):
        folder = tempfile.mkdtemp()

        def verdict(name):
            path = write_file(EDGE_CASES[name], name + ".csv",
                              folder=folder)
            return Investigator(Dataset(path)).investigate().short_verdict

        self.assertEqual(verdict("trailing_delimiter"), "Case closed")
        self.assertNotEqual(verdict("title_line"), "Case closed")
        self.assertNotEqual(verdict("all_identical_rows"), "Case closed")


class TestFuzz(unittest.TestCase):

    def test_random_files_never_crash(self):
        rng = random.Random(9001)
        folder = tempfile.mkdtemp()
        for number in range(400):
            data = random_csv(rng)
            with self.subTest(number=number):
                check_pipeline(self, write_file(data, f"f{number}.csv",
                                                folder=folder))

    def test_random_typing_never_crashes(self):
        rng = random.Random(42)
        datasets = tempfile.mkdtemp()
        write_file(SAMPLE_TEXT, "t.csv", folder=datasets)
        write_file("", "empty.csv", folder=datasets)
        reports = os.path.join(tempfile.mkdtemp(), "reports")
        vocabulary = ["0", "1", "2", "3", "4", "5", "9", "", " ", "x", "P",
                      "p", "B", "b", "y", "n", "yes", "²", "１",
                      "-1", "01", '"', "?", "~", "CON" if os.name == "nt"
                      else "/dev/null", os.path.join(datasets, "t.csv")]
        for session in range(150):
            typed = [rng.choice(vocabulary) for _ in range(rng.randint(1, 25))]
            ending = rng.choice([EOFError(), KeyboardInterrupt()])
            out = io.StringIO()
            with self.subTest(session=session, typed=typed), \
                 mock.patch.object(main, "DATASETS_DIR", datasets), \
                 mock.patch.object(main, "REPORTS_DIR", reports), \
                 mock.patch("builtins.input",
                            side_effect=typed + [ending]), \
                 contextlib.redirect_stdout(out):
                main.main()
            self.assertTrue(out.getvalue().rstrip().endswith(
                "Case closed. Goodbye, detective."))


class TestShippedDatasets(unittest.TestCase):

    def test_shipped_files_match_the_generator(self):
        # Catches anyone editing a generated dataset by hand, which would
        # make the answer key wrong.
        folder = tempfile.mkdtemp()
        make_datasets.build_datasets(folder)
        shipped = os.path.join(APP_DIR, "datasets")
        for name in os.listdir(folder):
            with open(os.path.join(folder, name), "rb") as fresh, \
                 open(os.path.join(shipped, name), "rb") as kept:
                self.assertEqual(fresh.read(), kept.read(), name)


if __name__ == "__main__":
    unittest.main()
