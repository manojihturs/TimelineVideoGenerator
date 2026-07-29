import type { DatasetPreview } from '../../models/DatasetSchema'

export function DataPreviewTable({ preview }: { preview: DatasetPreview }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-gray-900 text-gray-400">
          <tr>
            {preview.columns.map((col) => (
              <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {preview.rows.map((row, i) => (
            <tr key={i} className="text-gray-200">
              {preview.columns.map((col) => (
                <td key={col} className="whitespace-nowrap px-3 py-2">
                  {String(row[col] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
