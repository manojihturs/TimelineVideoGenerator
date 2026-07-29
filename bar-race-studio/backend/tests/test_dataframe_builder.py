import pandas as pd
import pytest

from app.models.config import ColumnMapping, SortDirection
from app.services.dataframe_builder import (
    build_long_dataframe,
    compute_frame_rankings,
    interpolate_frames,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "Entity": ["A", "B", "C"],
        "Category": ["X", "Y", "X"],
        "2020": [10, 30, 20],
        "2021": [20, 20, 40],
    })


@pytest.fixture
def mapping():
    return ColumnMapping(
        entity_column="Entity",
        category_column="Category",
        image_column=None,
        timeline_start_column="2020",
        timeline_end_column="2021",
        value_columns=["2020", "2021"],
    )


def test_build_long_dataframe_shape_and_values(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    assert set(long_df.columns) >= {"entity", "category", "value", "period_index"}
    assert len(long_df) == 6  # 3 entities x 2 periods

    a_2020 = long_df[(long_df.entity == "A") & (long_df.period_index == 0)]
    assert a_2020["value"].iloc[0] == 10
    assert a_2020["category"].iloc[0] == "X"


def test_build_long_dataframe_strips_currency_symbols(mapping):
    df = pd.DataFrame({"Entity": ["A"], "Category": ["X"], "2020": ["$1,234"], "2021": ["45%"]})
    long_df = build_long_dataframe(df, mapping)
    values = long_df.set_index("period_index")["value"]
    assert values[0] == 1234
    assert values[1] == 45


def test_interpolate_frames_no_interpolation(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=0)
    # one frame per period per entity, no in-betweens
    assert sorted(frames["frame_index"].unique()) == [0, 1]
    assert len(frames) == 6


def test_interpolate_frames_linear_midpoint(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=1)
    # entity A: 10 at period 0, 20 at period 1 -> midpoint frame should be 15
    midpoint = frames[(frames.entity == "A") & (frames.frame_index == 0.5)]
    assert midpoint["value"].iloc[0] == pytest.approx(15.0)

    # entity B: 30 -> 20, midpoint should be 25
    midpoint_b = frames[(frames.entity == "B") & (frames.frame_index == 0.5)]
    assert midpoint_b["value"].iloc[0] == pytest.approx(25.0)


def test_interpolate_frames_multiple_steps(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=3)
    # 2 anchor frames + 3 in-between per entity per transition (1 transition here)
    assert len(frames["frame_index"].unique()) == 5  # 0, 0.25, 0.5, 0.75, 1


def test_compute_frame_rankings_descending(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=0)
    ranked = compute_frame_rankings(frames, bar_count=2, sort_direction=SortDirection.DESCENDING)

    period_0 = ranked[ranked.frame_index == 0].sort_values("rank")
    # period 2020 values: A=10, B=30, C=20 -> top 2 descending: B(30), C(20)
    assert list(period_0["entity"]) == ["B", "C"]
    assert list(period_0["rank"]) == [1, 2]


def test_compute_frame_rankings_ascending(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=0)
    ranked = compute_frame_rankings(frames, bar_count=2, sort_direction=SortDirection.ASCENDING)

    period_0 = ranked[ranked.frame_index == 0].sort_values("rank")
    # ascending: smallest first -> A(10), C(20)
    assert list(period_0["entity"]) == ["A", "C"]


def test_compute_frame_rankings_respects_bar_count(sample_df, mapping):
    long_df = build_long_dataframe(sample_df, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=0)
    ranked = compute_frame_rankings(frames, bar_count=1, sort_direction=SortDirection.DESCENDING)
    assert len(ranked[ranked.frame_index == 0]) == 1


def test_empty_dataframe_does_not_crash(mapping):
    empty = pd.DataFrame(columns=["Entity", "Category", "2020", "2021"])
    long_df = build_long_dataframe(empty, mapping)
    frames = interpolate_frames(long_df, steps_per_transition=2)
    ranked = compute_frame_rankings(frames, bar_count=5, sort_direction=SortDirection.DESCENDING)
    assert ranked.empty
