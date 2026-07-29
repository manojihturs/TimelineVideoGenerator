"""Turn a wide dataset (one row per entity, one column per timeline
period) into the exact frame-by-frame, ranked, interpolated shape the
renderer needs — the one place that owns "what does frame N look like"."""
import numpy as np
import pandas as pd

from app.models.config import ColumnMapping, SortDirection


def build_long_dataframe(df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    """Wide -> tidy: one row per (entity, period) with its value, plus the
    entity's category/image carried along. Values are coerced numeric —
    currency symbols/commas/percent signs are stripped first so
    "$1,234"/"45%"-style cells still parse."""
    id_vars = [mapping.entity_column]
    if mapping.category_column:
        id_vars.append(mapping.category_column)
    if mapping.image_column:
        id_vars.append(mapping.image_column)

    long_df = df.melt(
        id_vars=id_vars,
        value_vars=mapping.value_columns,
        var_name="period",
        value_name="value",
    )
    cleaned = long_df["value"].astype(str).str.replace(r"[,$€£%]", "", regex=True).str.strip()
    long_df["value"] = pd.to_numeric(cleaned, errors="coerce").fillna(0.0)

    long_df = long_df.rename(columns={
        mapping.entity_column: "entity",
        **({mapping.category_column: "category"} if mapping.category_column else {}),
        **({mapping.image_column: "image_url"} if mapping.image_column else {}),
    })
    if "category" not in long_df.columns:
        long_df["category"] = None
    if "image_url" not in long_df.columns:
        long_df["image_url"] = None

    # preserve chronological period order (mapping.value_columns is
    # already chronologically sorted by the timeline parser) rather than
    # whatever order melt/groupby would otherwise produce
    period_order = {p: i for i, p in enumerate(mapping.value_columns)}
    long_df["period_index"] = long_df["period"].map(period_order)
    return long_df.sort_values(["period_index", "entity"]).reset_index(drop=True)


def interpolate_frames(long_df: pd.DataFrame, steps_per_transition: int) -> pd.DataFrame:
    """Insert `steps_per_transition` linearly-interpolated in-between
    frames between every pair of consecutive periods, per entity — this
    is what makes bars glide instead of jump. steps_per_transition=0
    means no interpolation (one frame per period, a "snap" animation).
    Returns columns: frame_index (float, period_index-aligned), entity,
    category, image_url, value."""
    if long_df.empty:
        return long_df.assign(frame_index=pd.Series(dtype=float))

    entities = long_df[["entity", "category", "image_url"]].drop_duplicates("entity")
    period_indices = sorted(long_df["period_index"].unique())

    frame_rows = []
    for entity_row in entities.itertuples(index=False):
        entity_values = (
            long_df[long_df["entity"] == entity_row.entity]
            .set_index("period_index")["value"]
        )
        for i in range(len(period_indices)):
            p0 = period_indices[i]
            frame_rows.append((p0, entity_row.entity, entity_row.category, entity_row.image_url, entity_values.get(p0, 0.0)))
            if i + 1 < len(period_indices) and steps_per_transition > 0:
                p1 = period_indices[i + 1]
                v0, v1 = entity_values.get(p0, 0.0), entity_values.get(p1, 0.0)
                for step in range(1, steps_per_transition + 1):
                    t = step / (steps_per_transition + 1)
                    frame_index = p0 + t * (p1 - p0)
                    value = v0 + t * (v1 - v0)
                    frame_rows.append((frame_index, entity_row.entity, entity_row.category, entity_row.image_url, value))

    result = pd.DataFrame(frame_rows, columns=["frame_index", "entity", "category", "image_url", "value"])
    return result.sort_values(["frame_index", "entity"]).reset_index(drop=True)


def compute_frame_rankings(
    interpolated_df: pd.DataFrame,
    bar_count: int,
    sort_direction: SortDirection,
) -> pd.DataFrame:
    """Per frame_index, rank entities by value and keep only the top
    bar_count (or bottom bar_count, for ascending). Adds a `rank` column
    (1 = best per sort_direction)."""
    ascending = sort_direction == SortDirection.ASCENDING

    if interpolated_df.empty:
        return interpolated_df.assign(rank=pd.Series(dtype=int))

    ranked_frames = []
    for frame_index, frame in interpolated_df.groupby("frame_index"):
        ranked = frame.sort_values("value", ascending=ascending).reset_index(drop=True)
        ranked["rank"] = np.arange(1, len(ranked) + 1)
        ranked_frames.append(ranked.head(bar_count))

    return pd.concat(ranked_frames, ignore_index=True)
