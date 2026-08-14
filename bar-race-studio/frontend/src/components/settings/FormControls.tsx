import type { ReactNode } from 'react'

export function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string
  required?: boolean
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="mb-3 block text-xs">
      <span className="mb-1 block font-medium text-gray-400">
        {label}
        {required && <span className="ml-0.5 text-red-400">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-gray-500">{hint}</span>}
    </label>
  )
}

const inputClass =
  'w-full rounded-md border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-100 focus:border-violet-500 focus:outline-none'

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={inputClass} />
}

export function NumberInput({ min, max, onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!onChange) return
    const raw = e.target.value
    // Let the user clear the field or type a leading '-' without forcing a
    // clamp mid-edit -- only clamp once the value parses to a real number.
    if (raw === '' || raw === '-') return
    const parsed = Number(raw)
    if (Number.isNaN(parsed)) return
    let clamped = parsed
    if (min !== undefined && min !== '' && clamped < Number(min)) clamped = Number(min)
    if (max !== undefined && max !== '' && clamped > Number(max)) clamped = Number(max)
    if (clamped !== parsed) {
      e.target.value = String(clamped)
    }
    onChange(e)
  }
  return <input type="number" min={min} max={max} {...props} onChange={handleChange} className={inputClass} />
}

export function ColorInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type="color" {...props} className="h-8 w-full rounded-md border border-gray-700 bg-gray-900" />
}

export function SelectInput<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className={inputClass}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

export function ToggleInput({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
}) {
  return (
    <label className="mb-2 flex items-center justify-between text-sm text-gray-300">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-violet-600"
      />
    </label>
  )
}

export function PanelSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mb-5 border-b border-gray-800 pb-4 last:border-b-0">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
      {children}
    </div>
  )
}
