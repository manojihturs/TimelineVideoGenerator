import type { DatasetPreview } from '../../models/DatasetSchema'

// Datasets this app targets routinely have hundreds of period columns
// (e.g. 30 years of monthly data = 360+). Rendering every one of them in
// a preview table — just to sanity-check the data before mapping — was
// measured to make the page unresponsive for several seconds on a
// realistic dataset; nobody actually needs to see all 360 side by side
// here, so the preview caps at a fixed count and just says how many more
// there are.
const MAX_PREVIEW_COLUMNS = 15

export function DataPreviewTable({ preview }: { preview: DatasetPreview }) {
  const columns = preview.columns.slice(0, MAX_PREVIEW_COLUMNS)
  const hiddenCount = preview.columns.length - columns.length

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-gray-900 text-gray-400">
          <tr>
            {columns.map((col) => (
              <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                {col}
              </th>
            ))}
            {hiddenCount > 0 && (
              <th className="whitespace-nowrap px-3 py-2 font-medium italic text-gray-500">
                +{hiddenCount} more column{hiddenCount === 1 ? '' : 's'}
              </th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {preview.rows.map((row, i) => (
            <tr key={i} className="text-gray-200">
              {columns.map((col) => (
                <td key={col} className="whitespace-nowrap px-3 py-2">
                  {String(row[col] ?? '')}
                </td>
              ))}
              {hiddenCount > 0 && <td className="px-3 py-2 text-gray-600">…</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
