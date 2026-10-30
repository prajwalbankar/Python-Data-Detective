"""Tests for the investigator's rules, column profiles and scores."""
import datetime
import math
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

    def test_mostly_numbers_are_flagged(self):
        # 70% numbers: below the 80% numeric threshold, so the column is
        # text, but the 3 values that aren't numbers are still reported.
        p = profile(["1", "2", "3", "4", "5", "6", "7", "x", "y", "z"])
        self.assertEqual(p.kind, "text")
        self.assertEqual((p.invalid, p.not_numbers), (0, 3))
        self.assertEqual(p.invalid_examples[0], ("x", 9))

    def test_mostly_text_is_not_flagged(self):
        p = profile(["1", "2", "x", "y", "z"])
        self.assertEqual(p.not_numbers, 0)

    def test_missing_is_not_invalid(self):
        p = profile(["1", "NA", "2", "?"])
        self.assertEqual(p.kind, "numeric")
        self.assertEqual(p.missing, 2)
        self.assertEqual(p.invalid, 0)
        self.assertEqual(p.stats, (1.0, 2.0, 1.5, 1.5))

    def test_median_near_the_float_limit(self):
        # Adding the two middle values overflows to inf, but their median
        # (like their mean) is an ordinary number below the limit.
        for values in [["1.5e308", "1.6e308"], ["-1.7e308", "-1.6e308"]]:
            with self.subTest(values):
                low, high, mean, median = profile(values).stats
                self.assertTrue(math.isfinite(median))
                self.assertEqual(median, mean)

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
        # 10% missing, 10% duplicated, 11.1% invalid; each 1% costs 5.
        self.assertEqual((f.completeness, f.uniqueness, f.validity),
                         (50.0, 50.0, 44.4))
        self.assertEqual(f.overall, 48)
        self.assertEqual(f.short_verdict, "Unreliable")
        self.assertEqual(f.verdict,
                         "Unreliable evidence - investigate before use")
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
        # 20 unique rows, 1 invalid number (5%) -> validity 75
        # -> 40 + 30 + 22.5 = 92.5 -> 93
        text = ("n,id\n" + "".join(f"{i},r{i}\n" for i in range(19))
                + "oops,r19\n")
        f = Investigator(make_dataset(text)).investigate()
        self.assertEqual(f.validity, 75.0)
        self.assertEqual(f.overall, 93)

    def test_malformed_rows_lower_validity(self):
        # 1 of 4 rows has an extra field: 25% malformed -> validity 0
        f = Investigator(make_dataset(
            "a,b\n1,2,3\n4,5\n6,7\n8,9\n")).investigate()
        self.assertEqual(f.malformed_percent, 25.0)
        self.assertEqual(f.validity, 0.0)
        self.assertEqual(f.overall, 70)

    def test_sub_scores_never_below_zero(self):
        # 2 of 3 rows are duplicates (66.7%) -> 100 - 333 -> 0
        f = Investigator(make_dataset("a,b\n1,x\n1,x\n1,x\n")).investigate()
        self.assertEqual(f.uniqueness, 0.0)
        self.assertEqual(f.overall, 70)

    def test_padded_cells_count_as_missing(self):
        f = Investigator(make_dataset("a,b,c\n1,2\n3,4,5\n")).investigate()
        self.assertEqual(f.missing_cells, 1)


if __name__ == "__main__":
    unittest.main()
