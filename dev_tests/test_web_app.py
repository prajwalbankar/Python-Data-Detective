"""Tests for the web UI's HTTP server, using real local connections."""
import json
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from context import SAMPLE_TEXT, write_file
import web_app
from web_api import DetectiveApi


class ServerTestCase(unittest.TestCase):
    """Runs the real server on a free port in a background thread."""

    def setUp(self):
        base = tempfile.mkdtemp()
        datasets = os.path.join(base, "datasets")
        uploads = os.path.join(base, "uploads")
        os.makedirs(datasets)
        os.makedirs(uploads)
        write_file(SAMPLE_TEXT, "t.csv", folder=datasets)
        self.api = DetectiveApi(datasets, os.path.join(base, "reports"),
                                uploads, base)
        self.server = web_app.start_server([0], self.api)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def request(self, method, path, body=None):
        """Return (status, content type, body bytes) for one request."""
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url, data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as reply:
                return (reply.status, reply.headers["Content-Type"],
                        reply.read())
        except urllib.error.HTTPError as err:
            return err.code, err.headers["Content-Type"], err.read()


class TestServer(ServerTestCase):

    def test_serves_the_page(self):
        status, kind, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertTrue(kind.startswith("text/html"))
        self.assertIn(b"<title>Data Detective</title>", body)
        self.assertTrue(self.request("GET", "/style.css")[1]
                        .startswith("text/css"))
        self.assertTrue(self.request("GET", "/app.js")[1]
                        .startswith("text/javascript"))

    def test_unknown_static_path(self):
        for path in ["/../main.py", "/secret.txt", "/web/app.js"]:
            with self.subTest(path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_api_round_trip(self):
        status, _, body = self.request(
            "POST", "/api/cases/locker", json.dumps({"name": "t.csv"}).encode())
        self.assertEqual(status, 200, body)
        status, _, body = self.request("POST", "/api/cases/c1/investigate",
                                       b"")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["score"], 48)

    def test_upload_over_http(self):
        status, _, body = self.request("POST",
                                       "/api/cases/upload?name=x%20y.csv",
                                       SAMPLE_TEXT.encode())
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["case"]["name"], "x y.csv")

    def test_binds_to_localhost(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_falls_back_to_next_port(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        busy = blocker.getsockname()[1]
        try:
            server = web_app.start_server([busy, 0], self.api)
            try:
                self.assertNotEqual(server.server_address[1], busy)
            finally:
                server.server_close()
        finally:
            blocker.close()

    def test_concurrent_requests(self):
        # Review Focus 4: several requests at once share the API safely.
        statuses = []

        def open_and_investigate():
            status, _, body = self.request(
                "POST", "/api/cases/locker",
                json.dumps({"name": "t.csv"}).encode())
            case_id = json.loads(body)["case"]["id"]
            statuses.append(status)
            statuses.append(self.request(
                "POST", f"/api/cases/{case_id}/investigate", b"")[0])

        threads = [threading.Thread(target=open_and_investigate)
                   for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertEqual(statuses, [200] * 16)
        self.assertEqual(len(self.api.cases), 8)


if __name__ == "__main__":
    unittest.main()
