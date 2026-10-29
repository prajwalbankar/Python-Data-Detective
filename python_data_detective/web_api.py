"""The web UI's API: every action the page can ask for.

DetectiveApi turns a request (method, path, query, body) into a Response.
It uses exactly the same Dataset, Investigator and Report classes as the
terminal program, so the web page always shows what the terminal would.
It knows nothing about HTTP itself (web_app.py does that), which keeps
it easy to test.
"""
import json
import os
import tempfile
import threading
import traceback
import urllib.parse
from typing import Optional

from dataset import Dataset
from errors import DatasetError
from investigator import ColumnProfile, Findings, Investigator
from main import TOO_BIG, list_csv_files
from report import DELIMITER_NAMES, Report, rank_findings, sub_score_notes

PREVIEW_ROWS = 5
MAX_UPLOAD_BYTES = 200 * 1024 * 1024   # 200 MB
MAX_OPEN_CASES = 20      # older cases are closed to limit memory use
LIST_LIMIT = 100         # longest duplicates / malformed list sent
# The colour band the page uses for each short verdict.
BANDS = {"Case closed": "good", "Minor clean-up": "fair",
         "Needs cleaning": "poor", "Unreliable": "bad"}
TOO_BIG_MESSAGE = "This file is too large for this computer's memory."
UNEXPECTED_MESSAGE = "Something went wrong. Details are in the terminal."
CLOSED_MESSAGE = ("This case is no longer open. Open it again from the "
                  "evidence locker.")


class ApiError(Exception):
    """A request the API refuses, with the HTTP status to send back."""

    def __init__(self, status: int, message: str) -> None:
        """Remember the status code and the message for the user."""
        super().__init__(message)
        self.status = status
        self.message = message


class Response:
    """What the server should send back for one request."""

    def __init__(self, status: int, content_type: str, body: bytes,
                 headers: Optional[dict] = None) -> None:
        """Store the parts of an HTTP response."""
        self.status = status
        self.content_type = content_type
        self.body = body
        self.headers: dict[str, str] = headers or {}


def json_response(status: int, data: dict) -> Response:
    """Return data as a JSON response."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return Response(status, "application/json; charset=utf-8", body)


def text_response(text: str, filename: str) -> Response:
    """Return text as a file download called filename."""
    # Headers must be plain ASCII, so non-ASCII names go in filename*.
    fallback = filename.encode("ascii", "replace").decode().replace("?", "_")
    quoted = urllib.parse.quote(filename)
    disposition = (f'attachment; filename="{fallback}"; '
                   f"filename*=UTF-8''{quoted}")
    return Response(200, "text/plain; charset=utf-8", text.encode("utf-8"),
                    {"Content-Disposition": disposition})


def safe_file_name(name: str) -> str:
    """Return just the file name part of name, never a path."""
    # Split on both kinds of slash, whatever computer sent the name.
    base = name.replace("\\", "/").split("/")[-1].strip()
    if base in ("", ".", ".."):
        return "upload.csv"
    # Windows can't store these characters in a file name.
    safe = ""
    for char in base:
        if char in '<>:"|?*' or ord(char) < 32:
            safe += "_"
        else:
            safe += char
    return safe


def capitalise(message: str) -> str:
    """Give a program message a capital first letter for display."""
    return message[:1].upper() + message[1:]


def case_summary(case_id: str, dataset: Dataset, run: str) -> dict:
    """Return the short description of an open case."""
    return {"id": case_id, "name": dataset.name,
            "rows": dataset.num_rows(), "columns": dataset.num_columns(),
            "delimiter": DELIMITER_NAMES[dataset.delimiter],
            "encoding": dataset.encoding,
            "warnings": list(dataset.warnings), "run": run}


def profile_json(profile: ColumnProfile, rows: int) -> dict:
    """Describe one column's profile for the page."""
    stats = None
    if profile.stats is not None:
        low, high, mean, median = profile.stats
        stats = {"min": low, "max": high, "mean": mean, "median": median}
    most_common = None
    if profile.most_common is not None:
        value, count = profile.most_common
        most_common = {"value": value, "count": count}
    return {"column": profile.name, "kind": profile.kind,
            "missing_percent": round(100 * profile.missing / rows, 1),
            "stats": stats, "unique": profile.unique_count,
            "most_common": most_common}


def findings_json(findings: Findings, summary: dict) -> dict:
    """Describe everything an investigation found, for the page."""
    dataset = findings.dataset
    suspects = []
    for profile in findings.profiles:
        if profile.missing or profile.invalid or profile.not_numbers:
            examples = []
            for value, line in profile.invalid_examples:
                examples.append({"value": value, "line": line})
            suspects.append({"column": profile.name, "kind": profile.kind,
                             "missing": profile.missing,
                             "invalid": profile.invalid,
                             "not_numbers": profile.not_numbers,
                             "examples": examples})
    duplicates = []
    for copy_line, original_line in findings.duplicates[:LIST_LIMIT]:
        duplicates.append({"line": copy_line, "original": original_line})
    malformed = []
    for line, fields in dataset.malformed_rows[:LIST_LIMIT]:
        malformed.append({"line": line, "fields": fields})
    sub_scores = []
    for label, score, note in sub_score_notes(findings):
        sub_scores.append({"name": label, "score": score, "note": note})
    when = findings.investigated_at
    return {
        "case": summary,
        "case_number": when.strftime("%Y%m%d-%H%M"),
        "investigated_at": when.isoformat(timespec="seconds"),
        "score": findings.overall, "verdict": findings.verdict,
        "short_verdict": findings.short_verdict,
        "band": BANDS[findings.short_verdict],
        "sub_scores": sub_scores, "suspects": suspects,
        "duplicates": {"total": len(findings.duplicates),
                       "items": duplicates},
        "malformed": {"total": len(dataset.malformed_rows),
                      "expected_fields": dataset.num_columns(),
                      "items": malformed},
        "profiles": [profile_json(profile, dataset.num_rows())
                     for profile in findings.profiles],
    }


class DetectiveApi:
    """Every action the web page can ask for, independent of HTTP."""

    def __init__(self, datasets_dir: str, reports_dir: str,
                 upload_dir: str, base_dir: str) -> None:
        """Set up the folders and the (empty) list of open cases."""
        self.datasets_dir = datasets_dir
        self.reports_dir = reports_dir
        self.upload_dir = upload_dir
        self.base_dir = base_dir
        self.cases: dict[str, Dataset] = {}
        self.findings: dict[str, Findings] = {}
        self.next_id = 1
        # Ids start at c1 on every run, so the page sends this token back
        # with each case request; a page left open from an earlier run is
        # told its case is closed instead of reaching a different file.
        self.run_id = os.urandom(4).hex()
        # The latest Investigate ALL: (findings, [(file name, reason)]).
        self.board: Optional[tuple[list[Findings],
                                   list[tuple[str, str]]]] = None
        # The server answers requests on several threads at once; the
        # lock lets only one of them change the open cases at a time.
        self.lock = threading.Lock()

    def handle(self, method: str, path: str, query: dict,
               body: bytes) -> Response:
        """Answer one request. Never raises: errors become messages."""
        with self.lock:
            try:
                return self._route(method, path, query, body)
            except ApiError as err:
                return json_response(err.status, {"error": err.message})
            except DatasetError as err:
                return json_response(422, {"error": capitalise(str(err))})
            except MemoryError:
                return json_response(413, {"error": TOO_BIG_MESSAGE})
            except Exception:
                traceback.print_exc()   # details for the terminal only
                return json_response(500, {"error": UNEXPECTED_MESSAGE})

    def _route(self, method: str, path: str, query: dict,
               body: bytes) -> Response:
        """Send the request to the method that handles its path."""
        parts = [part for part in path.split("/") if part]
        if parts == ["api", "locker"]:
            require_method(method, "GET")
            return json_response(200, self.list_locker())
        if parts == ["api", "cases", "locker"]:
            require_method(method, "POST")
            name = read_json(body).get("name", "")
            return json_response(200, self.open_locker(name))
        if parts == ["api", "cases", "upload"]:
            require_method(method, "POST")
            return json_response(200, self.open_upload(
                query.get("name", ""), body))
        if parts == ["api", "investigate-all"]:
            require_method(method, "POST")
            return json_response(200, self.investigate_all())
        if parts == ["api", "save-all"]:
            require_method(method, "POST")
            return json_response(200, self.save_all())
        if len(parts) == 4 and parts[:2] == ["api", "cases"]:
            case_id, action = parts[2], parts[3]
            if query.get("run", self.run_id) != self.run_id:
                raise ApiError(404, CLOSED_MESSAGE)
            if action == "evidence":
                require_method(method, "GET")
                return json_response(200, self.evidence(case_id))
            if action == "investigate":
                require_method(method, "POST")
                return json_response(200, self.investigate(case_id))
            if action == "save":
                require_method(method, "POST")
                return json_response(200, self.save(case_id))
            if action == "report.txt":
                require_method(method, "GET")
                text = self.report_text(case_id)
                stem = os.path.splitext(self.cases[case_id].name)[0]
                return text_response(text, stem + "_report.txt")
        raise ApiError(404, "Not found.")

    def list_locker(self) -> dict:
        """List the CSV files in the evidence locker with their sizes."""
        datasets = []
        for name in list_csv_files(self.datasets_dir):
            size = os.path.getsize(os.path.join(self.datasets_dir, name))
            datasets.append({"name": name, "bytes": size})
        return {"datasets": datasets}

    def open_locker(self, name: str) -> dict:
        """Open a dataset from the evidence locker by its file name."""
        unsafe = (not isinstance(name, str) or "/" in name or "\\" in name
                  or ".." in name)
        if unsafe or name not in list_csv_files(self.datasets_dir):
            raise ApiError(404, f"There's no dataset called '{name}' in "
                                "the evidence locker.")
        return self._open(os.path.join(self.datasets_dir, name))

    def open_upload(self, name: str, data: bytes) -> dict:
        """Open a file the user dropped into the page."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "Files over 200 MB can't be uploaded.")
        # Each upload gets its own folder, so the file keeps its real
        # name (shown in the case and used for the report's name).
        folder = tempfile.mkdtemp(dir=self.upload_dir)
        path = os.path.join(folder, safe_file_name(name))
        with open(path, "wb") as file:
            file.write(data)
        return self._open(path)

    def evidence(self, case_id: str) -> dict:
        """Return the 'inspect the evidence' details of an open case."""
        dataset = self._case(case_id)
        return {"case": case_summary(case_id, dataset, self.run_id),
                "blank_lines_skipped": dataset.blank_lines_skipped,
                "trailing_delimiters": dataset.trailing_delimiters,
                "header": list(dataset.header),
                "preview": [list(row) for row in
                            dataset.preview(PREVIEW_ROWS)]}

    def investigate(self, case_id: str) -> dict:
        """Run the investigation on an open case and return the findings."""
        dataset = self._case(case_id)
        self.findings[case_id] = Investigator(dataset).investigate()
        return findings_json(self.findings[case_id],
                             case_summary(case_id, dataset, self.run_id))

    def save(self, case_id: str) -> dict:
        """Save the case report into reports/ (investigating if needed)."""
        try:
            path, replaced = Report(self._findings(case_id)).save(
                self.reports_dir)
        except OSError as err:
            raise ApiError(500, f"Couldn't save the report: {err}")
        return {"path": self._shown_path(path), "replaced": replaced}

    def report_text(self, case_id: str) -> str:
        """Return the case report as text (investigating if needed)."""
        return Report(self._findings(case_id)).to_text()

    def investigate_all(self) -> dict:
        """Investigate every dataset in the locker and rank them."""
        findings_list = []
        failures = []   # (file name, reason) for files that couldn't open
        for name in list_csv_files(self.datasets_dir):
            try:
                dataset = Dataset(os.path.join(self.datasets_dir, name))
                findings_list.append(Investigator(dataset).investigate())
            except DatasetError as err:
                failures.append((name, capitalise(str(err))))
            except MemoryError:
                failures.append((name, capitalise(TOO_BIG)))
        self.board = (findings_list, failures)
        ranked = []
        for rank, findings in enumerate(rank_findings(findings_list),
                                        start=1):
            ranked.append({"rank": rank, "name": findings.dataset.name,
                           "rows": findings.dataset.num_rows(),
                           "score": findings.overall,
                           "verdict": findings.verdict,
                           "short_verdict": findings.short_verdict,
                           "band": BANDS[findings.short_verdict]})
        failed = [{"name": name, "reason": reason}
                  for name, reason in failures]
        return {"ranked": ranked, "failures": failed}

    def save_all(self) -> dict:
        """Save every case report plus leaderboard.txt into reports/."""
        if self.board is None:
            self.investigate_all()
        findings_list, failures = self.board
        try:
            for findings in findings_list:
                Report(findings).save(self.reports_dir)
            # The folder may not exist yet if no dataset could be opened.
            os.makedirs(self.reports_dir, exist_ok=True)
            board = Report.leaderboard_text(findings_list, failures)
            with open(os.path.join(self.reports_dir, "leaderboard.txt"),
                      "w", encoding="utf-8") as file:
                file.write(board)
        except OSError as err:
            raise ApiError(500, f"Couldn't save the report: {err}")
        return {"saved": len(findings_list),
                "folder": self._shown_path(self.reports_dir)}

    def _findings(self, case_id: str) -> Findings:
        """Return a case's findings, investigating it first if needed."""
        self._case(case_id)
        if case_id not in self.findings:
            self.investigate(case_id)
        return self.findings[case_id]

    def _shown_path(self, path: str) -> str:
        """Show a path relative to the program folder, if possible,
        with "/" between folders on every system."""
        try:
            shown = os.path.relpath(path, self.base_dir)
        except ValueError:   # Windows: a path on another drive
            shown = path
        return shown.replace(os.sep, "/")

    def _open(self, path: str) -> dict:
        """Load the file at path as a new case and describe it."""
        dataset = Dataset(path)
        case_id = f"c{self.next_id}"
        self.next_id += 1
        self.cases[case_id] = dataset
        if len(self.cases) > MAX_OPEN_CASES:
            # Dicts keep insertion order, so the first key is the oldest.
            oldest = next(iter(self.cases))
            del self.cases[oldest]
            self.findings.pop(oldest, None)
        return {"case": case_summary(case_id, dataset, self.run_id)}

    def _case(self, case_id: str) -> Dataset:
        """Return an open case, or explain that it's no longer open."""
        if case_id not in self.cases:
            raise ApiError(404, CLOSED_MESSAGE)
        return self.cases[case_id]


def require_method(method: str, allowed: str) -> None:
    """Refuse a request made with the wrong HTTP method."""
    if method != allowed:
        raise ApiError(405, "Method not allowed.")


def read_json(body: bytes) -> dict:
    """Parse a JSON request body, which must be an object."""
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        raise ApiError(400, "The request wasn't valid JSON.")
    if not isinstance(data, dict):
        raise ApiError(400, "The request wasn't valid JSON.")
    return data
