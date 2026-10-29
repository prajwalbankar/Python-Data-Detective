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


class TestFindingsAndReports(ApiTestCase):

    def investigate(self, case_id):
        status, data = self.call("POST", f"/api/cases/{case_id}/investigate")
        self.assertEqual(status, 200, data)
        return data

    def upload(self, name, text):
        status, data = self.call("POST", "/api/cases/upload", text.encode(),
                                 {"name": name})
        self.assertEqual(status, 200, data)
        return data["case"]["id"]

    def test_investigate_sample(self):
        data = self.investigate(self.open_sample())
        self.assertEqual(data["score"], 48)
        self.assertEqual(data["band"], "bad")
        self.assertEqual(data["verdict"],
                         "Unreliable evidence - investigate before use")
        self.assertEqual(data["duplicates"],
                         {"total": 1, "items": [{"line": 11, "original": 2}]})
        self.assertEqual(data["sub_scores"][0],
                         {"name": "Completeness", "score": 50.0,
                          "note": "10.0% of cells missing"})
        suspect_a = next(s for s in data["suspects"] if s["column"] == "a")
        self.assertEqual(suspect_a["examples"], [{"value": "bad", "line": 9}])
        self.assertEqual(len(data["profiles"]), 2)
        self.assertRegex(data["case_number"], r"^\d{8}-\d{4}$")

    def test_profiles_shape(self):
        profiles = self.investigate(self.open_sample())["profiles"]
        a, b = profiles
        self.assertEqual((a["kind"], a["stats"]["max"]), ("numeric", 7.0))
        self.assertEqual(b["kind"], "text")
        self.assertEqual(b["most_common"], {"value": "x", "count": 2})
        self.assertEqual(b["unique"], 8)

    def test_html_in_data_is_passed_through(self):
        # Review Focus 2: the API hands markup over as plain text.
        case_id = self.upload("h.csv", "name,<b>col</b>\n1,<script>x</script>\n")
        profiles = self.investigate(case_id)["profiles"]
        self.assertEqual(profiles[1]["column"], "<b>col</b>")
        self.assertEqual(profiles[1]["most_common"]["value"],
                         "<script>x</script>")

    def test_wide_file_returns_every_profile(self):
        # Review Focus 5: a 1,000-column file.
        header = ",".join(f"c{i}" for i in range(1000))
        row = ",".join(str(i) for i in range(1000))
        case_id = self.upload("wide.csv", f"{header}\n{row}\n{row}\n{row}\n")
        self.assertEqual(len(self.investigate(case_id)["profiles"]), 1000)

    def test_lists_are_capped(self):
        case_id = self.upload("dups.csv", "a\n" + "1\n" * 150)
        duplicates = self.investigate(case_id)["duplicates"]
        self.assertEqual(duplicates["total"], 149)
        self.assertEqual(len(duplicates["items"]), 100)

    def test_save_and_replace(self):
        case_id = self.open_sample()
        self.investigate(case_id)
        status, data = self.call("POST", f"/api/cases/{case_id}/save")
        self.assertEqual((status, data), (200, {
            "path": os.path.join("reports", "t_report.txt"),
            "replaced": False}))
        self.assertTrue(os.path.exists(
            os.path.join(self.reports, "t_report.txt")))
        self.assertTrue(self.call("POST",
                                  f"/api/cases/{case_id}/save")[1]["replaced"])

    def test_report_download_matches_terminal(self):
        from report import Report
        case_id = self.open_sample()
        response = self.api.handle("GET", f"/api/cases/{case_id}/report.txt",
                                   {}, b"")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "text/plain; charset=utf-8")
        self.assertIn('filename="t_report.txt"',
                      response.headers["Content-Disposition"])
        self.assertEqual(response.body.decode("utf-8"),
                         Report(self.api.findings[case_id]).to_text())

    def test_save_runs_investigation_first(self):
        case_id = self.open_sample()
        status, _ = self.call("POST", f"/api/cases/{case_id}/save")
        self.assertEqual(status, 200)
        self.assertTrue(os.path.exists(
            os.path.join(self.reports, "t_report.txt")))

    def test_save_error(self):
        case_id = self.open_sample()
        self.api.reports_dir = write_file("not a folder", "reports_file")
        status, data = self.call("POST", f"/api/cases/{case_id}/save")
        self.assertEqual(status, 500)
        self.assertTrue(data["error"].startswith(
            "Couldn't save the report: "), data)


if __name__ == "__main__":
    unittest.main()
