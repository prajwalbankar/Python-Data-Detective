"""Integration tests: the app's counts must match the generator's key."""
import os
import tempfile
import unittest

from context import APP_DIR  # noqa: F401  (puts the app on sys.path)
import errors
import make_datasets
from dataset import Dataset
from investigator import Investigator


class TestAnswerKey(unittest.TestCase):

    def test_every_dataset_matches_answer_key(self):
        folder = tempfile.mkdtemp()
        for name, key in make_datasets.build_datasets(folder).items():
            with self.subTest(name):
                path = os.path.join(folder, name)
                if "error" in key:
                    with self.assertRaises(getattr(errors, key["error"])):
                        Dataset(path)
                    continue
                ds = Dataset(path)
                f = Investigator(ds).investigate()
                got = {"rows": ds.num_rows(), "columns": ds.num_columns(),
                       "delimiter": ds.delimiter, "encoding": ds.encoding,
                       "missing": f.missing_cells,
                       "invalid": f.invalid_cells,
                       "duplicates": len(f.duplicates),
                       "malformed": len(ds.malformed_rows),
                       "blank_lines": ds.blank_lines_skipped}
                if "duplicate_lines" in key:
                    got["duplicate_lines"] = f.duplicates
                self.assertEqual(got, key)

    def test_real_datasets_load(self):
        # Expected values were counted by hand from the downloaded files
        # (sort | uniq -d, grep NA), not with the app.
        folder = os.path.join(APP_DIR, "datasets")
        iris = Dataset(os.path.join(folder, "iris.csv"))
        self.assertEqual((iris.num_rows(), iris.num_columns()), (150, 5))
        self.assertEqual(iris.blank_lines_skipped, 1)
        self.assertEqual(Investigator(iris).investigate().duplicates,
                         [(36, 11), (39, 11), (144, 103)])
        penguins = Dataset(os.path.join(folder, "penguins.csv"))
        self.assertEqual((penguins.num_rows(), penguins.num_columns()),
                         (344, 8))
        found = Investigator(penguins).investigate()
        self.assertEqual(found.missing_cells, 19)
        self.assertEqual(found.duplicates, [])

    def test_generator_is_deterministic(self):
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        make_datasets.build_datasets(a)
        make_datasets.build_datasets(b)
        self.assertEqual(len(os.listdir(a)), 7)
        for name in os.listdir(a):
            with open(os.path.join(a, name), "rb") as x, \
                 open(os.path.join(b, name), "rb") as y:
                self.assertEqual(x.read(), y.read(), name)


if __name__ == "__main__":
    unittest.main()
