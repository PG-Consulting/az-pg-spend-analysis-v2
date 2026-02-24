import React, { useState, useEffect, useRef, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface SessionEntry {
  sessionId: string
  filename: string
  timestamp: string | number
  jobStatus?: 'PENDING' | 'PROCESSING' | 'CLASSIFIED' | 'ERROR'
  reviewState?: 'pending' | 'in_progress' | 'completed'
}

export interface CollapsibleSidebarProps {
  /** Active project info (null = no project selected) */
  activeProject: {
    project_id: string
    display_name: string
    sector: string
  } | null

  /** Session list */
  sessions: SessionEntry[]
  activeSessionId: string | null
  onSessionSelect: (id: string) => void

  /** Actions */
  onNewSession: () => void
  onOpenKB: () => void
  onClearHistory?: () => void
  onDeleteSession?: (id: string) => void

  /** Render prop for the ProjectSelect dropdown (gets collapsed state) */
  renderProjectSelect: (opts: { collapsed: boolean }) => React.ReactNode
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'sidebar-pinned'
const HOVER_DELAY_MS = 300
const COLLAPSED_WIDTH = 'w-16'
const EXPANDED_WIDTH = 'w-64'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase()
}

function formatTimestamp(ts: string | number): string {
  const d = new Date(ts)
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Truncate a filename to fit the compact session row */
function truncateFilename(name: string, maxLen = 18): string {
  if (name.length <= maxLen) return name
  const ext = name.lastIndexOf('.')
  if (ext > 0 && name.length - ext <= 5) {
    const base = name.slice(0, ext)
    const extension = name.slice(ext)
    const available = maxLen - extension.length - 1 // 1 for ellipsis char
    if (available > 3) {
      return base.slice(0, available) + '\u2026' + extension
    }
  }
  return name.slice(0, maxLen - 1) + '\u2026'
}

// ─── Status helpers ───────────────────────────────────────────────────────────

type SessionVisualStatus = 'active' | 'processing' | 'error' | 'classified' | 'reviewing' | 'completed' | 'idle'

function resolveSessionStatus(
  session: SessionEntry,
  isActive: boolean,
): SessionVisualStatus {
  if (session.jobStatus === 'PROCESSING' || session.jobStatus === 'PENDING') return 'processing'
  if (session.jobStatus === 'ERROR') return 'error'
  if (isActive) return 'active'
  if (session.reviewState === 'completed') return 'completed'
  if (session.reviewState === 'in_progress') return 'reviewing'
  if (session.jobStatus === 'CLASSIFIED') return 'classified'
  return 'idle'
}

// ─── Tooltip wrapper ──────────────────────────────────────────────────────────

function Tooltip({
  label,
  children,
  side = 'right',
}: {
  label: string
  children: React.ReactNode
  side?: 'right' | 'bottom'
}) {
  const positionClasses =
    side === 'right'
      ? 'left-full ml-3 top-1/2 -translate-y-1/2'
      : 'top-full mt-2 left-1/2 -translate-x-1/2'

  return (
    <div className="relative group/tip">
      {children}
      <div
        className={`
          pointer-events-none absolute z-50 ${positionClasses}
          whitespace-nowrap rounded-lg bg-[#0e1b38] px-2.5 py-1.5
          text-[11px] font-medium text-white/90 shadow-xl
          border border-white/10
          opacity-0 scale-95 group-hover/tip:opacity-100 group-hover/tip:scale-100
          transition-all duration-150
        `}
      >
        {label}
      </div>
    </div>
  )
}

// ─── Status dot component ─────────────────────────────────────────────────────

function StatusDot({ status, size = 'sm' }: { status: SessionVisualStatus; size?: 'sm' | 'md' }) {
  const dim = size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5'

  switch (status) {
    case 'active':
      return (
        <span
          className={`${dim} rounded-full bg-[#0693e3] shadow-[0_0_12px_rgba(6,147,227,0.5)] shrink-0`}
        />
      )
    case 'processing':
      return (
        <span
          className={`${dim} rounded-full bg-[#0693e3] animate-pulse shadow-[0_0_8px_rgba(6,147,227,0.4)] shrink-0`}
        />
      )
    case 'error':
      return <span className={`${dim} rounded-full bg-red-400 shrink-0`} />
    case 'completed':
      return (
        <span className={`${dim} rounded-full bg-[#7bdcb5] shrink-0 flex items-center justify-center`}>
          {size === 'md' && (
            <svg className="w-1.5 h-1.5 text-[#0e1b38]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={4} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </span>
      )
    case 'reviewing':
      return <span className={`${dim} rounded-full bg-amber-400 shrink-0`} />
    case 'classified':
      return <span className={`${dim} rounded-full bg-[#9b51e0] shrink-0`} />
    default:
      return <span className={`${dim} rounded-full bg-white/20 shrink-0`} />
  }
}

// ─── Collapsed session dot ────────────────────────────────────────────────────

function CollapsedSessionDot({
  session,
  isActive,
  onClick,
}: {
  session: SessionEntry
  isActive: boolean
  onClick: () => void
}) {
  const status = resolveSessionStatus(session, isActive)

  return (
    <Tooltip label={session.filename}>
      <button
        onClick={onClick}
        className={`
          w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200
          ${isActive
            ? 'bg-white/15 ring-1 ring-[#0693e3]/40'
            : 'hover:bg-white/10'
          }
        `}
      >
        <StatusDot status={status} size="md" />
      </button>
    </Tooltip>
  )
}

// ─── Expanded session row ─────────────────────────────────────────────────────

function ExpandedSessionRow({
  session,
  isActive,
  onClick,
  onDelete,
}: {
  session: SessionEntry
  isActive: boolean
  onClick: () => void
  onDelete?: () => void
}) {
  const status = resolveSessionStatus(session, isActive)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete?.()
  }

  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left px-3 py-2 rounded-lg transition-all duration-200 group relative
        ${isActive
          ? 'bg-white/[0.12] border-l-2 border-[#0693e3]'
          : 'hover:bg-white/[0.06] border-l-2 border-transparent'
        }
      `}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <StatusDot status={status} size="sm" />

        <div className="flex-1 min-w-0">
          <p
            className={`text-xs font-medium truncate leading-tight ${
              isActive ? 'text-white' : 'text-white/70 group-hover:text-white/90'
            }`}
          >
            {session.filename}
          </p>
        </div>

        <span className="text-[10px] text-white/30 tabular-nums shrink-0">
          {formatTimestamp(session.timestamp)}
        </span>
      </div>

      {/* Processing indicator */}
      {(session.jobStatus === 'PROCESSING' || session.jobStatus === 'PENDING') && (
        <div className="mt-1 ml-4.5 flex items-center gap-1.5">
          <svg className="w-2.5 h-2.5 text-[#0693e3] animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-[10px] text-[#38a8f5]">
            {session.jobStatus === 'PROCESSING' ? 'Classificando...' : 'Na fila...'}
          </span>
        </div>
      )}

      {/* Delete button (hover-only) */}
      {onDelete && (
        <div
          onClick={handleDelete}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded-md
                     opacity-0 group-hover:opacity-100
                     hover:bg-red-500/20 text-white/30 hover:text-red-400
                     transition-all cursor-pointer"
          title="Excluir sessão"
        >
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </div>
      )}
    </button>
  )
}

// ─── Icon components ──────────────────────────────────────────────────────────

function LogoMark() {
  return (
    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#1e3a8a] to-[#2563eb] flex items-center justify-center shadow-lg shadow-[#2563eb]/30">
      <span className="text-xs font-black text-white leading-none tracking-tight">PG</span>
    </div>
  )
}

function KBIcon() {
  return (
    <svg className="w-4.5 h-4.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
      />
    </svg>
  )
}

function PlusIcon({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  )
}

function PinIcon({ pinned }: { pinned: boolean }) {
  if (pinned) {
    // Filled pin (pinned state)
    return (
      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
        <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z" />
      </svg>
    )
  }
  // Outline pin (unpinned)
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"
      />
    </svg>
  )
}

function ChevronDoubleRight({ className = 'w-4 h-4' }: { className?: string }) {
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.8}
        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
      />
    </svg>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function CollapsibleSidebar({
  activeProject,
  sessions,
  activeSessionId,
  onSessionSelect,
  onNewSession,
  onOpenKB,
  onClearHistory,
  onDeleteSession,
  renderProjectSelect,
}: CollapsibleSidebarProps) {
  // ── State ─────────────────────────────────────────────────────────────────

  const [pinned, setPinned] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [hoverExpanded, setHoverExpanded] = useState(false)
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sidebarRef = useRef<HTMLElement>(null)

  const expanded = pinned || hoverExpanded

  // ── Hydrate pin state from localStorage (after mount to avoid SSR mismatch)
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'true') setPinned(true)
    setHydrated(true)
  }, [])

  // ── Persist pin state ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!hydrated) return
    localStorage.setItem(STORAGE_KEY, String(pinned))
  }, [pinned, hydrated])

  // ── Hover expand logic ────────────────────────────────────────────────────

  const handleMouseEnter = useCallback(() => {
    if (pinned) return
    hoverTimerRef.current = setTimeout(() => {
      setHoverExpanded(true)
    }, HOVER_DELAY_MS)
  }, [pinned])

  const handleMouseLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current)
      hoverTimerRef.current = null
    }
    if (!pinned) {
      setHoverExpanded(false)
    }
  }, [pinned])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    }
  }, [])

  // ── Toggle pin ────────────────────────────────────────────────────────────

  const togglePin = useCallback(() => {
    setPinned((prev) => {
      const next = !prev
      if (next) {
        // Pinning: ensure expanded
        setHoverExpanded(false)
      }
      return next
    })
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <aside
      ref={sidebarRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`
        ${expanded ? EXPANDED_WIDTH : COLLAPSED_WIDTH}
        h-full flex flex-col
        bg-gradient-to-b from-[#1c0957] via-[#180847] to-[#120535]
        border-r border-white/10 shadow-2xl
        transition-[width] duration-300 ease-out
        overflow-hidden select-none
        relative z-40
      `}
    >
      {/* ── Top: Logo ──────────────────────────────────────────────────── */}
      <div className="px-3 pt-4 pb-3 shrink-0">
        {expanded ? (
          <div className="px-1 space-y-2">
            <img
              src="/pg-logo.png"
              alt="Procurement Garage"
              className="h-10 w-full object-contain object-left"
            />
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#0693e3]/10 border border-[#0693e3]/20 text-[9px] font-semibold text-[#38a8f5] tracking-wider uppercase">
              <svg className="w-2 h-2 shrink-0" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2l2.09 6.26H21l-5.47 3.97 2.09 6.27L12 14.54l-5.62 3.96 2.09-6.27L3 8.26h6.91L12 2z"/>
              </svg>
              Spend AI
            </span>
          </div>
        ) : (
          <div className="flex justify-center">
            <Tooltip label="Procurement Garage — Spend AI">
              <LogoMark />
            </Tooltip>
          </div>
        )}
      </div>

      {/* ── Project section ────────────────────────────────────────────── */}
      <div className="px-3 pb-3 shrink-0">
        {expanded ? (
          // Full ProjectSelect via render prop
          <div className="transition-opacity duration-200">
            {renderProjectSelect({ collapsed: false })}
          </div>
        ) : (
          // Collapsed: project avatar
          <div className="flex justify-center">
            <Tooltip label={activeProject?.display_name ?? 'Selecionar projeto'}>
              <button
                className="w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200 hover:scale-105"
                style={{
                  background: activeProject
                    ? 'linear-gradient(135deg, #0693e3, #9b51e0)'
                    : 'rgba(255,255,255,0.06)',
                }}
              >
                {activeProject ? (
                  <span className="text-xs font-bold text-white leading-none">
                    {getInitial(activeProject.display_name)}
                  </span>
                ) : (
                  <svg className="w-4 h-4 text-white/25" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                )}
              </button>
            </Tooltip>
          </div>
        )}
      </div>

      {/* ── Separator ──────────────────────────────────────────────────── */}
      <div className="mx-3 border-t border-white/10 shrink-0" />

      {/* ── Sessions ───────────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 overflow-y-auto py-3 custom-scrollbar">
        {expanded ? (
          // Expanded: header + compact session list
          <div className="px-2">
            <div className="flex items-center justify-between px-2 mb-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.15em] text-white/30">
                Sessões
              </span>
              {sessions.length > 0 && (
                <span className="text-[10px] tabular-nums text-white/20">
                  {sessions.length}
                </span>
              )}
            </div>

            {sessions.length === 0 ? (
              <div className="text-center py-8 px-3">
                <p className="text-xs text-white/30">Nenhuma sessão</p>
                <p className="text-[10px] text-white/20 mt-1">Faça upload para começar</p>
              </div>
            ) : (
              <div className="space-y-0.5">
                {sessions.map((session) => (
                  <ExpandedSessionRow
                    key={session.sessionId}
                    session={session}
                    isActive={session.sessionId === activeSessionId}
                    onClick={() => onSessionSelect(session.sessionId)}
                    onDelete={onDeleteSession ? () => onDeleteSession(session.sessionId) : undefined}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          // Collapsed: session dots
          <div className="flex flex-col items-center gap-1.5 px-1">
            {sessions.map((session) => (
              <CollapsedSessionDot
                key={session.sessionId}
                session={session}
                isActive={session.sessionId === activeSessionId}
                onClick={() => onSessionSelect(session.sessionId)}
              />
            ))}
            {sessions.length === 0 && (
              <div className="w-8 h-8 rounded-lg border border-dashed border-white/10 flex items-center justify-center">
                <span className="text-white/15 text-[10px]">--</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Bottom actions ─────────────────────────────────────────────── */}
      <div className="shrink-0 border-t border-white/10 bg-white/[0.02]">
        {/* KB button */}
        <div className={`${expanded ? 'px-3 pt-3 pb-1' : 'px-2 pt-3 pb-1'}`}>
          {expanded ? (
            <button
              onClick={onOpenKB}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg
                         text-white/50 hover:text-white/80 hover:bg-white/[0.06]
                         transition-all duration-200 group"
            >
              <div className="w-7 h-7 rounded-md bg-white/[0.06] group-hover:bg-white/10 flex items-center justify-center transition-colors shrink-0">
                <KBIcon />
              </div>
              <span className="text-xs font-medium">Base de Conhecimento</span>
            </button>
          ) : (
            <div className="flex justify-center">
              <Tooltip label="Base de Conhecimento">
                <button
                  onClick={onOpenKB}
                  className="w-8 h-8 rounded-lg flex items-center justify-center
                             text-white/40 hover:text-white/70 hover:bg-white/[0.08]
                             transition-all duration-200"
                >
                  <KBIcon />
                </button>
              </Tooltip>
            </div>
          )}
        </div>

        {/* New session button */}
        <div className={`${expanded ? 'px-3 pb-2' : 'px-2 pb-2'}`}>
          {expanded ? (
            <button
              onClick={onNewSession}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg
                         bg-[#0693e3]/10 hover:bg-[#0693e3]/20
                         text-[#38a8f5] hover:text-[#0693e3]
                         transition-all duration-200 group border border-[#0693e3]/10 hover:border-[#0693e3]/25"
            >
              <div className="w-7 h-7 rounded-md bg-[#0693e3]/10 group-hover:bg-[#0693e3]/20 flex items-center justify-center transition-colors shrink-0">
                <PlusIcon className="w-3.5 h-3.5" />
              </div>
              <span className="text-xs font-semibold">Nova Sessão</span>
            </button>
          ) : (
            <div className="flex justify-center">
              <Tooltip label="Nova Sessão">
                <button
                  onClick={onNewSession}
                  className="w-8 h-8 rounded-lg flex items-center justify-center
                             bg-[#0693e3]/10 hover:bg-[#0693e3]/20
                             text-[#38a8f5] hover:text-[#0693e3]
                             transition-all duration-200 border border-[#0693e3]/10 hover:border-[#0693e3]/25"
                >
                  <PlusIcon className="w-4 h-4" />
                </button>
              </Tooltip>
            </div>
          )}
        </div>

        {/* Clear history (expanded only) */}
        {expanded && onClearHistory && (
          <div className="px-3 pb-2">
            <button
              onClick={onClearHistory}
              className="w-full flex items-center justify-center gap-2 py-2
                         text-[10px] text-white/20 hover:text-white/40
                         hover:bg-white/[0.03] rounded-lg transition-all duration-200"
            >
              <TrashIcon />
              <span>Limpar Histórico</span>
            </button>
          </div>
        )}

        {/* Pin / Expand toggle */}
        <div className={`${expanded ? 'px-3' : 'px-2'} pb-3`}>
          {expanded ? (
            <button
              onClick={togglePin}
              className={`
                w-full flex items-center gap-2.5 px-3 py-2 rounded-lg
                transition-all duration-200
                ${pinned
                  ? 'text-[#0693e3] bg-[#0693e3]/10 hover:bg-[#0693e3]/15'
                  : 'text-white/30 hover:text-white/50 hover:bg-white/[0.04]'
                }
              `}
              title={pinned ? 'Desafixar sidebar' : 'Fixar sidebar aberto'}
            >
              <PinIcon pinned={pinned} />
              <span className="text-[11px] font-medium">
                {pinned ? 'Sidebar fixo' : 'Fixar sidebar'}
              </span>
            </button>
          ) : (
            <div className="flex justify-center">
              <Tooltip label={pinned ? 'Desafixar sidebar' : 'Expandir sidebar'}>
                <button
                  onClick={togglePin}
                  className={`
                    w-8 h-8 rounded-lg flex items-center justify-center
                    transition-all duration-200
                    ${pinned
                      ? 'text-[#0693e3] bg-[#0693e3]/10'
                      : 'text-white/30 hover:text-white/50 hover:bg-white/[0.06]'
                    }
                  `}
                >
                  {pinned ? (
                    <PinIcon pinned={true} />
                  ) : (
                    <ChevronDoubleRight className="w-3.5 h-3.5" />
                  )}
                </button>
              </Tooltip>
            </div>
          )}
        </div>
      </div>
    </aside>
  )
}
