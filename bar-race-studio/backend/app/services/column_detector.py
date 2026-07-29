"""Heuristics that suggest a column mapping for any dataset — entity,
category, image, and timeline/value columns are inferred from column
shape (cardinality, value patterns, header format), never from column
names or position. The mapping screen always lets the user override
these suggestions before anything downstream runs."""
import re

import pandas as pd

from app.core.settings import DETECTION_SAMPLE_ROWS
from app.models.dataset import DetectedColumns
from app.services.timeline_parser import detect_timeline_columns

_URL_OR_IMAGE_RE = re.compile(r"^(https?://\S+|\S+\.(png|jpe?g|svg|webp|gif))$", re.IGNORECASE)


def _looks_like_image_column(series: pd.Series) -> bool:
    sample = series.dropna().astype(str).head(DETECTION_SAMPLE_ROWS)
    if sample.empty:
        return False
    hits = sample.apply(lambda v: bool(_URL_OR_IMAGE_RE.match(v.strip())))
    return hits.mean() > 0.6


def _is_mostly_numeric(series: pd.Series) -> bool:
    cleaned = (
        series.astype(str)
        .str.replace(r"[,$€£%]", "", regex=True)
        .str.strip()
    )
    numeric = pd.to_numeric(cleaned, errors="coerce")
    non_null = series.notna().sum()
    return non_null > 0 and numeric.notna().sum() / non_null > 0.8


def detect_columns(df: pd.DataFrame) -> DetectedColumns:
    sample = df.head(DETECTION_SAMPLE_ROWS)
    columns = list(df.columns)

    timeline_columns, timeline_format = detect_timeline_columns(columns)
    non_timeline_columns = [c for c in columns if c not in timeline_columns]

    image_column = next(
        (c for c in non_timeline_columns if _looks_like_image_column(sample[c])), None
    )

    text_columns = [
        c for c in non_timeline_columns
        if c != image_column and not _is_mostly_numeric(sample[c])
    ]

    entity_column = None
    category_column = None
    if text_columns:
        # entity = highest-cardinality text column (most likely unique per row)
        cardinalities = {c: sample[c].nunique(dropna=True) for c in text_columns}
        entity_column = max(cardinalities, key=cardinalities.get)
        # category = a lower-cardinality text column, distinct from entity
        remaining = [c for c in text_columns if c != entity_column]
        if remaining:
            low_card = {c: cardinalities.get(c, sample[c].nunique(dropna=True)) for c in remaining}
            best_category = min(low_card, key=low_card.get)
            # only worth calling it a "category" if it actually groups rows
            # (fewer distinct values than rows), not just another id column
            if low_card[best_category] < len(sample):
                category_column = best_category

    return DetectedColumns(
        entity_column=entity_column,
        category_column=category_column,
        image_column=image_column,
        timeline_start_column=timeline_columns[0] if timeline_columns else None,
        timeline_end_column=timeline_columns[-1] if timeline_columns else None,
        value_columns=timeline_columns,
        timeline_format=timeline_format,
    )
