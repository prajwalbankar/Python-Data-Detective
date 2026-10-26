"""Tests for the investigator's rules, column profiles and scores."""
import datetime
import unittest

from context import SAMPLE_TEXT, make_dataset
from investigator import Investigator


def profile(values):
    """Profile a one-column dataset built from a list of values."""
    dataset = make_dataset("v\n" + "\n".join(values) + "\n")
    return Investigator(dataset)._profile_column(0)


class TestRules(unittest.TestCase):

    def test_is_missing(self):
        for v in ["", "  ", "NA", "n/a", "N/A", "null", "NULL", "None",
                  "nan", "NaN", "-", "?", " na "]:
            self.assertTrue(Investigator.is_missing(v), v)
        for v in ["0", "--", "N.A.", "none of them", "x"]:
            self.assertFalse(Investigator.is_missing(v), v)

    def test_is_number(self):
        for v in ["3.5", "-2", "+5", "1e3", " 42 ", "0"]:
            self.assertTrue(Investigator.is_number(v), v)
        for v in ["inf", "-inf", "nan", "1,204", "$15", "twelve", ""]:
            self.assertFalse(Investigator.is_number(v), v)

    def test_verdict_bands(self):
        cases = {100: "Case closed", 95: "Case closed",
                 94: "Minor clean-up", 85: "Minor clean-up",
                 84: "Needs cleaning", 70: "Needs cleaning",
                 69: "Unreliable", 0: "Unreliable"}
        for score, short in cases.items():
            self.assertEqual(Investigator.verdict_for(score)[0], short)
        self.assertEqual(Investigator.verdict_for(94)[1],
                         "Minor clean-up needed")


class TestColumnProfile(unittest.TestCase):

    def test_exactly_80_percent_is_numeric(self):
        p = profile(["1", "2", "3", "4", "x"])
        self.assertEqual(p.kind, "numeric")
        self.assertEqual(p.invalid, 1)
        self.assertEqual(p.invalid_examples, [("x", 6)])
        self.assertEqual(p.stats, (1.0, 4.0, 2.5, 2.5))

    def test_below_threshold_is_text(self):
        p = profile(["1", "2", "3", "x", "y"])
        self.assertEqual(p.kind, "text")
        self.assertEqual(p.invalid, 0)
        self.assertEqual(p.unique_count, 5)
        self.assertEqual(p.most_common, ("1", 1))

    def test_missing_is_not_invalid(self):
        p = profile(["1", "NA", "2", "?"])
        self.assertEqual(p.kind, "numeric")
        self.assertEqual(p.missing, 2)
        self.assertEqual(p.invalid, 0)
        self.assertEqual(p.stats, (1.0, 2.0, 1.5, 1.5))

    def test_empty_column(self):
        p = profile(["NA", "null"])
        self.assertEqual(p.kind, "empty")
        self.assertEqual(p.missing, 2)
        self.assertIsNone(p.stats)
        self.assertIsNone(p.most_common)

    def test_examples_capped_in_file_order(self):
        values = [str(i) for i in range(1, 21)] + ["a", "b", "c", "d"]
        p = profile(values)
        self.assertEqual(p.invalid, 4)
        self.assertEqual(len(p.invalid_examples), 3)
        self.assertEqual(p.invalid_examples[0], ("a", 22))

    def test_text_values_are_stripped(self):
        p = profile(["North", "South", "North", " North "])
        self.assertEqual(p.unique_count, 2)
        self.assertEqual(p.most_common, ("North", 3))


class TestInvestigate(unittest.TestCase):

    def test_sample_scores(self):
        f = Investigator(make_dataset(SAMPLE_TEXT)).investigate()
        self.assertEqual((f.total_cells, f.missing_cells), (20, 2))
        self.assertEqual((f.numeric_cells, f.invalid_cells), (9, 1))
        self.assertEqual(f.duplicates, [(11, 2)])
        self.assertEqual((f.completeness, f.uniqueness, f.validity),
                         (90.0, 90.0, 88.9))
        self.assertEqual(f.overall, 90)
        self.assertEqual(f.short_verdict, "Minor clean-up")
        self.assertEqual(f.verdict, "Minor clean-up needed")
        self.assertIsInstance(f.investigated_at, datetime.datetime)
        self.assertEqual(len(f.profiles), 2)

    def test_duplicates_ignore_spaces_but_not_case(self):
        f = Investigator(make_dataset(
            "a,b\n1,x\nNorth,1\n 1 , x \nnorth,1\n")).investigate()
        self.assertEqual(f.duplicates, [(4, 2)])

    def test_validity_100_without_numeric_columns(self):
        f = Investigator(make_dataset("name\nAnn\nBob\n")).investigate()
        self.assertEqual((f.numeric_cells, f.validity), (0, 100.0))

    def test_overall_rounds_half_up(self):
        # 20 unique rows, 1 invalid number -> 40 + 30 + 28.5 = 98.5 -> 99
        text = ("n,id\n" + "".join(f"{i},r{i}\n" for i in range(19))
                + "oops,r19\n")
        f = Investigator(make_dataset(text)).investigate()
        self.assertEqual(f.overall, 99)

    def test_padded_cells_count_as_missing(self):
        f = Investigator(make_dataset("a,b,c\n1,2\n3,4,5\n")).investigate()
        self.assertEqual(f.missing_cells, 1)


if __name__ == "__main__":
    unittest.main()
