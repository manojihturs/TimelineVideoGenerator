"""Recognize timeline column headers in any of the formats the app must
support (YYYY-MM, bare year, month names, quarters, week numbers) and
provide a sort key for each, so detected timeline columns can be ordered
chronologically regardless of their left-to-right order in the file."""
import re
from dataclasses import dataclass

MONTH_NAMES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_PATTERNS = [
    ("year_month", re.compile(r"^(\d{4})[-/](\d{1,2})$")),
    ("year_month_day", re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")),
    ("year", re.compile(r"^(\d{4})$")),
    ("quarter", re.compile(r"^(?:(\d{4})[-\s]?)?[Qq]([1-4])$")),
    ("week", re.compile(r"^[Ww]eek\s*(\d{1,2})$")),
    ("month_name", re.compile(
        r"^(" + "|".join(MONTH_NAMES) + r")[a-z]*\.?(?:\s*(\d{4}))?$", re.IGNORECASE)),
]


@dataclass
class TimelineMatch:
    header: str
    format_name: str
    sort_key: tuple  # comparable across all matches of the same format_name


def match_header(header: str) -> TimelineMatch | None:
    text = str(header).strip()
    for format_name, pattern in _PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        if format_name == "year_month":
            year, month = int(m.group(1)), int(m.group(2))
            return TimelineMatch(header, format_name, (year, month))
        if format_name == "year_month_day":
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return TimelineMatch(header, format_name, (year, month, day))
        if format_name == "year":
            return TimelineMatch(header, format_name, (int(m.group(1)),))
        if format_name == "quarter":
            year = int(m.group(1)) if m.group(1) else 0
            quarter = int(m.group(2))
            return TimelineMatch(header, format_name, (year, quarter))
        if format_name == "week":
            return TimelineMatch(header, format_name, (int(m.group(1)),))
        if format_name == "month_name":
            month = MONTH_NAMES[m.group(1).lower()]
            year = int(m.group(2)) if m.group(2) else 0
            return TimelineMatch(header, format_name, (year, month))
    return None


def detect_timeline_columns(columns: list[str]) -> tuple[list[str], str | None]:
    """Try each header against every column; the format that matches the
    most columns wins (>50% of columns, to avoid false positives from one
    stray numeric-looking header). Returns (ordered_matching_columns,
    format_name) — columns are returned in chronological order per that
    format's sort key, not file order."""
    matches_by_format: dict[str, list[TimelineMatch]] = {}
    for col in columns:
        match = match_header(col)
        if match:
            matches_by_format.setdefault(match.format_name, []).append(match)

    if not matches_by_format:
        return [], None

    best_format, best_matches = max(matches_by_format.items(), key=lambda kv: len(kv[1]))
    if len(best_matches) < max(2, len(columns) * 0.3):
        return [], None  # too few matches to be confident this is the timeline

    ordered = sorted(best_matches, key=lambda m: m.sort_key)
    return [m.header for m in ordered], best_format
