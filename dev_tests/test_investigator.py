"""Tests for the investigator's rules, column profiles and scores."""
import unittest

from context import make_dataset
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


if __name__ == "__main__":
    unittest.main()
