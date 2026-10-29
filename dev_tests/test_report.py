"""Tests for the case report, the evidence screen and the leaderboard."""
import os
import tempfile
import unittest

from context import SAMPLE_TEXT, make_dataset
import make_datasets
from dataset import Dataset
from investigator import Findings, Investigator
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

    def test_format_stat_keeps_numbers_honest(self):
        # -0.0 needs its own check: as a dict key it equals 0.0.
        self.assertEqual(format_stat(-0.0), "0")
        cases = {88.95: "89.0", 2.04: "2.0", 1204.0: "1,204", 0.0: "0",
                 0.035: "0.035", -0.01: "-0.01", 2e300: "2e+300",
                 1e30: "1e+30"}
        for value, shown in cases.items():
            self.assertEqual(format_stat(value), shown, value)
        text = report_for("p\n2.04\n88.95\n").to_text()
        self.assertIn("min 2.0  max 89.0", text)

    def test_sample_report_lines(self):
        text = report_for(SAMPLE_TEXT).to_text()
        for line in ["[EVIDENCE]", "  10 rows x 2 columns  (delimiter ',')",
                     "[SUSPECTS]  columns with problems",
                     "[DUPLICATES]  1 duplicate row",
                     "  line 11 duplicates line 2",
                     "[MALFORMED ROWS]  none found", "[COLUMN PROFILES]",
                     "[SUB-SCORES]  100 - 5 points per 1% of problem data",
                     "  Completeness   50.0  (10.0% of cells missing)",
                     "  Uniqueness     50.0  (10.0% of rows duplicated)",
                     "  Validity       44.4  (11.1% of numbers invalid)",
                     "VERDICT: 48/100  -  "
                     "Unreliable evidence - investigate before use"]:
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

    def test_unclosed_quote_warning(self):
        ds = make_dataset('a,b\n1,"oops\n2,3\n4,5\n')
        warning = "WARNING: a quote opened on line 2 is never closed"
        self.assertIn(warning, Report(Investigator(ds).investigate()).to_text())
        self.assertIn(warning, Report.evidence_text(ds))
        clean = report_for("a,b\n1,2\n").to_text()
        self.assertNotIn("WARNING", clean)

    def test_mostly_numeric_column_is_a_suspect(self):
        text = report_for("m\n1\n2\n3\n4\n5\n6\n7\nx\ny\nz\n").to_text()
        self.assertIn("3 not numbers", text)
        self.assertIn("e.g. 'x' (line 9)", text)

    def test_suspect_line_with_huge_counts_fits(self):
        findings = Investigator(make_dataset(
            "m\n1\n2\n3\n4\n5\n6\n7\nx\ny\nz\n")).investigate()
        profile = findings.profiles[0]
        profile.missing, profile.not_numbers = 1_234_567, 1_234_567
        for line in Report(findings).to_text().splitlines():
            self.assertLessEqual(len(line), WIDTH, line)

    def test_singular_rows_and_columns(self):
        ds = make_dataset("a\n1\n")
        self.assertEqual(str(ds), "t.csv (1 row x 1 column)")
        text = Report(Investigator(ds).investigate()).to_text()
        self.assertIn("  1 row x 1 column  (delimiter ',')", text.splitlines())

    def test_structure_problems_are_reported(self):
        text = report_for("# exported by tool v2\nid,name,score\n"
                          "1,a,5\n2,b,6\n").to_text()
        self.assertIn("WARNING:", text)
        self.assertIn("rows malformed", text)
        self.assertNotIn("Case closed", text)
        trailing = report_for("a,b,\n1,2,\n3,4,\n").to_text()
        self.assertIn("trailing delimiters ignored", trailing)
        self.assertIn("Case closed", trailing)

    def test_line_breaks_in_values_are_flattened(self):
        ds = make_dataset('id,note\n1,"top\nbottom"\n2,"top\nbottom"\n')
        self.assertIn("top bottom", Report.evidence_text(ds))
        text = Report(Investigator(ds).investigate()).to_text()
        self.assertIn("'top bottom'", text)


class TestLeaderboard(unittest.TestCase):

    def _findings(self, name, score, short):
        f = Findings(make_dataset("a\n1\n", name=name))
        f.overall, f.short_verdict = score, short
        return f

    def test_sorted_by_score_then_name(self):
        text = Report.leaderboard_text(
            [self._findings("b.csv", 90, "Minor clean-up"),
             self._findings("C.csv", 97, "Case closed"),
             self._findings("a.csv", 90, "Minor clean-up")], [])
        order = [line.split()[1] for line in text.splitlines()
                 if line[:3].strip().isdigit()]
        self.assertEqual(order, ["C.csv", "a.csv", "b.csv"])

    def test_failures_last_with_reasons(self):
        text = Report.leaderboard_text(
            [self._findings("a.csv", 90, "Minor clean-up")],
            [("empty.csv", "file is empty")])
        lines = text.splitlines()
        fail_row = next(line for line in lines
                        if "empty.csv" in line and "Could not open" in line)
        self.assertTrue(fail_row.strip().startswith("--"))
        self.assertGreater(lines.index(fail_row),
                           next(i for i, line in enumerate(lines)
                                if "a.csv" in line))
        self.assertIn("  empty.csv: file is empty", lines)

    def test_big_row_counts_stay_aligned(self):
        big = self._findings("big.csv", 90, "Minor clean-up")
        big.dataset.rows = big.dataset.rows * 1_234_567  # 1,234,567 rows
        small = self._findings("small.csv", 97, "Case closed")
        lines = Report.leaderboard_text([big, small], []).splitlines()
        header = next(line for line in lines if "Score" in line)
        score_end = header.index("Score") + len("Score")
        for line in lines:
            if "big.csv" in line or "small.csv" in line:
                self.assertIn(line[score_end - 2:score_end], ("90", "97"),
                              line)
                self.assertLessEqual(len(line), WIDTH)

    def test_leaderboard_fits_width(self):
        text = Report.leaderboard_text(
            [self._findings("x" * 30 + ".csv", 50, "Unreliable")],
            [("y" * 30 + ".csv", "couldn't be read as CSV: " + "z" * 80)])
        for line in text.splitlines():
            self.assertLessEqual(len(line), WIDTH, line)


if __name__ == "__main__":
    unittest.main()
