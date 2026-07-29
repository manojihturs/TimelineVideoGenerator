import type { ReactNode } from 'react'

interface Props {
  left: ReactNode
  center: ReactNode
  bottom: ReactNode
  header?: ReactNode
}

/** The 3-pane studio layout: settings on the left, live preview in the
 * center, timeline scrubber along the bottom — matches the editor shape
 * described in the spec. */
export function AppShell({ left, center, bottom, header }: Props) {
  return (
    <div className="flex h-screen flex-col bg-[#0b0f14] text-gray-100">
      {header && <div className="border-b border-gray-800 px-4 py-2">{header}</div>}
      <div className="flex min-h-0 flex-1">
        <aside className="w-80 shrink-0 overflow-y-auto border-r border-gray-800 bg-gray-950/40 p-4">
          {left}
        </aside>
        <main className="flex flex-1 items-center justify-center overflow-auto p-6">
          {center}
        </main>
      </div>
      <footer className="h-24 shrink-0 border-t border-gray-800 bg-gray-950/40 p-3">
        {bottom}
      </footer>
    </div>
  )
}
