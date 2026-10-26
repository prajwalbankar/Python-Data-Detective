"""Custom exceptions for problems with data files.

DatasetError is the base class. main.py catches it to show the user a
friendly message. Any other exception is a genuine bug, so it is left
alone and still shows up while developing.
"""


class DatasetError(Exception):
    """An expected problem with a data file, shown to the user."""


class UnreadableFileError(DatasetError):
    """The file is missing, is a folder, or can't be read as a CSV."""


class EmptyDatasetError(DatasetError):
    """The file has no rows at all, or a header with no data rows."""
