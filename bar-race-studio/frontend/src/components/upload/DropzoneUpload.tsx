import { useCallback, useState } from 'react'

interface Props {
  onFileSelected: (file: File) => void
  accept?: string
}

export function DropzoneUpload({ onFileSelected, accept = '.csv,.xlsx,.xls' }: Props) {
  const [isDragging, setIsDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) onFileSelected(file)
    },
    [onFileSelected],
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-16 text-center transition-colors ${
        isDragging ? 'border-violet-400 bg-violet-500/10' : 'border-gray-700 bg-gray-900/40'
      }`}
    >
      <p className="mb-2 text-lg font-medium text-gray-100">
        Drag &amp; drop a CSV or XLSX file
      </p>
      <p className="mb-4 text-sm text-gray-400">or</p>
      <label className="cursor-pointer rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500">
        Browse files
        <input
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onFileSelected(file)
          }}
        />
      </label>
    </div>
  )
}
