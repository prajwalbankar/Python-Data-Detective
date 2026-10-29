# RUN THIS FILE for the web UI: python web_app.py   (optional extra)
"""Python Data Detective: the web UI.

Starts a small web server on this computer only (localhost) and opens
the Data Detective page in your browser:

    python web_app.py                  (or python3 web_app.py)
    python web_app.py --no-browser     (just print the address)

Press Ctrl+C in this terminal to stop it. It needs only Python's
standard library. Ed can't run it, because it uses networking; the
terminal program (main.py) is the main version of the project.

This file only handles HTTP. Every action is answered by web_api.py,
which uses the same classes as the terminal program.
"""
import os
import shutil
import sys
import tempfile
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

import web_api
from main import BASE_DIR, DATASETS_DIR, REPORTS_DIR
from web_api import DetectiveApi, Response, json_response

WEB_DIR = os.path.join(BASE_DIR, "web")
PORTS = list(range(8000, 8011))   # 8000, then 8001 ... 8010 if busy
FORBIDDEN_MESSAGE = "This server only answers its own page on this computer."
# The only files the server will send: URL path -> (file, content type).
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class LocalServer(ThreadingHTTPServer):
    """A threaded HTTP server that refuses ports already in use."""

    # On Windows, address reuse would let us share a port another
    # program is using, so it's turned off and we try the next port.
    allow_reuse_address = False

    def handle_error(self, request: object, client_address: tuple) -> None:
        """Stay quiet when the browser hangs up (a tab closed or reloaded
        mid-answer); print the details of any other error."""
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    """Answers one HTTP request: a page file or an API call."""

    server_version = "DataDetective"

    def do_GET(self) -> None:
        """Answer a GET request."""
        self.dispatch("GET")

    def do_POST(self) -> None:
        """Answer a POST request."""
        self.dispatch("POST")

    def dispatch(self, method: str) -> None:
        """Send API paths to the API and page paths to the page files."""
        if not self.from_this_computer():
            self.close_connection = True      # its body is never read
            self.send(json_response(403, {"error": FORBIDDEN_MESSAGE}))
            return
        url = urllib.parse.urlsplit(self.path)
        if url.path.startswith("/api/"):
            body = self.read_body()
            if body is None:
                return            # too big: already answered
            query = {}
            for key, values in urllib.parse.parse_qs(url.query).items():
                query[key] = values[0]
            response = self.server.api.handle(method, url.path, query, body)
        elif method == "GET" and url.path in STATIC_FILES:
            response = static_response(url.path)
        else:
            response = json_response(404, {"error": "Not found."})
        self.send(response)

    def from_this_computer(self) -> bool:
        """Is this request from our own page, not another website?

        Any web page can send requests to 127.0.0.1, or reach it through
        a host name it controls, so the Host must be this server's own
        address, and so must the Origin when the browser sends one.
        """
        port = self.server.server_address[1]
        hosts = [f"127.0.0.1:{port}", f"localhost:{port}"]
        if (self.headers.get("Host") or "").lower() not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() in [
            "http://" + host for host in hosts]

    def read_body(self) -> Optional[bytes]:
        """Read the request body, refusing anything over the size limit."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > web_api.MAX_UPLOAD_BYTES:
            self.close_connection = True
            self.send(json_response(413, {
                "error": "Files over 200 MB can't be uploaded."}))
            return None
        return self.rfile.read(length)

    def send(self, response: Response) -> None:
        """Write a Response back to the browser."""
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(response.body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in response.headers.items():
            self.send_header(name, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        """Keep the terminal quiet: don't log every request."""


def static_response(path: str) -> Response:
    """Return one of the page's own files."""
    name, content_type = STATIC_FILES[path]
    with open(os.path.join(WEB_DIR, name), "rb") as file:
        return Response(200, content_type, file.read())


def start_server(ports: list[int], api: DetectiveApi) -> LocalServer:
    """Start the server on the first free port, on this computer only."""
    error: OSError = OSError("no ports to try")
    for port in ports:
        try:
            server = LocalServer(("127.0.0.1", port), Handler)
        except OSError as err:
            error = err
            continue
        server.api = api
        return server
    raise error


def main(argv: list[str]) -> None:
    """Run the web UI until Ctrl+C is pressed."""
    upload_dir = tempfile.mkdtemp(prefix="data_detective_uploads_")
    api = DetectiveApi(DATASETS_DIR, REPORTS_DIR, upload_dir, BASE_DIR)
    try:
        server = start_server(PORTS, api)
    except OSError:
        print("Could not start: ports 8000 to 8010 are all in use.")
        shutil.rmtree(upload_dir, ignore_errors=True)
        return
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Data Detective is running at {url}. Press Ctrl+C to stop.")
    if "--no-browser" not in argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Case closed.")
    finally:
        server.server_close()
        # Uploaded files are only kept while the server runs.
        shutil.rmtree(upload_dir, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
