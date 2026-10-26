"""Test helpers: put the app on sys.path and build temporary datasets."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "python_data_detective")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.join(APP_DIR, "tools"))


def write_file(content, name="t.csv", encoding="utf-8", folder=None):
    """Write text (newline="" keeps \\r\\n) or bytes; return the path."""
    folder = folder or tempfile.mkdtemp()
    path = os.path.join(folder, name)
    if isinstance(content, bytes):
        with open(path, "wb") as f:
            f.write(content)
    else:
        with open(path, "w", encoding=encoding, newline="") as f:
            f.write(content)
    return path


def make_dataset(text, name="t.csv", encoding="utf-8"):
    """Build a Dataset from CSV text written to a temporary file."""
    from dataset import Dataset
    return Dataset(write_file(text, name, encoding))
