"""Run every stress scenario through Python Data Detective and record it.

For each file in stress_tests/files/ this:
  1. runs Dataset -> Investigator -> Report in this process (timing it and
     checking that no line of the program's own text exceeds 64 chars);
  2. runs the real program end to end: option 1, P, the path, option 3;
then runs "Investigate ALL" on a copy of the app whose datasets/ folder
holds every scenario file, and measures peak memory on the largest files.

Results go to stress_tests/results.json and stress_tests/results.md.

    python stress_tests/make_stress_files.py
    python stress_tests/run_stress_tests.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = os.path.join(HERE, "files")
APP = os.path.join(os.path.dirname(HERE), "python_data_detective")
sys.path.insert(0, APP)

from dataset import Dataset            # noqa: E402
from errors import DatasetError        # noqa: E402
from investigator import Investigator  # noqa: E402
from report import WIDTH, Report       # noqa: E402

CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
ANACONDA = os.path.expanduser(r"~\anaconda3\python.exe")


def pipeline(path: str) -> dict:
    """Load, investigate and report one file; describe what happened."""
    start = time.perf_counter()
    result = {}
    try:
        dataset = Dataset(path)
        findings = Investigator(dataset).investigate()
        texts = [Report(findings).to_text(), Report.evidence_text(dataset)]
        kinds = [profile.kind for profile in findings.profiles]
        result = {
            "outcome": "loaded",
            "rows": dataset.num_rows(), "columns": dataset.num_columns(),
            "delimiter": dataset.delimiter, "encoding": dataset.encoding,
            "numeric_cols": kinds.count("numeric"),
            "text_cols": kinds.count("text"),
            "empty_cols": kinds.count("empty"),
            "missing_pct": round(findings.missing_percent, 1),
            "duplicates": len(findings.duplicates),
            "invalid": findings.invalid_cells,
            "malformed": len(dataset.malformed_rows),
            "warnings": dataset.warnings,
            "trailing": dataset.trailing_delimiters,
            "score": findings.overall, "verdict": findings.short_verdict,
            "report_lines": len(texts[0].splitlines()),
            "too_wide": sum(len(line) > WIDTH for text in texts
                            for line in text.splitlines()),
        }
    except DatasetError as err:
        result = {"outcome": "refused", "message": str(err)}
    except Exception as err:   # anything else is a bug
        result = {"outcome": "CRASH", "message": f"{type(err).__name__}: "
                                                 f"{err}"}
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result


def end_to_end(path: str) -> dict:
    """Drive the real main.py: open the file with P, investigate, quit."""
    start = time.perf_counter()
    run = subprocess.run(
        [sys.executable, os.path.join(APP, "main.py")],
        input=f"1\nP\n{path}\n3\n0\n", capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, env=CHILD_ENV,
        cwd=tempfile.gettempdir())
    said = ""
    for line in run.stdout.splitlines():
        for marker in ("Could not open case:", "VERDICT:"):
            if marker in line:
                said = line[line.index(marker):].strip()
    return {"exit_code": run.returncode,
            "traceback": "Traceback" in run.stderr,
            "said": said, "goodbye": "Goodbye, detective" in run.stdout,
            "seconds": round(time.perf_counter() - start, 2)}


def investigate_all(names: list) -> str:
    """Run option 5 on a copy of the app whose datasets/ holds every file."""
    copy = os.path.join(tempfile.mkdtemp(), "app")
    shutil.copytree(APP, copy, ignore=shutil.ignore_patterns(
        "datasets", "reports", "__pycache__"))
    os.makedirs(os.path.join(copy, "datasets"))
    for name in names:
        source = os.path.join(FILES, name)
        if os.path.isfile(source):
            shutil.copy(source, os.path.join(copy, "datasets", name))
        else:
            shutil.copytree(source, os.path.join(copy, "datasets", name))
    run = subprocess.run([sys.executable, os.path.join(copy, "main.py")],
                         input="5\nn\n0\n", capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=600,
                         env=CHILD_ENV)
    board = run.stdout[run.stdout.index("CASE BOARD") - 67:]
    board = board[:board.index("Save a report")]
    return board + f"\n(exit code {run.returncode}, traceback: " \
                   f"{'Traceback' in run.stderr})\n"


def peak_memory_mb(path: str) -> float:
    """Peak memory of a fresh process investigating path (Windows)."""
    if not os.path.exists(ANACONDA):
        return -1.0
    code = ("import sys, psutil; sys.path.insert(0, sys.argv[1])\n"
            "from dataset import Dataset\n"
            "from investigator import Investigator\n"
            "from report import Report\n"
            "Report(Investigator(Dataset(sys.argv[2])).investigate())"
            ".to_text()\n"
            "print(psutil.Process().memory_info().peak_wset / 1e6)\n")
    run = subprocess.run([ANACONDA, "-c", code, APP, path],
                         capture_output=True, text=True, timeout=600)
    return round(float(run.stdout.strip()), 1)


def main() -> None:
    """Run every scenario and write results.json and results.md."""
    with open(os.path.join(FILES, "_index.json"), encoding="utf-8") as f:
        scenarios = json.load(f)
    results = []
    for name, category, description in scenarios:
        path = os.path.join(FILES, name)
        size = (os.path.getsize(path) if os.path.isfile(path)
                else sum(os.path.getsize(os.path.join(path, n))
                         for n in os.listdir(path)))
        entry = {"name": name, "category": category,
                 "description": description, "bytes": size,
                 "pipeline": pipeline(path), "program": end_to_end(path)}
        results.append(entry)
        p, e = entry["pipeline"], entry["program"]
        print(f"{name:32} {p['outcome']:8} {p.get('score', '')!s:>4} "
              f"{e['said'][:60]}")

    board = investigate_all([name for name, _, _ in scenarios])
    memory = {name: peak_memory_mb(os.path.join(FILES, name))
              for name in ["huge_1m_rows.csv", "ecommerce_100k.csv",
                           "wide_1000_columns.csv"]}
    with open(os.path.join(HERE, "results.json"), "w",
              encoding="utf-8") as f:
        json.dump({"python": sys.version.split()[0], "results": results,
                   "investigate_all": board, "peak_memory_mb": memory},
                  f, ensure_ascii=False, indent=1)
    print(board)
    print("peak memory (MB):", memory)
    crashes = [r["name"] for r in results
               if r["pipeline"]["outcome"] == "CRASH"
               or r["program"]["traceback"] or r["program"]["exit_code"]]
    print("crashes / tracebacks:", crashes or "none")


if __name__ == "__main__":
    main()
