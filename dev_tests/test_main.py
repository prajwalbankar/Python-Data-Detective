"""Tests for the menu-driven case desk in main.py."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from context import APP_DIR, SAMPLE_TEXT, write_file
import main

GOODBYE = "Case closed. Goodbye, detective."


class MenuTestCase(unittest.TestCase):
    """Runs main() with typed inputs against temporary folders."""

    def setUp(self):
        self.datasets = tempfile.mkdtemp()
        self.reports = os.path.join(tempfile.mkdtemp(), "reports")
        write_file(SAMPLE_TEXT, "t.csv", folder=self.datasets)

    def run_main(self, inputs):
        out = io.StringIO()
        with mock.patch.object(main, "DATASETS_DIR", self.datasets), \
             mock.patch.object(main, "REPORTS_DIR", self.reports), \
             mock.patch("builtins.input", side_effect=inputs), \
             contextlib.redirect_stdout(out):
            main.main()
        return out.getvalue()

    def report_files(self):
        if not os.path.isdir(self.reports):
            return []
        return sorted(os.listdir(self.reports))


class TestHelpers(MenuTestCase):

    def test_list_csv_files(self):
        folder = tempfile.mkdtemp()
        for name in ["b.CSV", "a.csv", "notes.txt"]:
            write_file("x\n1\n", name, folder=folder)
        self.assertEqual(main.list_csv_files(folder), ["a.csv", "b.CSV"])
        self.assertEqual(
            main.list_csv_files(os.path.join(folder, "missing")), [])

    def test_clean_path(self):
        self.assertEqual(main.clean_path('  "C:\\My Data\\f.csv" '),
                         "C:\\My Data\\f.csv")
        home = main.clean_path("~/f.csv")
        self.assertFalse(home.startswith("~"))
        self.assertTrue(home.startswith(os.path.expanduser("~")))
        with mock.patch.object(main.os, "name", "nt"):
            # Backslashes are folder separators on Windows: keep them.
            self.assertEqual(main.clean_path("C:\\My\\ Data\\f.csv"),
                             "C:\\My\\ Data\\f.csv")
        with mock.patch.object(main.os, "name", "posix"):
            # A file dragged into a macOS terminal arrives escaped.
            self.assertEqual(
                main.clean_path("/Users/me/My\\ Data/f\\ (1).csv "),
                "/Users/me/My Data/f (1).csv")

    def test_ask_yes_no(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=["maybe", "Y"]), \
             contextlib.redirect_stdout(out):
            self.assertTrue(main.ask_yes_no("Save? (y/n): "))
        self.assertIn("Please enter y or n", out.getvalue())
        with mock.patch("builtins.input", side_effect=["no"]):
            self.assertFalse(main.ask_yes_no("Save? (y/n): "))


class TestMenu(MenuTestCase):

    def test_bad_menu_input(self):
        out = self.run_main(["9", "abc", "", "0"])
        self.assertEqual(out.count("Please enter a number from 0 to 5"), 3)
        self.assertTrue(out.rstrip().endswith(GOODBYE))
        self.assertTrue(out.isascii())

    def test_chooser_bad_input(self):
        out = self.run_main(["1", "7", "x", "b", "0"])
        self.assertEqual(
            out.count("Please enter a number from 1 to 1, P or B"), 2)
        self.assertNotIn("Opening case", out)
        self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_superscript_digit_in_chooser(self):
        # '²' passes str.isdigit() but int('²') fails.
        out = self.run_main(["1", "²", "b", "0"])
        self.assertIn("Please enter a number from 1 to 1, P or B", out)
        self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_needs_open_case(self):
        out = self.run_main(["2", "3", "4", "0"])
        self.assertEqual(out.count("No case open - choose option 1 first"), 3)

    def test_open_run_save(self):
        out = self.run_main(["1", "1", "3", "4", "4", "0"])
        self.assertIn(
            "Opening case... t.csv (10 rows x 2 columns, delimiter ',')", out)
        self.assertIn("Current case: t.csv (10 rows x 2 columns)", out)
        self.assertIn("VERDICT: 48/100", out)
        self.assertIn("Report saved to", out)
        self.assertIn("(replaced the previous report)", out)
        self.assertEqual(self.report_files(), ["t_report.txt"])

    def test_save_runs_investigation(self):
        out = self.run_main(["1", "1", "4", "0"])
        self.assertNotIn("VERDICT", out)  # investigated silently
        self.assertEqual(self.report_files(), ["t_report.txt"])

    def test_bad_dataset_reason(self):
        write_file("", "e.csv", folder=self.datasets)
        out = self.run_main(["1", "1", "0"])
        self.assertIn("Could not open case: file is empty", out)
        self.assertIn("Current case: none", out.split("Could not open")[-1])

    def test_quoted_path_with_spaces(self):
        # Review Focus 2: Windows "Copy as path" adds quotes.
        folder = os.path.join(tempfile.mkdtemp(), "my data")
        os.makedirs(folder)
        path = write_file(SAMPLE_TEXT, "x y.csv", folder=folder)
        out = self.run_main(["1", "P", f'"{path}"', "0"])
        self.assertIn("Opening case... x y.csv", out)

    def test_odd_paths_do_not_crash(self):
        # A lone quote, '?' or '*' is an invalid file name on Windows.
        for typed in ['"', "?", "*", '"C:\\half copied.csv']:
            with self.subTest(typed=typed):
                out = self.run_main(["1", "P", typed, "0"])
                self.assertIn("Could not open case:", out)
                self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_empty_path(self):
        out = self.run_main(["1", "P", "   ", "0"])
        self.assertIn("No path entered", out)
        self.assertNotIn("Could not open case", out)

    def test_long_messages_fit_width(self):
        path = os.path.join(tempfile.mkdtemp(), "a_very_long_folder_name",
                            "and_an_even_longer_file_name_for_testing.csv")
        out = self.run_main(["1", "P", path, "0"])
        self.assertIn("Could not open case:", out)
        for line in out.splitlines():
            self.assertLessEqual(len(line), 64, line)

    def test_empty_locker(self):
        os.remove(os.path.join(self.datasets, "t.csv"))
        out = self.run_main(["1", "B", "0"])
        self.assertIn("The evidence locker is empty", out)

    def test_eof_in_chooser(self):
        # Review Focus 4: Ctrl+D inside a nested prompt.
        out = self.run_main(["1", EOFError()])
        self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_ctrl_c_at_menu(self):
        out = self.run_main([KeyboardInterrupt()])
        self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_ctrl_c_at_path_prompt(self):
        out = self.run_main(["1", "P", KeyboardInterrupt()])
        self.assertTrue(out.rstrip().endswith(GOODBYE))

    def test_ctrl_c_at_yes_no_prompt(self):
        out = self.run_main(["5", KeyboardInterrupt()])
        self.assertIn("CASE BOARD", out)
        self.assertTrue(out.rstrip().endswith(GOODBYE))
        self.assertEqual(self.report_files(), [])

    def test_save_error_reported(self):
        self.reports = write_file("not a folder", "reports_file")
        out = self.run_main(["1", "1", "4", "0"])
        self.assertIn("Could not save report:", out)
        self.assertTrue(out.rstrip().endswith(GOODBYE))


class TestInvestigateAll(MenuTestCase):

    def test_all_board_and_save(self):
        write_file("a,b\n1,x\n2,y\n", "good.csv", folder=self.datasets)
        write_file("", "e.csv", folder=self.datasets)
        out = self.run_main(["5", "y", "0"])
        self.assertIn("CASE BOARD", out)
        self.assertIn("  e.csv: file is empty", out.splitlines())
        self.assertEqual(self.report_files(),
                         ["good_report.txt", "leaderboard.txt",
                          "t_report.txt"])

    def test_all_saved_message_is_singular(self):
        out = self.run_main(["5", "y", "0"])
        self.assertIn("Saved 1 case report and leaderboard.txt", out)

    def test_all_no_save(self):
        out = self.run_main(["5", "n", "0"])
        self.assertIn("CASE BOARD", out)
        self.assertEqual(self.report_files(), [])

    def test_all_keeps_current_case(self):
        out = self.run_main(["1", "1", "5", "n", "0"])
        self.assertIn("CASE BOARD", out)
        status = [line for line in out.splitlines()
                  if "Current case:" in line]
        self.assertEqual(status[-1],
                         "  Current case: t.csv (10 rows x 2 columns)")

    def test_all_empty_locker(self):
        os.remove(os.path.join(self.datasets, "t.csv"))
        out = self.run_main(["5", "0"])
        self.assertIn("The evidence locker is empty", out)
        self.assertNotIn("CASE BOARD", out)
        self.assertNotIn("Please enter y or n", out)


class TestRealProgram(unittest.TestCase):

    def run_program(self, typed, encoding="utf-8"):
        return subprocess.run(
            [sys.executable, os.path.join(APP_DIR, "main.py")],
            input=typed, cwd=tempfile.mkdtemp(), capture_output=True,
            text=True, timeout=60, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": encoding})

    def test_unprintable_data_does_not_crash(self):
        # Output that can't show the data's characters (e.g. Windows
        # output redirected to a file) must not end in a traceback.
        path = write_file("name\n王小明\n", "chinese.csv")
        result = self.run_program(f"1\nP\n{path}\n2\n3\n0\n",
                                  encoding="ascii")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Rows: 1", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_runs_from_other_directory(self):
        # Review Focus 1: the tutor runs it from some other folder.
        result = self.run_program("1\n1\n3\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("VERDICT:", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_all_from_other_directory(self):
        result = self.run_program("5\nn\n0\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("CASE BOARD", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
