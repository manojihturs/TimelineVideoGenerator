from app.services.timeline_parser import detect_timeline_columns


def test_year_month_headers():
    cols = ["Country", "Region", "1995-01", "1995-02", "1995-03", "2024-12"]
    detected, fmt = detect_timeline_columns(cols)
    assert fmt == "year_month"
    assert detected == ["1995-01", "1995-02", "1995-03", "2024-12"]


def test_bare_year_headers_unordered():
    cols = ["Name", "2012", "2010", "2011"]
    detected, fmt = detect_timeline_columns(cols)
    assert fmt == "year"
    assert detected == ["2010", "2011", "2012"]  # chronological, not file order


def test_month_name_headers():
    cols = ["Entity", "Jan", "Feb", "Mar"]
    detected, fmt = detect_timeline_columns(cols)
    assert fmt == "month_name"
    assert detected == ["Jan", "Feb", "Mar"]


def test_week_headers():
    cols = ["Item", "Week 2", "Week 1", "Week 3"]
    detected, fmt = detect_timeline_columns(cols)
    assert fmt == "week"
    assert detected == ["Week 1", "Week 2", "Week 3"]


def test_quarter_headers():
    cols = ["Company", "Q2", "Q1", "Q3", "Q4"]
    detected, fmt = detect_timeline_columns(cols)
    assert fmt == "quarter"
    assert detected == ["Q1", "Q2", "Q3", "Q4"]


def test_no_timeline_columns():
    cols = ["Name", "Category", "Notes"]
    detected, fmt = detect_timeline_columns(cols)
    assert detected == []
    assert fmt is None
