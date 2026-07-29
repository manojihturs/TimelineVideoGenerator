"""Turn a raw numeric value into the display string a given
RaceConfig.value_format calls for."""
from app.models.config import ValueFormat


def format_value(value: float, fmt: ValueFormat, decimal_places: int) -> str:
    if fmt == ValueFormat.CURRENCY:
        return f"${value:,.{decimal_places}f}"
    if fmt == ValueFormat.PERCENTAGE:
        return f"{value:.{decimal_places}f}%"
    if fmt == ValueFormat.THOUSANDS:
        return f"{value / 1_000:,.{decimal_places}f}K"
    if fmt == ValueFormat.MILLIONS:
        return f"{value / 1_000_000:,.{decimal_places}f}M"
    if fmt == ValueFormat.BILLIONS:
        return f"{value / 1_000_000_000:,.{decimal_places}f}B"
    return f"{value:,.{decimal_places}f}"
