"""Turns an arbitrary raw export into the app's template shape (Entity
Name / Category / Image URL, then one column per timeline period) without
the user having to manually transpose or relabel anything first.

Two raw shapes are recognized, both driven by timeline_parser's existing
header-matching heuristic — never by column name or position:
  - already entity-rows / period-columns (our template, possibly missing
    Category/Image URL, or with the entity column named something else)
  - transposed: one row per period, one column per entity (a common
    export shape — e.g. a "Date,Chrome,Safari,..." monthly CSV)
Anything where neither the column headers nor the first column's values
resolve to a timeline is rejected rather than guessed at further.

Image URL is also auto-filled for any row left blank. Entity names that
match a known browser get a verified logo file from the alrra/browser-logos
or simple-icons GitHub repos (every URL below was checked to actually
resolve, not guessed) — the same real files used manually for the
browser-share datasets earlier in this project. Anything not in that table
falls back to a guessed "<slugified-entity-name>.com" logo via Clearbit's
public logo API (https://logo.clearbit.com/<domain>): a best-effort guess,
not a verified lookup. Either way, entity names that don't resolve to a
real logo just 404 at render time, and the renderer already falls back to
a colored-initials avatar for any image that fails to load — so a wrong
guess never breaks the video, it just doesn't get a logo."""
import re

import pandas as pd

from app.services.timeline_parser import detect_timeline_columns

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")

_BROWSER_LOGOS_BASE = "https://raw.githubusercontent.com/alrra/browser-logos/master/src/{d}/{d}_128x128.png"
_SIMPLE_ICONS_BASE = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/{slug}.svg"

# Keyed by lowercased entity name. Verified (HTTP 200) at the time these
# were sourced — see the browser-share renders earlier in this project for
# where each of these was individually checked.
KNOWN_LOGO_URLS: dict[str, str] = {
    "chrome": _BROWSER_LOGOS_BASE.format(d="chrome"),
    "safari": _BROWSER_LOGOS_BASE.format(d="safari"),
    "edge": _BROWSER_LOGOS_BASE.format(d="edge"),
    "edge legacy": _BROWSER_LOGOS_BASE.format(d="edge"),
    "firefox": _BROWSER_LOGOS_BASE.format(d="firefox"),
    "samsung internet": _BROWSER_LOGOS_BASE.format(d="samsung-internet"),
    "opera": _BROWSER_LOGOS_BASE.format(d="opera"),
    "brave": _BROWSER_LOGOS_BASE.format(d="brave"),
    "uc browser": _BROWSER_LOGOS_BASE.format(d="uc"),
    "yandex browser": _BROWSER_LOGOS_BASE.format(d="yandex"),
    "pale moon": _BROWSER_LOGOS_BASE.format(d="pale-moon"),
    "chromium": _BROWSER_LOGOS_BASE.format(d="chromium"),
    "seamonkey": _BROWSER_LOGOS_BASE.format(d="seamonkey"),
    "android": _SIMPLE_ICONS_BASE.format(slug="android"),
    "mozilla": _SIMPLE_ICONS_BASE.format(slug="mozilla"),
    "sogou explorer": _SIMPLE_ICONS_BASE.format(slug="sogou"),
    "ecosia": _SIMPLE_ICONS_BASE.format(slug="ecosia"),
    "kaios": _SIMPLE_ICONS_BASE.format(slug="kaios"),
    "qq browser": _SIMPLE_ICONS_BASE.format(slug="qq"),
    "whale browser": _SIMPLE_ICONS_BASE.format(slug="naver"),
    "ie": (
        "https://raw.githubusercontent.com/alrra/browser-logos/master/"
        "src/archive/internet-explorer_9-11/internet-explorer_9-11_128x128.png"
    ),
}


class FormatError(ValueError):
    """Raised when no timeline could be recognized in the file's headers
    or its first column's values — there's nothing to safely reshape."""


def _guessed_logo_url(entity_name: str) -> str:
    key = str(entity_name).strip().lower()
    if key in KNOWN_LOGO_URLS:
        return KNOWN_LOGO_URLS[key]
    slug = _NON_ALNUM_RE.sub("", key)
    return f"https://logo.clearbit.com/{slug}.com" if slug else ""


def _fill_missing_image_urls(df: pd.DataFrame) -> pd.DataFrame:
    blank = df["Image URL"].isna() | (df["Image URL"].astype(str).str.strip() == "")
    df.loc[blank, "Image URL"] = df.loc[blank, "Entity Name"].map(_guessed_logo_url)
    return df


def format_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df.columns) < 2:
        raise FormatError("File has no data or too few columns to contain a timeline.")

    columns = [str(c) for c in df.columns]

    header_periods, _ = detect_timeline_columns(columns[1:])
    if header_periods:
        return _fill_missing_image_urls(_ensure_template_columns(df, columns, header_periods))

    first_col = columns[0]
    first_col_values = df[first_col].dropna().astype(str).tolist()
    value_periods, _ = detect_timeline_columns(first_col_values)
    if value_periods and len(value_periods) >= max(2, len(first_col_values) * 0.5):
        return _fill_missing_image_urls(_transpose(df, first_col))

    raise FormatError(
        "Couldn't find a recognizable timeline (dates/years/quarters/weeks) "
        "in either the column headers or the first column's values."
    )


def _ensure_template_columns(df: pd.DataFrame, columns: list[str], period_columns: list[str]) -> pd.DataFrame:
    non_period_columns = [c for c in columns if c not in period_columns]
    entity_col = non_period_columns[0]
    extra_columns = [c for c in non_period_columns[1:] if c not in ("Category", "Image URL")]
    renamed = df.rename(columns={entity_col: "Entity Name"})

    parts = [renamed[["Entity Name"]]]
    for required in ("Category", "Image URL"):
        parts.append(renamed[[required]] if required in non_period_columns else pd.DataFrame({required: [""] * len(df)}))
    parts.append(renamed[extra_columns])
    parts.append(renamed[period_columns])
    return pd.concat(parts, axis=1)


def _transpose(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    entity_names = [c for c in df.columns if c != date_col]
    periods = df[date_col].astype(str).tolist()

    out = pd.DataFrame({"Entity Name": entity_names, "Category": "", "Image URL": ""})
    values = df[entity_names].T  # rows become entities, columns become periods
    values.columns = periods
    values = values.reset_index(drop=True)
    return pd.concat([out, values], axis=1)
