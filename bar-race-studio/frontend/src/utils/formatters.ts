import type { ValueFormat } from '../models/RaceConfig'

// Mirrors backend/app/services/value_formatting.py — kept in sync by hand.
export function formatValue(value: number, fmt: ValueFormat, decimalPlaces: number): string {
  switch (fmt) {
    case 'currency':
      return `$${value.toLocaleString(undefined, { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })}`
    case 'percentage':
      return `${value.toFixed(decimalPlaces)}%`
    case 'thousands':
      return `${(value / 1_000).toLocaleString(undefined, { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })}K`
    case 'millions':
      return `${(value / 1_000_000).toLocaleString(undefined, { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })}M`
    case 'billions':
      return `${(value / 1_000_000_000).toLocaleString(undefined, { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })}B`
    default:
      return value.toLocaleString(undefined, { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces })
  }
}
