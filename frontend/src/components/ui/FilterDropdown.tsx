import React, { useState, useRef, useEffect, useCallback } from 'react'

interface FilterOption {
  value: string
  label: string
  count: number
  separator?: boolean
}

interface FilterDropdownProps {
  options: FilterOption[]
  value: string
  onChange: (value: string) => void
  className?: string
}

export default function FilterDropdown({
  options,
  value,
  onChange,
  className = '',
}: FilterDropdownProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const selected = options.find((o) => o.value === value) ?? options[0]

  const close = useCallback(() => setOpen(false), [])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        close()
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [open, close])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        close()
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, close])

  function handleSelect(opt: FilterOption) {
    onChange(opt.value)
    close()
    triggerRef.current?.focus()
  }

  function handleKeyDown(e: React.KeyboardEvent, opt: FilterOption) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      handleSelect(opt)
    }
  }

  return (
    <div ref={containerRef} className={`relative inline-block ${className}`}>
      {/* Trigger */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-sm hover:bg-gray-50 transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:ring-offset-1"
      >
        <span className="text-gray-500">Filtrar:</span>
        <span className="font-medium text-gray-700">
          {selected?.label ?? 'Todos'}
        </span>
        <span className="text-xs text-gray-400">
          ({selected?.count ?? 0})
        </span>
        <ChevronIcon open={open} />
      </button>

      {/* Dropdown */}
      {open && (
        <ul
          role="listbox"
          aria-activedescendant={`filter-option-${value}`}
          className="absolute z-20 mt-1 w-56 bg-white rounded-xl border border-gray-100 shadow-lg py-1 animate-in fade-in slide-in-from-top-1 duration-150"
        >
          {options.map((opt) => {
            const isSelected = opt.value === value
            return (
              <React.Fragment key={opt.value}>
                {opt.separator && (
                  <li
                    role="separator"
                    className="border-t border-gray-100 my-1"
                  />
                )}
                <li
                  id={`filter-option-${opt.value}`}
                  role="option"
                  aria-selected={isSelected}
                  tabIndex={0}
                  onClick={() => handleSelect(opt)}
                  onKeyDown={(e) => handleKeyDown(e, opt)}
                  className={`
                    px-3 py-2 text-sm flex justify-between items-center cursor-pointer transition-colors duration-100
                    ${
                      isSelected
                        ? 'bg-[#eff8ff] text-[#0693e3] border-l-2 border-l-[#0693e3]'
                        : 'hover:bg-gray-50 text-gray-700 border-l-2 border-l-transparent'
                    }
                  `}
                >
                  <span>{opt.label}</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full ${
                      isSelected
                        ? 'bg-[#0693e3]/10 text-[#0693e3]'
                        : 'bg-gray-100 text-gray-400'
                    }`}
                  >
                    {opt.count}
                  </span>
                </li>
              </React.Fragment>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`text-gray-400 transition-transform duration-200 ${
        open ? 'rotate-180' : ''
      }`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}
