import pandas as pd

from app.services.column_detector import detect_columns


def test_detects_entity_category_and_timeline():
    df = pd.DataFrame({
        "Country Name": ["USA", "India", "China", "Brazil"],
        "Region": ["Americas", "Asia", "Asia", "Americas"],
        "Image URL": [
            "https://example.com/usa.png",
            "https://example.com/india.png",
            "https://example.com/china.png",
            "https://example.com/brazil.png",
        ],
        "2020": [100, 200, 300, 50],
        "2021": [110, 210, 310, 55],
        "2022": [120, 220, 320, 60],
    })
    result = detect_columns(df)
    assert result.entity_column == "Country Name"
    assert result.category_column == "Region"
    assert result.image_column == "Image URL"
    assert result.value_columns == ["2020", "2021", "2022"]
    assert result.timeline_format == "year"


def test_no_image_column_detected_when_absent():
    df = pd.DataFrame({
        "Brand": ["A", "B", "C"],
        "1995-01": [1, 2, 3],
        "1995-02": [2, 3, 4],
    })
    result = detect_columns(df)
    assert result.image_column is None
    assert result.entity_column == "Brand"
    assert result.timeline_format == "year_month"
