"""Tests for the case report, the evidence screen and the leaderboard."""
import os
import tempfile
import unittest

from context import SAMPLE_TEXT, make_dataset
import make_datasets
from dataset import Dataset
from investigator import Investigator
from report import WIDTH, Report, format_stat, shorten


def report_for(text):
    """Investigate CSV text and return its report."""
    return Report(Investigator(make_dataset(text)).investigate())


class TestCaseReport(unittest.TestCase):

    def test_shorten_and_format_stat(self):
        self.assertEqual(shorten("abcdefghijklmnop", 12), "abcdefghij..")
        self.assertEqual(shorten("short", 12), "short")
        self.assertEqual([format_stat(v) for v in (1.0, 100.5, 24.13, 2.0)],
                         ["1", "100.5", "24.1", "2"])

    def test_sample_report_lines(self):
        text = report_for(SAMPLE_TEXT).to_text()
        for line in ["[EVIDENCE]", "  10 rows x 2 columns  (delimiter ',')",
                     "[SUSPECTS]  columns with problems",
                     "[DUPLICATES]  1 duplicate row",
                     "  line 11 duplicates line 2",
                     "[MALFORMED ROWS]  none found", "[COLUMN PROFILES]",
                     "  Completeness  90.0%  (2 of 20 cells missing)",
                     "  Uniqueness    90.0%  (1 of 10 rows duplicated)",
                     "  Validity      88.9%  (1 of 9 numeric values invalid)",
                     "VERDICT: 90/100  -  Minor clean-up needed"]:
            self.assertIn(line, text.splitlines())
        self.assertIn("'bad' (line 9)", text)
        self.assertRegex(text, r"CASE FILE #\d{8}-\d{4}")
        self.assertTrue(text.isascii())

    def test_detail_lines_are_spaced_and_aligned(self):
        lines = report_for(SAMPLE_TEXT).to_text().splitlines()
        self.assertIn(" " * 16 + "e.g. 'bad' (line 9)", lines)
        self.assertIn(" " * 16 + "8 unique, most common 'x' (2)", lines)
        evidence = Report.evidence_text(make_dataset(SAMPLE_TEXT))
        self.assertIn("  Columns: a, b", evidence.splitlines())

    def test_clean_report_messages(self):
        text = report_for("a,b\n1,x\n2,y\n").to_text()
        self.assertIn("No suspects - every column checks out.", text)
        self.assertIn("[DUPLICATES]  none found", text)

    def test_lines_fit_width(self):
        folder = tempfile.mkdtemp()
        make_datasets.build_datasets(folder)
        long_text = ("a_really_long_column_name_that_goes_on,b\n"
                     + "1,x\n" * 9 + ("y" * 40) + ",z\n")
        texts = [report_for(long_text).to_text()]
        for name in ["messy_sales.csv", "broken_rows.csv",
                     "tricky_addresses.csv"]:
            ds = Dataset(os.path.join(folder, name))
            texts.append(Report(Investigator(ds).investigate()).to_text())
            texts.append(Report.evidence_text(ds))
        for text in texts:
            for line in text.splitlines():
                self.assertLessEqual(len(line), WIDTH, line)

    def test_save_and_replace(self):
        report = report_for(SAMPLE_TEXT)
        folder = os.path.join(tempfile.mkdtemp(), "new")
        path, replaced = report.save(folder)
        self.assertTrue(path.endswith("t_report.txt"))
        self.assertFalse(replaced)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), report.to_text())
        self.assertTrue(report.save(folder)[1])

    def test_evidence_preview(self):
        wide = (",".join(f"col{i}" for i in range(8)) + "\n"
                + ("".join("x" * 20 + "," for _ in range(7)) + "end\n") * 7)
        text = Report.evidence_text(make_dataset(wide))
        self.assertIn("more columns)", text)
        self.assertIn("xxxxxxxxxx..", text)
        # The 8th column ("end") doesn't fit, so it's cut off.
        self.assertNotIn("end", text.split("Preview")[-1])
        latin = make_dataset("name\ncafé\n", encoding="latin-1")
        self.assertIn("Encoding: latin-1", Report.evidence_text(latin))

    def test_line_breaks_in_values_are_flattened(self):
        ds = make_dataset('id,note\n1,"top\nbottom"\n2,"top\nbottom"\n')
        self.assertIn("top bottom", Report.evidence_text(ds))
        text = Report(Investigator(ds).investigate()).to_text()
        self.assertIn("'top bottom'", text)


if __name__ == "__main__":
    unittest.main()
