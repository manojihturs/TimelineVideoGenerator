import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import type { RaceConfig } from '../models/RaceConfig'

interface RaceConfigContextValue {
  config: RaceConfig
  updateConfig: (patch: Partial<RaceConfig>) => void
  setConfig: (config: RaceConfig) => void
}

const RaceConfigContext = createContext<RaceConfigContextValue | null>(null)

export function RaceConfigProvider({
  initialConfig,
  children,
}: {
  initialConfig: RaceConfig
  children: ReactNode
}) {
  const [config, setConfig] = useState<RaceConfig>(initialConfig)

  const value = useMemo<RaceConfigContextValue>(
    () => ({
      config,
      setConfig,
      updateConfig: (patch) => setConfig((prev) => ({ ...prev, ...patch })),
    }),
    [config],
  )

  return <RaceConfigContext.Provider value={value}>{children}</RaceConfigContext.Provider>
}

export function useRaceConfig(): RaceConfigContextValue {
  const ctx = useContext(RaceConfigContext)
  if (!ctx) throw new Error('useRaceConfig must be used within a RaceConfigProvider')
  return ctx
}
