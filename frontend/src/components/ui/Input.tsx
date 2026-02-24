import React from 'react'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
  icon?: React.ReactNode
}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, icon, className = '', id, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

    return (
      <div className={className}>
        {label && (
          <label
            htmlFor={inputId}
            className="text-sm font-medium text-[#32373c] mb-1.5 block"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={[
              'h-10 w-full rounded-xl border bg-white text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors',
              'placeholder:text-gray-300',
              'focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none',
              'disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-50',
              error ? 'border-red-300' : 'border-gray-200',
              icon ? 'pl-10 pr-3' : 'px-3',
            ].join(' ')}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={
              error
                ? `${inputId}-error`
                : hint
                  ? `${inputId}-hint`
                  : undefined
            }
            {...props}
          />
        </div>
        {error && (
          <p id={`${inputId}-error`} className="text-xs text-red-500 mt-1" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${inputId}-hint`} className="text-xs text-gray-400 mt-1">
            {hint}
          </p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

export default Input
