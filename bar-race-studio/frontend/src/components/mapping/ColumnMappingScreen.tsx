import type { DetectedColumns } from '../../models/DatasetSchema'

interface Props {
  columns: string[]
  detected: DetectedColumns
}

const MAX_INLINE_VALUES = 12

function ColumnRow({ label, value }: { label: string; value: string | string[] | null }) {
  let display: string
  if (Array.isArray(value)) {
    const shown = value.slice(0, MAX_INLINE_VALUES).join(', ')
    const hiddenCount = value.length - MAX_INLINE_VALUES
    display = hiddenCount > 0 ? `${shown}, +${hiddenCount} more` : shown
  } else {
    display = value ?? '—'
  }
  return (
    <div className="flex items-center justify-between border-b border-gray-800 py-2 text-sm">
      <span className="text-gray-400">{label}</span>
      <span className="font-medium text-gray-100">{display}</span>
    </div>
  )
}

export function ColumnMappingScreen({ detected }: Props) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
      <h3 className="mb-2 text-sm font-semibold text-gray-300">Suggested mapping</h3>
      <ColumnRow label="Entity column" value={detected.entity_column} />
      <ColumnRow label="Category column" value={detected.category_column} />
      <ColumnRow label="Image column" value={detected.image_column} />
      <ColumnRow
        label="Timeline range"
        value={
          detected.timeline_start_column && detected.timeline_end_column
            ? `${detected.timeline_start_column} → ${detected.timeline_end_column}`
            : null
        }
      />
      <ColumnRow label="Timeline format" value={detected.timeline_format} />
      <ColumnRow label="Value columns" value={detected.value_columns} />
    </div>
  )
}
