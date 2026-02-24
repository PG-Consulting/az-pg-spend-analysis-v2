import React, { useState } from 'react'
import { tw } from '@/lib/design-tokens'

interface TabItem {
    id: string
    label: string
    badge?: string
    badgeColor?: string
    /** When true, the tab is non-interactive and shows a lock icon */
    locked?: boolean
    /** Tooltip text shown on hover when the tab is locked */
    lockedTooltip?: string
}

interface TabsProps {
    tabs: TabItem[]
    activeTab: string
    onTabChange: (tabId: string) => void
    disabled?: boolean
}

/** Small inline lock icon (SVG) shown on locked tabs */
function LockIcon() {
    return (
        <svg
            className="w-3.5 h-3.5 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
        >
            <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
        </svg>
    )
}

export default function Tabs({ tabs, activeTab, onTabChange, disabled }: TabsProps) {
    const [tooltipTabId, setTooltipTabId] = useState<string | null>(null)

    return (
        <div className="flex gap-1 w-full p-1.5 bg-white rounded-xl border border-gray-200 shadow-sm">
            {tabs.map((tab) => {
                const isLocked = tab.locked === true
                const isActive = activeTab === tab.id
                const isDisabled = disabled || isLocked

                return (
                    <div key={tab.id} className="relative flex-1">
                        <button
                            onClick={() => {
                                if (!disabled && !isLocked) onTabChange(tab.id)
                            }}
                            disabled={isDisabled}
                            onMouseEnter={() => isLocked ? setTooltipTabId(tab.id) : undefined}
                            onMouseLeave={() => isLocked ? setTooltipTabId(null) : undefined}
                            className={`
                                relative w-full py-3 px-2 text-sm font-medium transition-all duration-300 rounded-lg text-center flex items-center justify-center gap-2
                                ${isActive
                                    ? 'text-white bg-gradient-to-r from-[#1c0957] to-[#2a1177] shadow-md'
                                    : isLocked
                                        ? 'text-gray-400 bg-gray-50 cursor-not-allowed opacity-60'
                                        : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                                }
                                ${disabled && !isLocked ? 'cursor-not-allowed opacity-50' : ''}
                            `}
                        >
                            {isLocked && <LockIcon />}
                            <span className="truncate">{tab.label}</span>
                            {tab.badge && (
                                <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded-full ${
                                    isActive
                                        ? 'bg-white/20 text-white'
                                        : isLocked
                                            ? 'bg-gray-200 text-gray-400'
                                            : (tab.badgeColor || 'bg-[#eff8ff] text-[#045d94]')
                                }`}>
                                    {tab.badge}
                                </span>
                            )}
                            {isActive && (
                                <div className="absolute bottom-0 left-1/4 right-1/4 h-0.5 bg-[#38a8f5] rounded-full" />
                            )}
                        </button>

                        {/* Locked tooltip */}
                        {isLocked && tab.lockedTooltip && tooltipTabId === tab.id && (
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none">
                                <div className="whitespace-nowrap px-2 py-1 text-xs text-white bg-gray-900 rounded shadow-lg">
                                    {tab.lockedTooltip}
                                </div>
                            </div>
                        )}
                    </div>
                )
            })}
        </div>
    )
}
