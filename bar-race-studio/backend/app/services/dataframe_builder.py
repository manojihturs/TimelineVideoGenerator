"""Turn a wide dataset (one row per entity, one column per timeline
period) into the exact frame-by-frame, ranked, interpolated shape the
renderer needs — the one place that owns "what does frame N look like"."""
import pandas as pd

from app.models.config import ColumnMapping, Interpolation, SortDirection


def _ease(t: float, interpolation: Interpolation) -> float:
    """Remaps a linear 0-1 progress value into an eased curve — this is
    what actually produces a "slow motion" feel: easeInOut starts and
    ends each transition slowly and moves fastest through the middle,
    rather than the constant, mechanical speed a plain linear
    interpolation (t unchanged) produces."""
    if interpolation == Interpolation.LINEAR:
        return t
    if interpolation == Interpolation.EASE_IN:
        return t * t
    if interpolation == Interpolation.EASE_OUT:
        return 1 - (1 - t) * (1 - t)
    # EASE_IN_OUT (default) — smoothstep
    return t * t * (3 - 2 * t)


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


def _period_ranks(long_df: pd.DataFrame, sort_direction: SortDirection) -> dict[tuple[int, str], int]:
    """Real, non-interpolated rank (1 = best per sort_direction) of every
    entity at every period — the anchor points interpolate_frames eases a
    continuous *position* between, so an overtake slides across the whole
    transition instead of snapping the instant an interpolated value
    crosses a neighbor's. Ties are broken by entity name so the anchor
    order is deterministic."""
    ascending = sort_direction == SortDirection.ASCENDING
    ordered = long_df.sort_values(["period_index", "value", "entity"], ascending=[True, ascending, True])
    ranks = ordered.groupby("period_index").cumcount() + 1
    return dict(zip(zip(ordered["period_index"], ordered["entity"]), ranks))


def interpolate_frames(
    long_df: pd.DataFrame,
    steps_per_transition: int,
    sort_direction: SortDirection = SortDirection.DESCENDING,
    interpolation: Interpolation = Interpolation.EASE_IN_OUT,
) -> pd.DataFrame:
    """Insert `steps_per_transition` interpolated in-between frames
    between every pair of consecutive periods, per entity — this is what
    makes bars glide instead of jump. `interpolation` shapes *how* they
    glide (see _ease); frame_index itself always advances linearly with
    step so playback timing stays even, only the interpolated value and
    rank follow the eased curve. Rank here is the entity's real,
    non-interpolated rank at each anchor period, eased the same way value
    is — the renderer then plots each bar at this continuous rank instead
    of a position re-derived from an instantaneous value sort, so a lead
    change slides smoothly across the whole transition rather than
    snapping into its new slot the instant the (also-interpolated) values
    cross. steps_per_transition=0 means no interpolation (one frame per
    period, a "snap" animation). Returns columns: frame_index (float,
    period_index-aligned), entity, category, image_url, value, rank
    (float, 1 = best)."""
    if long_df.empty:
        return long_df.assign(frame_index=pd.Series(dtype=float), rank=pd.Series(dtype=float))

    entities = long_df[["entity", "category", "image_url"]].drop_duplicates("entity")
    period_indices = sorted(long_df["period_index"].unique())
    period_ranks = _period_ranks(long_df, sort_direction)

    frame_rows = []
    for entity_row in entities.itertuples(index=False):
        entity_values = (
            long_df[long_df["entity"] == entity_row.entity]
            .set_index("period_index")["value"]
        )
        for i in range(len(period_indices)):
            p0 = period_indices[i]
            rank0 = period_ranks[(p0, entity_row.entity)]
            frame_rows.append((p0, entity_row.entity, entity_row.category, entity_row.image_url,
                                entity_values.get(p0, 0.0), float(rank0)))
            if i + 1 < len(period_indices) and steps_per_transition > 0:
                p1 = period_indices[i + 1]
                v0, v1 = entity_values.get(p0, 0.0), entity_values.get(p1, 0.0)
                rank1 = period_ranks[(p1, entity_row.entity)]
                for step in range(1, steps_per_transition + 1):
                    t = step / (steps_per_transition + 1)
                    eased_t = _ease(t, interpolation)
                    frame_index = p0 + t * (p1 - p0)  # linear — controls playback timing, not motion feel
                    value = v0 + eased_t * (v1 - v0)  # eased — controls how the bar actually glides
                    rank = rank0 + eased_t * (rank1 - rank0)  # eased — controls how the bar's slot glides
                    frame_rows.append((frame_index, entity_row.entity, entity_row.category, entity_row.image_url, value, rank))

    result = pd.DataFrame(frame_rows, columns=["frame_index", "entity", "category", "image_url", "value", "rank"])
    return result.sort_values(["frame_index", "entity"]).reset_index(drop=True)


def compute_frame_rankings(
    interpolated_df: pd.DataFrame,
    bar_count: int,
) -> pd.DataFrame:
    """Per frame_index, keep only entities within the top bar_count by the
    continuous rank interpolate_frames already assigned. Deliberately does
    not re-sort by value here — that would recompute a fresh, discrete
    order from the instantaneous interpolated value every substep and
    reintroduce the instant position-snap this module exists to avoid.

    Also attaches `period_total` — the sum of every entity's value at that
    frame_index, not just the visible top bar_count — computed here while
    the full (unfiltered) set of entities is still available, since it's
    gone once we drop everyone outside the top bar_count below."""
    if interpolated_df.empty:
        return interpolated_df.assign(period_total=pd.Series(dtype=float))

    totals = interpolated_df.groupby("frame_index")["value"].transform("sum")
    interpolated_df = interpolated_df.assign(period_total=totals)

    ranked_frames = []
    for _, frame in interpolated_df.groupby("frame_index"):
        kept = frame[frame["rank"] <= bar_count].sort_values("rank").reset_index(drop=True)
        ranked_frames.append(kept)

    return pd.concat(ranked_frames, ignore_index=True)
