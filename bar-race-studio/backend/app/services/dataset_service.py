"""Load an uploaded CSV/XLSX into a pandas DataFrame — the one place that
knows how to read either format, so every other service just works with
a DataFrame."""
from pathlib import Path

import pandas as pd


def load_dataframe(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".xlsx", ".xls"):
        # first sheet only, per spec
        return pd.read_excel(path, sheet_name=0)
    raise ValueError(f"Unsupported file type: {suffix}")
