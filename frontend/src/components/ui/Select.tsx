import React from 'react'

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  hint?: string
  error?: string
  options: Array<{ value: string; label: string; disabled?: boolean }>
  placeholder?: string
}

const ChevronDown = () => (
  <svg
    className="h-4 w-4 text-gray-400 pointer-events-none"
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
      clipRule="evenodd"
    />
  </svg>
)

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, hint, error, options, placeholder, className = '', id, ...props }, ref) => {
    const selectId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

    return (
      <div className={className}>
        {label && (
          <label
            htmlFor={selectId}
            className="text-sm font-medium text-[#32373c] mb-1.5 block"
          >
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={[
              'h-10 w-full rounded-xl border bg-white pl-3 pr-8 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors appearance-none',
              'focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none',
              'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50',
              error ? 'border-red-300' : 'border-gray-200',
            ].join(' ')}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={
              error
                ? `${selectId}-error`
                : hint
                  ? `${selectId}-hint`
                  : undefined
            }
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center">
            <ChevronDown />
          </div>
        </div>
        {error && (
          <p id={`${selectId}-error`} className="text-xs text-red-500 mt-1" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${selectId}-hint`} className="text-xs text-gray-400 mt-1">
            {hint}
          </p>
        )}
      </div>
    )
  }
)

Select.displayName = 'Select'

export default Select
