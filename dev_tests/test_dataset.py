"""Tests for loading CSV files into a Dataset."""
import os
import tempfile
import unittest

from context import make_dataset, write_file
from dataset import Dataset
from errors import EmptyDatasetError, UnreadableFileError


class TestDatasetLoading(unittest.TestCase):

    def test_loads_simple_csv(self):
        ds = make_dataset("a,b\n1,2\n3,4\n")
        self.assertEqual(ds.header, ["a", "b"])
        self.assertEqual(ds.rows, [["1", "2"], ["3", "4"]])
        self.assertEqual(ds.line_numbers, [2, 3])
        self.assertEqual(ds.delimiter, ",")
        self.assertEqual(ds.encoding, "utf-8")
        self.assertEqual(ds.num_rows(), 2)
        self.assertEqual(ds.num_columns(), 2)
        self.assertEqual(str(ds), "t.csv (2 rows x 2 columns)")

    def test_strips_bom(self):
        ds = make_dataset("﻿id,name\n1,x\n")
        self.assertEqual(ds.header[0], "id")

    def test_detects_semicolon(self):
        ds = make_dataset('id;city\n1;"Sydney, NSW"\n2;Perth\n')
        self.assertEqual(ds.delimiter, ";")
        self.assertEqual(ds.rows[0], ["1", "Sydney, NSW"])

    def test_line_break_in_quoted_field(self):
        ds = make_dataset('id,note\n1,"two\nlines"\n2,ok\n')
        self.assertEqual(ds.rows[0][1], "two\nlines")
        self.assertEqual(ds.line_numbers, [2, 4])

    def test_skips_blank_lines(self):
        ds = make_dataset("a,b\n\n1,2\n   \n3,4\n")
        self.assertEqual(ds.num_rows(), 2)
        self.assertEqual(ds.blank_lines_skipped, 2)
        self.assertEqual(ds.line_numbers, [3, 5])

    def test_all_empty_fields_is_data(self):
        ds = make_dataset("a,b\n,\n1,2\n")
        self.assertEqual(ds.num_rows(), 2)

    def test_crlf_line_endings(self):
        # Review Focus 3: files saved by Excel or on Windows.
        ds = make_dataset("a,b\r\n1,2\r\n\r\n3,4\r\n")
        self.assertEqual(ds.line_numbers, [2, 4])
        self.assertEqual(ds.blank_lines_skipped, 1)

    def test_single_column(self):
        # Review Focus 5: the Sniffer can't pick a delimiter here.
        ds = make_dataset("score\n1.5\n2\n3\n")
        self.assertEqual(ds.num_columns(), 1)
        self.assertEqual(ds.delimiter, ",")
        self.assertEqual(ds.num_rows(), 3)

    def test_pads_and_trims(self):
        ds = make_dataset("a,b,c\n1,2\n1,2,3,4\n")
        self.assertEqual(ds.rows, [["1", "2", ""], ["1", "2", "3"]])
        self.assertEqual(ds.malformed_rows, [(2, 2), (3, 4)])

    def test_blank_header_names(self):
        ds = make_dataset("id,,score\n1,x,2\n")
        self.assertEqual(ds.header, ["id", "column_2", "score"])

    def test_latin1_fallback(self):
        ds = make_dataset("name\ncafé\n", encoding="latin-1")
        self.assertEqual(ds.encoding, "latin-1")
        self.assertEqual(ds.rows[0][0], "café")

    def test_column_values_and_preview(self):
        ds = make_dataset("a,b\n1,x\n2,y\n3,z\n")
        self.assertEqual(ds.column_values(1), ["x", "y", "z"])
        self.assertEqual(ds.preview(2), [["1", "x"], ["2", "y"]])


class TestDatasetErrors(unittest.TestCase):

    def assert_error(self, error_class, message, path):
        with self.assertRaises(error_class) as caught:
            Dataset(path)
        self.assertEqual(str(caught.exception), message)

    def test_empty_file(self):
        self.assert_error(EmptyDatasetError, "file is empty", write_file(""))

    def test_only_blank_lines(self):
        self.assert_error(EmptyDatasetError, "file is empty",
                          write_file("\n\n"))

    def test_header_only(self):
        self.assert_error(EmptyDatasetError,
                          "file has a header but no data rows",
                          write_file("a,b\n"))

    def test_binary_file(self):
        path = write_file(b"\x89PNG\r\n\x1a\n\x00\x00")
        self.assert_error(UnreadableFileError,
                          "doesn't look like a plain text CSV", path)

    def test_missing_file(self):
        path = os.path.join(tempfile.mkdtemp(), "nope.csv")
        self.assert_error(UnreadableFileError, f"no file at '{path}'", path)

    def test_folder(self):
        path = tempfile.mkdtemp()
        self.assert_error(UnreadableFileError,
                          f"'{path}' is a folder, not a file", path)

    def test_csv_parse_error(self):
        path = write_file("a\n" + "x" * 200000 + "\n")
        with self.assertRaises(UnreadableFileError) as caught:
            Dataset(path)
        self.assertTrue(
            str(caught.exception).startswith("couldn't be read as CSV: "))


if __name__ == "__main__":
    unittest.main()
