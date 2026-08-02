import pandas as pd

from app.models.config import ColumnMapping, RaceConfig
from app.services.race_renderer import _resolve_colors


def _config(entity_column="Entity Name", category_column="Category"):
    mapping = ColumnMapping(
        entity_column=entity_column, category_column=category_column,
        timeline_start_column="2020", timeline_end_column="2021",
        value_columns=["2020", "2021"],
    )
    return RaceConfig(dataset_id="x", mapping=mapping, title="t", data_source_label="s")


def test_constant_category_falls_back_to_per_entity_colors():
    # every row shares the same category ("Browser") — a real dataset
    # this app has been fed (browser market share) hits this exact shape
    df = pd.DataFrame({
        "entity": ["Chrome", "Safari", "Firefox", "Edge"],
        "category": ["Browser", "Browser", "Browser", "Browser"],
        "value": [70, 15, 10, 5],
    })
    colors = _resolve_colors(df, _config())
    assert len(set(colors.values())) > 1, "all entities got the same color despite a constant category"


def test_varied_category_still_groups_by_category():
    df = pd.DataFrame({
        "entity": ["A", "B", "C", "D"],
        "category": ["X", "X", "Y", "Y"],
        "value": [10, 9, 8, 7],
    })
    colors = _resolve_colors(df, _config())
    assert colors["A"] == colors["B"]
    assert colors["C"] == colors["D"]
    assert colors["A"] != colors["C"]


def test_no_category_falls_back_to_per_entity_colors():
    df = pd.DataFrame({
        "entity": ["A", "B", "C"],
        "category": [None, None, None],
        "value": [3, 2, 1],
    })
    colors = _resolve_colors(df, _config(category_column=None))
    assert len(set(colors.values())) == 3
