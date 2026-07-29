interface Props {
  frameIndices: number[]
  currentIndex: number
  onChange: (index: number) => void
  periodLabel: (frameIndex: number) => string
}

export function TimelineScrubber({ frameIndices, currentIndex, onChange, periodLabel }: Props) {
  if (frameIndices.length === 0) {
    return <p className="text-xs text-gray-500">No timeline periods detected.</p>
  }
  const current = frameIndices[Math.min(currentIndex, frameIndices.length - 1)]
  return (
    <div className="flex h-full flex-col justify-center">
      <div className="mb-1 flex justify-between text-xs text-gray-400">
        <span>{periodLabel(frameIndices[0])}</span>
        <span className="font-medium text-gray-200">{periodLabel(current)}</span>
        <span>{periodLabel(frameIndices[frameIndices.length - 1])}</span>
      </div>
      <input
        type="range"
        min={0}
        max={frameIndices.length - 1}
        value={currentIndex}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-violet-600"
      />
    </div>
  )
}
