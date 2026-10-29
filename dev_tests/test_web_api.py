"""Tests for the web UI's API (DetectiveApi), called without a network."""
import json
import os
import tempfile
import unittest
from unittest import mock

from context import SAMPLE_TEXT, write_file
import web_api
from web_api import DetectiveApi


class ApiTestCase(unittest.TestCase):
    """Builds a DetectiveApi over temporary folders."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.datasets = os.path.join(self.base, "datasets")
        self.reports = os.path.join(self.base, "reports")
        self.uploads = os.path.join(self.base, "uploads")
        os.makedirs(self.datasets)
        os.makedirs(self.uploads)
        write_file(SAMPLE_TEXT, "t.csv", folder=self.datasets)
        write_file("", "e.csv", folder=self.datasets)
        self.api = DetectiveApi(self.datasets, self.reports, self.uploads,
                                self.base)

    def call(self, method, path, body=b"", query=None):
        """Send one request; return (status, parsed JSON)."""
        response = self.api.handle(method, path, query or {}, body)
        return response.status, json.loads(response.body)

    def open_sample(self):
        """Open t.csv from the locker and return its case id."""
        status, data = self.call("POST", "/api/cases/locker",
                                 json.dumps({"name": "t.csv"}).encode())
        self.assertEqual(status, 200, data)
        return data["case"]["id"]


class TestLockerAndEvidence(ApiTestCase):

    def test_locker_lists_csv_files(self):
        status, data = self.call("GET", "/api/locker")
        self.assertEqual(status, 200)
        names = [d["name"] for d in data["datasets"]]
        self.assertEqual(names, ["e.csv", "t.csv"])
        size = os.path.getsize(os.path.join(self.datasets, "t.csv"))
        self.assertEqual(data["datasets"][1]["bytes"], size)

    def test_open_from_locker(self):
        status, data = self.call("POST", "/api/cases/locker",
                                 json.dumps({"name": "t.csv"}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(data["case"], {
            "id": "c1", "name": "t.csv", "rows": 10, "columns": 2,
            "delimiter": "','", "encoding": "utf-8", "warnings": []})

    def test_open_refused_file_reports_reason(self):
        status, data = self.call("POST", "/api/cases/locker",
                                 json.dumps({"name": "e.csv"}).encode())
        self.assertEqual((status, data), (422, {"error": "File is empty"}))

    def test_unknown_or_unsafe_locker_names(self):
        for name in ["nope.csv", "../t.csv", "a/b.csv"]:
            with self.subTest(name):
                status, data = self.call(
                    "POST", "/api/cases/locker",
                    json.dumps({"name": name}).encode())
                self.assertEqual(status, 404)
                self.assertEqual(
                    data["error"], f"There's no dataset called '{name}' in "
                                   "the evidence locker.")

    def test_evidence(self):
        case_id = self.open_sample()
        status, data = self.call("GET", f"/api/cases/{case_id}/evidence")
        self.assertEqual(status, 200)
        self.assertEqual(data["header"], ["a", "b"])
        self.assertEqual(data["preview"][0], ["1", "x"])
        self.assertEqual(len(data["preview"]), 5)
        self.assertEqual(data["blank_lines_skipped"], 0)
        self.assertIs(data["trailing_delimiters"], False)
        self.assertEqual(data["case"]["id"], case_id)

    def test_unknown_case(self):
        status, data = self.call("GET", "/api/cases/c99/evidence")
        self.assertEqual(status, 404)
        self.assertEqual(data["error"], "This case is no longer open. Open "
                                        "it again from the evidence locker.")

    def test_unknown_path_and_method(self):
        self.assertEqual(self.call("GET", "/api/nothing"),
                         (404, {"error": "Not found."}))
        self.assertEqual(self.call("DELETE", "/api/locker"),
                         (405, {"error": "Method not allowed."}))

    def test_unexpected_error_is_hidden(self):
        with mock.patch.object(web_api, "Dataset",
                               side_effect=RuntimeError("boom")), \
             mock.patch.object(web_api.traceback, "print_exc"):
            status, data = self.call("POST", "/api/cases/locker",
                                     json.dumps({"name": "t.csv"}).encode())
        self.assertEqual(status, 500)
        self.assertEqual(data["error"], "Something went wrong. Details are "
                                        "in the terminal.")


if __name__ == "__main__":
    unittest.main()
