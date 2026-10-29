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


class TestUploads(ApiTestCase):

    def upload(self, name, data):
        return self.call("POST", "/api/cases/upload", data, {"name": name})

    def test_upload_csv(self):
        # Review Focus 1: spaces and accents in the file name.
        status, data = self.upload("ventes été 2024.csv",
                                   SAMPLE_TEXT.encode())
        self.assertEqual(status, 200, data)
        self.assertEqual(data["case"]["name"], "ventes été 2024.csv")
        self.assertEqual(data["case"]["rows"], 10)

    def test_upload_png_is_named(self):
        status, data = self.upload("photo.png",
                                   b"\x89PNG\r\n\x1a\n\x00\x00")
        self.assertEqual(status, 422)
        self.assertEqual(data["error"], "This is a PNG image, not a CSV file")

    def test_upload_too_big(self):
        with mock.patch.object(web_api, "MAX_UPLOAD_BYTES", 10):
            status, data = self.upload("big.csv", b"x" * 11)
        self.assertEqual(status, 413)
        self.assertEqual(data["error"], "Files over 200 MB can't be "
                                        "uploaded.")

    def test_safe_file_name(self):
        cases = {"../../x.csv": "x.csv", "C:\\a\\b.csv": "b.csv",
                 "": "upload.csv", "..": "upload.csv", " ": "upload.csv"}
        for name, safe in cases.items():
            self.assertEqual(web_api.safe_file_name(name), safe, name)

    def test_open_case_limit(self):
        for _ in range(21):
            self.open_sample()
        self.assertNotIn("c1", self.api.cases)
        self.assertIn("c21", self.api.cases)
        self.assertEqual(len(self.api.cases), 20)

    def test_out_of_memory(self):
        with mock.patch.object(web_api, "Dataset", side_effect=MemoryError):
            status, data = self.call("POST", "/api/cases/locker",
                                     json.dumps({"name": "t.csv"}).encode())
        self.assertEqual(status, 413)
        self.assertEqual(data["error"], "This file is too large for this "
                                        "computer's memory.")


if __name__ == "__main__":
    unittest.main()
