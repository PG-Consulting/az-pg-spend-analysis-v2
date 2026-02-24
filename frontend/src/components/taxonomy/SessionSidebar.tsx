import React from 'react'
import { colors, tw } from '@/lib/design-tokens'
import type { ReviewState } from '@/lib/types'

export interface Session {
    sessionId: string
    filename: string
    sector: string
    timestamp: string | number
    summary?: any
    analytics?: any
    items?: any[]
    downloadUrl?: string
    downloadFilename?: string
    // Review state fields (optional for backward compatibility)
    reviewState?: ReviewState
    projectId?: string | null
    // Background job status (v3)
    jobStatus?: 'PENDING' | 'PROCESSING' | 'CLASSIFIED' | 'ERROR'
}

interface SessionSidebarProps {
    sessions: Session[]
    activeSessionId: string | null
    onSessionSelect: (sessionId: string) => void
    onNewUpload: () => void
    onClearHistory?: () => void
    onDeleteSession?: (sessionId: string) => void
    // Project filter props (optional)
    projectId?: string | null
    onFilterByProject?: (pid: string | null) => void
}

export default function SessionSidebar({
    sessions,
    activeSessionId,
    onSessionSelect,
    onNewUpload,
    onClearHistory,
    onDeleteSession,
    projectId,
    onFilterByProject,
}: SessionSidebarProps) {
    // Filter sessions by project if a projectId filter is active
    const displayedSessions = projectId
        ? sessions.filter(s => s.projectId === projectId)
        : sessions

    return (
        <div className="flex flex-col h-full min-h-0">
            {/* History section header */}
            <div className="px-5 py-2.5 flex items-center justify-between border-b border-white/10 bg-white/[0.03] shrink-0">
                <div className="flex items-center gap-2.5">
                    <div className="w-2 h-2 rounded-full bg-[#38a8f5] shadow-[0_0_8px_rgba(56,190,201,0.5)] animate-pulse shrink-0" />
                    <span className="text-xs font-bold tracking-widest text-white/60 uppercase">Histórico</span>
                </div>
                {/* Clear project filter button */}
                {projectId && onFilterByProject && (
                    <button
                        onClick={() => onFilterByProject(null)}
                        title="Mostrar todas as sessões"
                        className="shrink-0 p-1 rounded-md text-white/50 hover:text-white/80 hover:bg-white/10 transition-colors"
                    >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                )}
            </div>

            {/* Active project filter indicator */}
            {projectId && (
                <div className="px-3 py-1.5 bg-white/5 border-b border-white/10 flex items-center gap-1.5">
                    <svg className="w-3 h-3 text-[#38a8f5] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
                    </svg>
                    <span className="text-xs text-white/50 truncate">Filtrado por projeto</span>
                </div>
            )}

            {/* Sessions List */}
            <div className="flex-1 overflow-y-auto py-3 px-3 space-y-1.5 custom-scrollbar">
                {displayedSessions.length === 0 ? (
                    <div className="text-center py-10 px-4">
                        <div className="w-14 h-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mx-auto mb-4 text-white/20 shadow-inner">
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                            </svg>
                        </div>
                        <p className="text-sm text-white/50 font-medium">
                            {projectId ? 'Nenhuma sessão neste projeto' : 'Nenhuma sessão recente'}
                        </p>
                        <p className="text-xs text-white/30 mt-1">Faça upload para começar</p>
                    </div>
                ) : (
                    displayedSessions.map((session) => (
                        <SessionItem
                            key={session.sessionId}
                            session={session}
                            isActive={session.sessionId === activeSessionId}
                            onClick={() => onSessionSelect(session.sessionId)}
                            onDelete={onDeleteSession ? () => onDeleteSession(session.sessionId) : undefined}
                        />
                    ))
                )}
            </div>

            {/* Footer Actions */}
            <div className="p-4 border-t border-white/10 bg-white/[0.03] shrink-0">
                {onClearHistory && (
                    <button
                        onClick={onClearHistory}
                        className="w-full flex items-center justify-center gap-2 py-2.5 text-xs text-white/30 hover:text-white/60 hover:bg-white/5 rounded-lg transition-colors border border-transparent hover:border-white/5"
                    >
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-4 w-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={1.5}
                                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                        </svg>
                        Limpar Histórico
                    </button>
                )}
            </div>
        </div>
    )
}

function EmptyState() {
    return (
        <div className="text-center py-16 px-4">
            <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
                <svg className="w-8 h-8 text-white/30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            </div>
            <p className="text-sm font-medium text-white/60 mb-1">Nenhuma sessão recente</p>
            <p className="text-xs text-white/40">Faça o upload de um arquivo para iniciar.</p>
        </div>
    )
}

interface SessionItemProps {
    session: Session
    isActive: boolean
    onClick: () => void
    onDelete?: () => void
}

/** Returns a review status badge element, or null for 'pending' (no badge shown). */
function ReviewBadge({ reviewState }: { reviewState?: ReviewState }) {
    if (!reviewState || reviewState === 'pending') return null

    if (reviewState === 'in_progress') {
        return (
            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-yellow-400/20 text-yellow-300 border border-yellow-400/30">
                Em revisão
            </span>
        )
    }

    // completed
    return (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-mint-300/20 text-mint-300 border border-mint-300/30">
            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
            Revisado
        </span>
    )
}

function SessionItem({ session, isActive, onClick, onDelete }: SessionItemProps) {
    const handleDelete = (e: React.MouseEvent) => {
        e.stopPropagation() // Prevent selecting the session
        if (onDelete) onDelete()
    }

    return (
        <button
            onClick={onClick}
            className={`w-full text-left p-3 rounded-xl transition-all duration-200 group relative ${isActive
                ? 'bg-white/15 backdrop-blur-sm border-l-2 border-[#38a8f5]'
                : 'hover:bg-white/10 border-l-2 border-transparent'
                }`}
        >
            <div className="flex items-start gap-3">
                {/* File Icon */}
                <div className={`mt-0.5 p-2 rounded-lg transition-colors ${isActive
                    ? 'bg-[#38a8f5]/20 text-[#38a8f5]'
                    : 'bg-white/10 text-white/50 group-hover:text-white/70'
                    }`}>
                    <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium truncate transition-colors ${isActive ? 'text-white' : 'text-white/80 group-hover:text-white'
                        }`}>
                        {session.filename}
                    </p>
                    <p className={`text-xs mt-0.5 ${isActive ? 'text-[#38a8f5]' : 'text-white/50'
                        }`}>
                        {session.sector}
                    </p>
                    <p className="text-xs text-white/40 mt-1">
                        {new Date(session.timestamp).toLocaleString('pt-BR', {
                            day: '2-digit',
                            month: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        })}
                    </p>
                    {/* Background job progress */}
                    {(session.jobStatus === 'PENDING' || session.jobStatus === 'PROCESSING') && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                            <svg className="w-3 h-3 text-[#38a8f5] animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            <span className="text-[10px] text-[#38a8f5]">
                                {session.jobStatus === 'PROCESSING' ? 'Classificando...' : 'Na fila...'}
                            </span>
                        </div>
                    )}
                    {session.jobStatus === 'ERROR' && (
                        <div className="mt-1.5 flex items-center gap-1.5">
                            <svg className="w-3 h-3 text-red-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <span className="text-[10px] text-red-400">Erro no processamento</span>
                        </div>
                    )}
                    {/* Review status badge */}
                    {session.reviewState && session.reviewState !== 'pending' && !session.jobStatus && (
                        <div className="mt-1.5">
                            <ReviewBadge reviewState={session.reviewState} />
                        </div>
                    )}
                </div>

                {/* Active Indicator */}
                {isActive && (
                    <div className="w-2 h-2 rounded-full bg-[#38a8f5] animate-pulse mt-2"></div>
                )}
            </div>

            {/* Delete Button - Bottom Right */}
            {onDelete && (
                <div
                    onClick={handleDelete}
                    className="absolute bottom-2 right-2 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-white/40 hover:text-red-300 transition-all cursor-pointer"
                    title="Excluir sessão"
                >
                    <svg
                        className="w-3.5 h-3.5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                    >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </div>
            )}
        </button>
    )
}
