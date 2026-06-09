/**
 * @fileoverview Hook for managing taxonomy classification sessions.
 *
 * Submits jobs via the v3 async API (submitClassificationJobRaw),
 * then polls GetTaxonomyJobStatus in a blocking loop until CLASSIFIED.
 * The UI is locked via isProcessing=true and shows real-time progress.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { apiClient } from '@/lib/api'
import { saveSession, getAllSessions, clearAllSessions, deleteSession } from '@/lib/database'
import type { TaxonomySession, ReviewSummary, ReviewState } from '@/lib/types'

export type { TaxonomySession }

// ─────────────────────────────────────────────────────────────────────────────
// Return type
// ─────────────────────────────────────────────────────────────────────────────

interface UseTaxonomySessionReturn {
    sessions: TaxonomySession[]
    activeSessionId: string | null
    activeSession: TaxonomySession | undefined
    isProcessing: boolean
    isCancelling: boolean
    progress: { message: string; pct: number } | null
    clientContext: string
    activeProjectId: string | null

    setClientContext: (context: string) => void
    setActiveSessionId: (id: string | null) => void
    setActiveProjectId: (id: string | null) => void
    handleNewUpload: () => void
    handleFileSelect: (file: File, fileContent: string, hierarchyContent?: string, useWebSearch?: boolean) => Promise<void>
    handleClearHistory: () => void
    handleDeleteSession: (sessionId: string) => void
    setReviewCompleted: (summary: ReviewSummary, approvedFileB64: string, approvedFilename: string) => Promise<void>
    cancelJob: () => Promise<void>
}

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────

export function useTaxonomySession(): UseTaxonomySessionReturn {
    const [sessions, setSessions] = useState<TaxonomySession[]>([])
    const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
    const [isProcessing, setIsProcessing] = useState(false)
    const [isCancelling, setIsCancelling] = useState(false)
    const [progress, setProgress] = useState<{ message: string; pct: number } | null>(null)
    const [clientContext, setClientContext] = useState('')
    const [activeProjectId, setActiveProjectId] = useState<string | null>(null)

    const cancelledRef = useRef(false)
    const currentJobIdRef = useRef<string | null>(null)
    const sessionsRef = useRef(sessions)
    sessionsRef.current = sessions

    const activeSession = sessions.find(s => s.sessionId === activeSessionId)

    // ── Session loading ────────────────────────────────────────────────────────

    useEffect(() => {
        const loadSessions = async () => {
            const stored = await getAllSessions()
            if (stored.length === 0) return
            setSessions(stored)
            setActiveSessionId(stored[0].sessionId)
        }
        loadSessions()
    }, [])

    // ── Actions ────────────────────────────────────────────────────────────────

    const handleNewUpload = useCallback(() => {
        setActiveSessionId(null)
    }, [])

    /**
     * Submits the file to the v3 job API, then polls for progress until
     * the job reaches CLASSIFIED status. UI is locked throughout.
     */
    const handleFileSelect = async (
        file: File,
        fileContent: string,
        hierarchyContent?: string,
        useWebSearch?: boolean
    ) => {
        setIsProcessing(true)
        setIsCancelling(false)
        cancelledRef.current = false
        setProgress({ message: 'Enviando arquivo...', pct: 0 })

        try {
            // Submit job — get jobId immediately
            const { jobId } = await apiClient.submitClassificationJobRaw({
                fileContent,
                originalFilename: file.name,
                projectId: activeProjectId || undefined,
                customHierarchy: hierarchyContent,
                useWebSearch,
            })

            currentJobIdRef.current = jobId
            console.log(`[Session] Job submitted: ${jobId}`)
            setProgress({ message: 'Upload concluído. Aguardando início...', pct: 2 })

            // Poll until CLASSIFIED (or ERROR / CANCELLED / timeout)
            const MAX_POLLS = 600  // 50 minutes at 5 s/poll
            let attempts = 0

            while (attempts < MAX_POLLS) {
                await new Promise(resolve => setTimeout(resolve, 5000))

                // Check if cancelled locally (user clicked cancel)
                if (cancelledRef.current) {
                    console.log(`[Session] Job ${jobId} cancelled by user`)
                    return
                }

                try {
                    const status = await apiClient.getJobStatus(jobId)
                    const newPct = (status as any).progress_pct ?? 0
                    const msg = (status as any).message || 'Classificando chunks...'

                    console.log(`[Session] Job ${jobId}: ${status.status} (${newPct}%)`)

                    // Job cancelled (possibly from another tab/session)
                    if (status.status === 'CANCELLED') {
                        console.log(`[Session] Job ${jobId} was cancelled`)
                        return
                    }

                    // Never go backwards — backend reports 0% for PENDING jobs
                    setProgress(prev => ({ message: msg, pct: Math.max(prev?.pct ?? 0, newPct) }))

                    if (status.status === 'CLASSIFIED' || status.status === 'COMPLETED') {
                        // Fetch all classified items
                        setProgress({ message: 'Carregando resultados...', pct: 98 })
                        const results = await apiClient.getJobResults(jobId)

                        const newSession: TaxonomySession = {
                            sessionId: jobId,
                            jobId,
                            filename: file.name,
                            timestamp: Date.now(),
                            projectId: activeProjectId || undefined,
                            jobStatus: 'CLASSIFIED',
                            summary: results.summary,
                            analytics: results.analytics,
                            items: results.items,
                            extraColumns: results.extra_columns || [],
                            downloadFilename: status.download_filename,
                            fileContentBase64: status.file_content_base64,
                            reviewState: 'pending',
                            reviewedCount: 0,
                            totalItems: results.total,
                        }

                        setSessions(prev => [newSession, ...prev])
                        setActiveSessionId(jobId)
                        await saveSession(newSession)

                        setProgress({ message: 'Concluído!', pct: 100 })
                        return
                    }

                    if (status.status === 'ERROR') {
                        throw new Error((status as any).error || (status as any).message || 'Erro no processamento do arquivo.')
                    }

                } catch (pollErr: any) {
                    if (pollErr?.response?.status === 404) {
                        throw new Error('Job não encontrado. Tente novamente.')
                    }
                    console.warn('[Session] Polling error (retrying):', pollErr)
                }

                attempts++
            }

            throw new Error('Tempo limite atingido. O arquivo pode ser muito grande.')

        } catch (error: any) {
            console.error('Erro no processamento:', error)
            if (!cancelledRef.current) {
                alert(`Erro ao processar arquivo: ${error.message || 'Erro desconhecido'}`)
            }
        } finally {
            setIsProcessing(false)
            setIsCancelling(false)
            setProgress(null)
            currentJobIdRef.current = null
        }
    }

    const setReviewCompleted = useCallback(async (
        summary: ReviewSummary,
        approvedFileB64: string,
        approvedFilename: string
    ) => {
        if (!activeSessionId) return

        const currentSession = sessionsRef.current.find(s => s.sessionId === activeSessionId);
        if (!currentSession) return;

        const updatedSession: TaxonomySession = {
            ...currentSession,
            reviewState: 'completed' as ReviewState,
            reviewSummary: summary,
            approvedFileContentBase64: approvedFileB64,
            approvedDownloadFilename: approvedFilename,
        };

        setSessions(prev => prev.map(s =>
            s.sessionId !== activeSessionId ? s : updatedSession
        ));

        await saveSession(updatedSession);
    }, [activeSessionId])

    const cancelJob = useCallback(async () => {
        const jobId = currentJobIdRef.current
        if (!jobId) return

        setIsCancelling(true)
        try {
            await apiClient.cancelJob(jobId)
            cancelledRef.current = true
        } catch (e) {
            console.error('[Session] Cancel error:', e)
            // Even if the API call fails, abort the polling loop
            cancelledRef.current = true
        }
    }, [])

    const handleClearHistory = useCallback(async () => {
        await clearAllSessions()

        const keysToRemove: string[] = []
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i)
            if (key?.startsWith('pg_spend_chat_')) keysToRemove.push(key)
        }
        keysToRemove.forEach(key => localStorage.removeItem(key))

        setSessions([])
        setActiveSessionId(null)
    }, [])

    const handleDeleteSession = useCallback(async (sessionId: string) => {
        await deleteSession(sessionId)
        localStorage.removeItem(`pg_spend_chat_${sessionId}`)
        setSessions(prev => prev.filter(s => s.sessionId !== sessionId))
        if (activeSessionId === sessionId) setActiveSessionId(null)
    }, [activeSessionId])

    return {
        sessions,
        activeSessionId,
        activeSession,
        isProcessing,
        isCancelling,
        progress,
        clientContext,
        activeProjectId,
        setClientContext,
        setActiveSessionId,
        setActiveProjectId,
        handleNewUpload,
        handleFileSelect,
        handleClearHistory,
        handleDeleteSession,
        setReviewCompleted,
        cancelJob,
    }
}

// Exported helper (synchronous, using atob for max compatibility)
export const base64ToBlobSync = (base64: string, contentType: string): Blob => {
    try {
        const cleanBase64 = base64.replace(/\s/g, '').split(',').pop() || ''
        if (!cleanBase64) return new Blob([], { type: contentType })
        const byteCharacters = atob(cleanBase64)
        const byteArrays: Uint8Array[] = []
        for (let offset = 0; offset < byteCharacters.length; offset += 512) {
            const slice = byteCharacters.slice(offset, offset + 512)
            const byteNumbers = new Uint8Array(slice.length)
            for (let i = 0; i < slice.length; i++) byteNumbers[i] = slice.charCodeAt(i)
            byteArrays.push(byteNumbers)
        }
        return new Blob(byteArrays as unknown as BlobPart[], { type: contentType })
    } catch (e) {
        console.error('base64ToBlobSync failed:', e)
        return new Blob([], { type: contentType })
    }
}
