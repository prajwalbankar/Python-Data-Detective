"""Investigate a Dataset's quality.

The Investigator works out each column's type, counts missing values and
invalid numbers, profiles every column, finds duplicate rows and turns
it all into three sub-scores and an overall quality score.
"""
import math
import statistics
from collections import Counter
from datetime import datetime
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


class Findings:
    """Everything the investigation found out about one dataset."""

    def __init__(self, dataset: Dataset) -> None:
        """Start with empty results; Investigator.investigate fills them."""
        self.dataset = dataset
        self.profiles: list[ColumnProfile] = []
        # (line of the copy, line of the original) for each duplicate row.
        self.duplicates: list[tuple[int, int]] = []
        self.total_cells = 0
        self.missing_cells = 0
        self.numeric_cells = 0      # filled cells in numeric columns
        self.invalid_cells = 0
        self.completeness = 0.0     # sub-scores, 0-100, one decimal place
        self.uniqueness = 0.0
        self.validity = 0.0
        self.overall = 0            # weighted overall score, 0-100
        self.verdict = ""
        self.short_verdict = ""
        self.investigated_at = datetime.now()


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

    def investigate(self) -> Findings:
        """Run every check on the dataset and return the findings."""
        findings = Findings(self.dataset)
        rows = self.dataset.num_rows()
        for index in range(self.dataset.num_columns()):
            profile = self._profile_column(index)
            findings.profiles.append(profile)
            findings.missing_cells += profile.missing
            findings.invalid_cells += profile.invalid
            if profile.kind == "numeric":
                findings.numeric_cells += rows - profile.missing
        findings.total_cells = rows * self.dataset.num_columns()
        findings.duplicates = self._find_duplicates()
        self._score(findings)
        findings.investigated_at = datetime.now()
        return findings

    def _find_duplicates(self) -> list[tuple[int, int]]:
        """Return (copy line, original line) for every repeated row."""
        first_seen = {}  # row as a tuple of stripped cells -> its line
        duplicates = []
        for row, line in zip(self.dataset.rows, self.dataset.line_numbers):
            # Tuples can't change, so they can be used as dict keys.
            key = tuple([cell.strip() for cell in row])
            if key in first_seen:
                duplicates.append((line, first_seen[key]))
            else:
                first_seen[key] = line
        return duplicates

    def _score(self, findings: Findings) -> None:
        """Work out the three sub-scores, the overall score and verdict."""
        completeness = 100 * (1 - findings.missing_cells
                              / findings.total_cells)
        uniqueness = 100 * (1 - len(findings.duplicates)
                            / self.dataset.num_rows())
        if findings.numeric_cells == 0:
            validity = 100.0    # nothing could be an invalid number
        else:
            validity = 100 * (1 - findings.invalid_cells
                              / findings.numeric_cells)

        complete_weight, unique_weight, valid_weight = Investigator.WEIGHTS
        overall = (complete_weight * completeness
                   + unique_weight * uniqueness
                   + valid_weight * validity)

        findings.completeness = round(completeness, 1)
        findings.uniqueness = round(uniqueness, 1)
        findings.validity = round(validity, 1)
        # Round halves up (round() would send 98.5 down to 98).
        findings.overall = math.floor(overall + 0.5)
        findings.short_verdict, findings.verdict = self.verdict_for(
            findings.overall)

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
