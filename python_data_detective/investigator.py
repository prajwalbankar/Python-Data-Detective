"""Investigate a Dataset's quality.

The Investigator works out each column's type, counts missing values and
invalid numbers, profiles every column, finds duplicate rows and turns
it all into three sub-scores and an overall quality score.
"""
import math
import statistics
from collections import Counter
from typing import Optional

from dataset import Dataset


class ColumnProfile:
    """What the investigation found in one column."""

    def __init__(self, name: str) -> None:
        """Start an empty profile for the column called name."""
        self.name = name
        self.kind = "text"          # "numeric", "text" or "empty"
        self.missing = 0
        self.invalid = 0
        self.invalid_examples: list[tuple[str, int]] = []
        # (min, max, mean, median) of the valid numbers.
        self.stats: Optional[tuple[float, float, float, float]] = None
        self.unique_count = 0
        self.most_common: Optional[tuple[str, int]] = None


class Investigator:
    """Runs every data-quality check on one Dataset."""

    # Values that count as missing, after stripping and ignoring case.
    MISSING_MARKERS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}
    # A column is numeric if at least this share of its filled cells
    # are numbers.
    NUMERIC_THRESHOLD = 0.8
    # Weights of completeness, uniqueness and validity in the overall.
    WEIGHTS = (0.4, 0.3, 0.3)
    # (minimum score, short verdict, full verdict), highest band first.
    VERDICT_BANDS = [
        (95, "Case closed", "Case closed - ready for analysis"),
        (85, "Minor clean-up", "Minor clean-up needed"),
        (70, "Needs cleaning", "Significant cleaning needed"),
        (0, "Unreliable", "Unreliable evidence - investigate before use"),
    ]
    # How many invalid values to quote as examples for each column.
    MAX_EXAMPLES = 3

    def __init__(self, dataset: Dataset) -> None:
        """Prepare to investigate dataset."""
        self.dataset = dataset

    @staticmethod
    def is_missing(value: str) -> bool:
        """Return True if value is blank or a marker such as 'NA'."""
        return value.strip().lower() in Investigator.MISSING_MARKERS

    @staticmethod
    def is_number(value: str) -> bool:
        """Return True if value is a finite number such as '3.5' or '1e3'."""
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False

    @staticmethod
    def verdict_for(score: int) -> tuple[str, str]:
        """Return the (short, full) verdict for an overall score."""
        for minimum, short, full in Investigator.VERDICT_BANDS:
            if score >= minimum:
                return short, full
        # Scores can't be negative; treat one like the lowest band.
        return Investigator.VERDICT_BANDS[-1][1:]

    def _profile_column(self, index: int) -> ColumnProfile:
        """Work out the type, problems and summary of one column."""
        profile = ColumnProfile(self.dataset.header[index])

        filled = []  # (stripped value, line) for every non-missing cell
        values = self.dataset.column_values(index)
        for value, line in zip(values, self.dataset.line_numbers):
            if self.is_missing(value):
                profile.missing += 1
            else:
                filled.append((value.strip(), line))
        if not filled:
            profile.kind = "empty"
            return profile

        numbers = []
        non_numbers = []  # (value, line) for filled cells that aren't numbers
        for value, line in filled:
            if self.is_number(value):
                numbers.append(float(value))
            else:
                non_numbers.append((value, line))

        if len(numbers) / len(filled) >= Investigator.NUMERIC_THRESHOLD:
            profile.kind = "numeric"
            profile.invalid = len(non_numbers)
            profile.invalid_examples = non_numbers[:Investigator.MAX_EXAMPLES]
            profile.stats = (min(numbers), max(numbers),
                             statistics.mean(numbers),
                             statistics.median(numbers))
        else:
            profile.kind = "text"
            # Count each distinct value; ties keep the first one seen.
            counts = Counter([value for value, line in filled])
            profile.unique_count = len(counts)
            profile.most_common = counts.most_common(1)[0]
        return profile
