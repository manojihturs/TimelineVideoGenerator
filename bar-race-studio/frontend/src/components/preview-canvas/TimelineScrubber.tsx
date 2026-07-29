import { useState } from 'react'

export function TimelineScrubber({ periods }: { periods: string[] }) {
  const [index, setIndex] = useState(0)
  if (periods.length === 0) {
    return <p className="text-xs text-gray-500">No timeline periods detected.</p>
  }
  return (
    <div className="flex h-full flex-col justify-center">
      <div className="mb-1 flex justify-between text-xs text-gray-400">
        <span>{periods[0]}</span>
        <span className="font-medium text-gray-200">{periods[index]}</span>
        <span>{periods[periods.length - 1]}</span>
      </div>
      <input
        type="range"
        min={0}
        max={periods.length - 1}
        value={index}
        onChange={(e) => setIndex(Number(e.target.value))}
        className="w-full accent-violet-600"
      />
    </div>
  )
}
