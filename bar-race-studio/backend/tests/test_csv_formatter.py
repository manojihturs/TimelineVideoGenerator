import io

import pandas as pd
import pytest

from app.services.csv_formatter import FormatError, format_dataframe


def test_passthrough_adds_missing_category_and_image_columns():
    df = pd.read_csv(io.StringIO(
        "Country,1995-01,1995-02,1995-03\nToyota,100,110,120\nFord,90,95,99\n"
    ))
    out = format_dataframe(df)
    assert list(out.columns) == ["Entity Name", "Category", "Image URL", "1995-01", "1995-02", "1995-03"]
    assert out["Entity Name"].tolist() == ["Toyota", "Ford"]
    assert (out["Category"] == "").all()


def test_passthrough_preserves_existing_category_and_extra_columns():
    df = pd.read_csv(io.StringIO(
        "Entity Name,Category,Region,2020,2021\n"
        "A,Cat1,US,1,2\n"
        "B,Cat2,EU,3,4\n"
    ))
    out = format_dataframe(df)
    assert list(out.columns) == ["Entity Name", "Category", "Image URL", "Region", "2020", "2021"]
    assert out["Category"].tolist() == ["Cat1", "Cat2"]
    assert out["Region"].tolist() == ["US", "EU"]


def test_transposes_date_rows_into_entity_rows():
    df = pd.read_csv(io.StringIO(
        "Date,Chrome,Safari,Firefox\n"
        "2025-01,60,20,10\n"
        "2025-02,61,19,10\n"
        "2025-03,62,18,9\n"
    ))
    out = format_dataframe(df)
    assert list(out.columns) == ["Entity Name", "Category", "Image URL", "2025-01", "2025-02", "2025-03"]
    assert sorted(out["Entity Name"].tolist()) == ["Chrome", "Firefox", "Safari"]
    chrome_row = out[out["Entity Name"] == "Chrome"].iloc[0]
    assert [chrome_row["2025-01"], chrome_row["2025-02"], chrome_row["2025-03"]] == [60, 61, 62]


def test_fills_blank_image_urls_with_verified_logos_for_known_browsers():
    df = pd.read_csv(io.StringIO(
        "Date,Chrome,Safari\n2025-01,60,20\n2025-02,61,19\n"
    ))
    out = format_dataframe(df)
    urls = dict(zip(out["Entity Name"], out["Image URL"]))
    assert urls["Chrome"] == (
        "https://raw.githubusercontent.com/alrra/browser-logos/master/src/chrome/chrome_128x128.png"
    )
    assert urls["Safari"] == (
        "https://raw.githubusercontent.com/alrra/browser-logos/master/src/safari/safari_128x128.png"
    )


def test_falls_back_to_guessed_clearbit_logo_for_unknown_entities():
    df = pd.read_csv(io.StringIO(
        "Date,Acme Corp\n2025-01,60\n2025-02,61\n"
    ))
    out = format_dataframe(df)
    assert out["Image URL"].iloc[0] == "https://logo.clearbit.com/acmecorp.com"


def test_does_not_overwrite_an_existing_image_url():
    df = pd.read_csv(io.StringIO(
        "Entity Name,Category,Image URL,2020,2021\n"
        "A,,https://example.com/a.png,1,2\n"
        "B,,,3,4\n"
    ))
    out = format_dataframe(df)
    urls = dict(zip(out["Entity Name"], out["Image URL"]))
    assert urls["A"] == "https://example.com/a.png"
    assert urls["B"] == "https://logo.clearbit.com/b.com"


def test_rejects_file_with_no_recognizable_timeline():
    df = pd.read_csv(io.StringIO(
        "Name,Score,Rank\nA,10,1\nB,9,2\n"
    ))
    with pytest.raises(FormatError):
        format_dataframe(df)
