/**
 * @fileoverview Hook for managing Copilot chat communication via Microsoft Direct Line.
 * 
 * This module provides the main hook for interacting with the AI Copilot, including:
 * - Stateless RAG (Retrieval-Augmented Generation) for each conversation turn
 * - Smart Context integration for enriching queries with relevant data
 * - Executive Summary generation from classification results
 * - Chat history persistence via localStorage
 * 
 * @module useCopilot
 */

import { useState, useCallback, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import { generateSmartContext, formatSmartContextMessage } from '@/lib/smart-context'
import type { Message } from '@/components/chat/ChatMessage'

// ============================================
// LocalStorage Utilities
// ============================================

/** Prefix for chat storage keys in localStorage */
const STORAGE_PREFIX = 'pg_spend_chat_'

/**
 * Retrieves chat messages from localStorage for a specific session.
 * @param sessionId - The unique identifier of the taxonomy session
 * @returns Array of Message objects, or empty array if not found
 */
const getChatFromStorage = (sessionId: string): Message[] => {
    if (typeof window === 'undefined') return []
    try {
        const stored = localStorage.getItem(`${STORAGE_PREFIX}${sessionId}`)
        if (!stored) return []
        const parsed = JSON.parse(stored)
        // Convert timestamp strings back to Date objects
        return parsed.map((msg: any) => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
        }))
    } catch {
        return []
    }
}

/**
 * Saves chat messages to localStorage for a specific session.
 * @param sessionId - The unique identifier of the taxonomy session
 * @param messages - Array of Message objects to persist
 */
const saveChatToStorage = (sessionId: string, messages: Message[]) => {
    if (typeof window === 'undefined') return
    try {
        localStorage.setItem(`${STORAGE_PREFIX}${sessionId}`, JSON.stringify(messages))
    } catch (e) {
        console.warn('Failed to save chat to localStorage', e)
    }
}

// ============================================
// Hook Interface
// ============================================

/** Props for the useCopilot hook */
interface UseCopilotProps {
    /** The currently active taxonomy session, or null if none selected */
    activeSession: any | null
    /**
     * When false, sendUserMessage returns early with a locked message
     * and isLocked is true. Defaults to false.
     */
    reviewCompleted?: boolean
}

/** Return type for the useCopilot hook */
interface UseCopilotReturn {
    /** Array of messages displayed in the chat UI */
    copilotMessages: Message[]
    /** Full chat history (may differ from displayed during loading states) */
    chatHistory: Message[]
    /** True when the Copilot is generating the initial Executive Summary */
    isCopilotLoading: boolean
    /** True when a user message is being sent and awaiting response */
    isSending: boolean
    /** Current value of the user input field */
    userMessage: string
    /** Updates the user input field value */
    setUserMessage: (msg: string) => void
    /** Sends a user message to the Copilot with Smart Context enrichment */
    sendUserMessage: (overrideMessage?: string) => Promise<void>
    /** Sends a message without updating UI (for batch operations) */
    sendSilentMessage: (msg: string) => Promise<string | null>
    /** Manually injects a message into the chat history */
    injectMessage: (role: 'user' | 'bot', text: string) => void
    /** Generates an Executive Summary from classification results */
    generateExecutiveSummary: () => Promise<void>
    /** Resets the chat state (loading flags and input) */
    resetChat: () => void
    /** True when the Copilot is locked because reviewCompleted is false */
    isLocked: boolean
}

// ============================================
// Main Hook
// ============================================

/**
 * Custom hook for managing Copilot chat communication.
 * 
 * Implements a stateless RAG architecture where each user message creates
 * a new Direct Line conversation to ensure context isolation with Smart Context.
 * 
 * @param props - Configuration including the active taxonomy session
 * @returns Object containing chat state and action methods
 * 
 * @example
 * ```tsx
 * const {
 *   copilotMessages,
 *   sendUserMessage,
 *   generateExecutiveSummary
 * } = useCopilot({ activeSession })
 * ```
 */
export function useCopilot({ activeSession, reviewCompleted = false }: UseCopilotProps): UseCopilotReturn {
    const sessionId = activeSession?.sessionId || null
    const isLocked = !reviewCompleted

    // State - initialized from localStorage
    const [copilotMessages, setCopilotMessages] = useState<Message[]>([])
    const [chatHistory, setChatHistory] = useState<Message[]>([])
    const [isCopilotLoading, setIsCopilotLoading] = useState(false)
    const [isSending, setIsSending] = useState(false)
    const [userMessage, setUserMessage] = useState('')

    // Load chat from localStorage when session changes
    useEffect(() => {
        if (sessionId) {
            const stored = getChatFromStorage(sessionId)
            setCopilotMessages(stored)
            setChatHistory(stored)
        } else {
            setCopilotMessages([])
            setChatHistory([])
        }
    }, [sessionId])

    // Helper: Save messages and update state
    const updateMessages = useCallback((newMessages: Message[]) => {
        setCopilotMessages(newMessages)
        setChatHistory(newMessages)
        if (sessionId) {
            saveChatToStorage(sessionId, newMessages)
        }
    }, [sessionId])

    const resetChat = useCallback(() => {
        setIsCopilotLoading(false)
        setIsSending(false)
        setUserMessage('')
    }, [])

    // Execute a conversation turn (stateless RAG)
    const executeConversationTurn = async (userMsg: string, contextData: any): Promise<Message[]> => {
        try {
            const tokenData = await apiClient.getDirectLineToken()
            const tempConversationId = tokenData.conversationId
            const tempToken = tokenData.token

            const finalMessage = formatSmartContextMessage(userMsg, contextData)

            await apiClient.postActivity(tempConversationId, tempToken, {
                type: 'message',
                from: { id: 'user' },
                text: finalMessage,
                locale: 'pt-BR'
            })

            let attempts = 0
            const maxAttempts = 12

            const poll = async (): Promise<Message[]> => {
                if (attempts >= maxAttempts) return []
                attempts++

                try {
                    const activityData: any = await apiClient.getMessagesFromCopilot(tempConversationId, tempToken)

                    const botMsgs = activityData.activities?.filter((a: any) =>
                        (a.from?.id !== 'user' && a.from.name !== 'user') &&
                        a.type === 'message' &&
                        a.text
                    ).map((msg: any) => ({
                        from: 'bot' as const,
                        text: msg.text.replace(/(?:📊|✅)?\s*AI-generated content may be incorrect[.\s]*/gi, '').trim(),
                        timestamp: new Date(msg.timestamp)
                    })) || []

                    if (botMsgs.length > 0) return botMsgs

                    await new Promise(r => setTimeout(r, 5000))
                    return poll()
                } catch (e) {
                    console.error("Poll error", e)
                    return []
                }
            }

            return poll()
        } catch (error) {
            console.error("Turn error", error)
            return [{ from: 'bot', text: "Erro ao processar mensagem. Tente novamente.", timestamp: new Date() }]
        }
    }

    // Expose a silent message sender for batch operations (Headless Mode)
    const sendSilentMessage = async (message: string): Promise<string | null> => {
        try {
            const tokenData = await apiClient.getDirectLineToken()
            const tempConversationId = tokenData.conversationId
            const tempToken = tokenData.token

            // Send message with Portuguese instruction (no JSON context)
            const payloadText = `INSTRUCÃO: Analise os grupos de itens abaixo e sugira a Taxonomia (Categoria N4) e a Hierarquia (N1-N3) para cada um. Responda em Português do Brasil.\n\n---\nDADOS PARA ANÁLISE:\n${message}`

            await apiClient.postActivity(tempConversationId, tempToken, {
                type: 'message',
                from: { id: 'user' },
                text: payloadText,
                locale: 'pt-BR'
            })

            let attempts = 0
            const maxAttempts = 30 // 2.5 minutes timeout

            const poll = async (): Promise<string | null> => {
                if (attempts >= maxAttempts) return null
                attempts++

                try {
                    const activityData: any = await apiClient.getMessagesFromCopilot(tempConversationId, tempToken)

                    const botMsgs = activityData.activities?.filter((a: any) =>
                        (a.from?.id !== 'user' && a.from.name !== 'user') &&
                        a.type === 'message' &&
                        a.text
                    ).map((msg: any) =>
                        msg.text.replace(/(?:📊|✅)?\s*AI-generated content may be incorrect[.\s]*/gi, '').trim()
                    ) || []

                    if (botMsgs.length > 0) return botMsgs.join('\n\n')

                    await new Promise(r => setTimeout(r, 5000))
                    return poll()
                } catch (e) {
                    console.error("Poll error", e)
                    return null
                }
            }

            return poll()
        } catch (error) {
            console.error("Silent message error", error)
            return null
        }
    }

    // Execute a direct message without Smart Context wrapper (fallback for greetings/casual)
    const executeDirectMessage = async (userMsg: string): Promise<Message[]> => {
        try {
            const tokenData = await apiClient.getDirectLineToken()
            const tempConversationId = tokenData.conversationId
            const tempToken = tokenData.token

            // Send message with Portuguese instruction (no JSON context)
            // Reverting to Prefix strategy as validated by user (Step 472)
            const payloadText = `INSTRUCÃO: Analise os grupos de itens abaixo e sugira a Taxonomia (Categoria N4) e a Hierarquia (N1-N3) para cada um. Responda em Português do Brasil.
            
---
DADOS PARA ANÁLISE:
${userMsg}`

            await apiClient.postActivity(tempConversationId, tempToken, {
                type: 'message',
                from: { id: 'user' },
                text: payloadText,
                locale: 'pt-BR'
            })

            let attempts = 0
            const maxAttempts = 30 // Increased to 2.5 minutes for large payloads

            const poll = async (): Promise<Message[]> => {
                if (attempts >= maxAttempts) {
                    return [{ from: 'bot', text: "⚠️ O Copilot demorou muito para responder. Por favor, tente novamente ou reduza a quantidade de grupos.", timestamp: new Date() }]
                }
                attempts++

                try {
                    const activityData: any = await apiClient.getMessagesFromCopilot(tempConversationId, tempToken)

                    const botMsgs = activityData.activities?.filter((a: any) =>
                        (a.from?.id !== 'user' && a.from.name !== 'user') &&
                        a.type === 'message' &&
                        a.text
                    ).map((msg: any) => ({
                        from: 'bot' as const,
                        text: msg.text.replace(/(?:📊|✅)?\s*AI-generated content may be incorrect[.\s]*/gi, '').trim(),
                        timestamp: new Date(msg.timestamp)
                    })) || []

                    if (botMsgs.length > 0) return botMsgs

                    await new Promise(r => setTimeout(r, 5000))
                    return poll()
                } catch (e) {
                    console.error("Poll error", e)
                    return [{ from: 'bot', text: "Erro de conexão ao buscar resposta.", timestamp: new Date() }]
                }
            }

            return poll()
        } catch (error) {
            console.error("Direct message error", error)
            return [{ from: 'bot', text: "Erro ao processar mensagem. Tente novamente.", timestamp: new Date() }]
        }
    }

    const sendUserMessage = async (overrideMessage?: string | any) => {
        // Gate: Copilot is locked until the review is completed
        if (isLocked) {
            const lockedMsg: Message = {
                from: 'bot',
                text: 'Complete a revisão primeiro para usar o Copilot.',
                timestamp: new Date()
            }
            const updatedMessages = [...copilotMessages, lockedMsg]
            updateMessages(updatedMessages)
            return
        }

        // Robust check: overrideMessage might be a MouseEvent if called from onClick={sendUserMessage}
        let msgToSend: string = '';
        if (typeof overrideMessage === 'string') {
            msgToSend = overrideMessage;
        } else if (typeof userMessage === 'string') {
            msgToSend = userMessage;
        }

        if (!msgToSend || !msgToSend.trim() || !sessionId) return;

        // Reset input IF we used the state message
        if (typeof overrideMessage !== 'string') setUserMessage('')

        setIsSending(true)

        // Add user message immediately
        const userMsgObj: Message = { from: 'user', text: msgToSend, timestamp: new Date() }
        const updatedWithUser = [...copilotMessages, userMsgObj]
        updateMessages(updatedWithUser)

        try {
            const smartContext = generateSmartContext(msgToSend, activeSession?.items || [])

            // If smart context found a match, use it; otherwise send message directly (fallback)
            if (smartContext) {
                // Has context - use structured prompt
                const responses = await executeConversationTurn(msgToSend, smartContext)
                updateMessages([...updatedWithUser, ...responses])
            } else {
                // No context (greeting, casual conversation) - send message directly
                const responses = await executeDirectMessage(msgToSend)
                updateMessages([...updatedWithUser, ...responses])
            }
        } catch (err) {
            console.error(err)
        } finally {
            setIsSending(false)
        }
    }

    const injectMessage = useCallback((role: 'user' | 'bot', text: string) => {
        const newMessage: Message = { from: role, text, timestamp: new Date() }
        setCopilotMessages(prev => {
            const updated = [...prev, newMessage]
            setChatHistory(updated)
            if (sessionId) saveChatToStorage(sessionId, updated)
            return updated
        })
    }, [sessionId])

    const generateExecutiveSummary = async () => {
        if (!activeSession || !sessionId) return

        const hasValidSummary = activeSession.summary?.total_linhas > 0
        const hasValidAnalytics = activeSession.analytics?.pareto && activeSession.analytics.pareto.length > 0

        console.log("[COPILOT] Checking summary trigger:", { hasValidSummary, hasValidAnalytics, analytics: activeSession.analytics });

        if (!hasValidSummary) {
            console.error("[COPILOT] Cannot generate summary: total_linhas is 0 or missing", activeSession.summary);
            injectMessage('bot', "⚠️ Os resultados foram processados, mas os dados de sumário estão zerados ou incompletos na resposta do servidor.")
            setIsCopilotLoading(false)
            return
        }

        if (!hasValidAnalytics) {
            console.error("[COPILOT] Cannot generate summary: analytics.pareto is missing or empty", activeSession.analytics);
            injectMessage('bot', "⚠️ Os resultados foram processados, mas os dados analíticos (Pareto) estão ausentes.")
            setIsCopilotLoading(false)
            return
        }

        setIsCopilotLoading(true)

        try {
            const tokenData = await apiClient.getDirectLineToken()
            const tempConversationId = tokenData.conversationId
            const tempToken = tokenData.token

            const totalItems = activeSession.summary?.total_linhas || 0
            const uniqueItems = activeSession.summary?.unico || 0
            const ambiguousItems = activeSession.summary?.ambiguo || 0
            const classifiedItems = uniqueItems + ambiguousItems
            const classificationRate = totalItems ? ((classifiedItems / totalItems) * 100).toFixed(1) : '0.0'
            const uniqueRate = totalItems ? ((uniqueItems / totalItems) * 100).toFixed(1) : '0.0'
            const ambiguousRate = totalItems ? ((ambiguousItems / totalItems) * 100).toFixed(1) : '0.0'

            const contextData = {
                metricas_gerais: {
                    total_itens: totalItems,
                    itens_classificados: classifiedItems,
                    taxa_classificacao: `${classificationRate}%`,
                    unicos_classificados: uniqueItems,
                    taxa_unicos: `${uniqueRate}%`,
                    ambiguos_classificados: ambiguousItems,
                    taxa_ambiguos: `${ambiguousRate}%`
                },
                top_N4_Categorias: activeSession.analytics?.pareto_N4?.slice(0, 20).map((item: any) => ({
                    categoria: item.N4,
                    volume: item.Contagem
                })),
            }

            const summaryPrompt = `ATUE COMO UM ANALISTA DE DADOS SÊNIOR.
Sua tarefa é analisar os dados JSON fornecidos abaixo e gerar um RESUMO EXECUTIVO.

INSTRUÇÕES OBRIGATÓRIAS:
1. Analise os dados fornecidos nesta mensagem. NÃO peça mais informações.
2. O foco principal deve ser as estatísticas de 'metricas_gerais' e os rankings de 'top_N4'.
3. Responda em Português do Brasil com formatação profissional (Markdown).

DADOS DA ANÁLISE(JSON):
\`\`\`json
${JSON.stringify(contextData, null, 2)}
\`\`\``

            await apiClient.sendMessageToCopilot(tempConversationId, tempToken, summaryPrompt)

            let attempts = 0
            const maxAttempts = 20 // Increased to 1 minute 40s
            let pollingComplete = false

            const poll = async () => {
                if (attempts >= maxAttempts) {
                    if (!pollingComplete) {
                        setIsCopilotLoading(false)
                        updateMessages([{
                            from: 'bot',
                            text: "O Resumo Automático não pôde ser gerado no momento. Você pode fazer perguntas específicas sobre os dados abaixo!",
                            timestamp: new Date()
                        }])
                    }
                    return
                }

                if (pollingComplete) return
                attempts++
                console.log(`[COPILOT] Polling summary attempt ${attempts}/${maxAttempts}...`);

                try {
                    const activityData: any = await apiClient.getMessagesFromCopilot(tempConversationId, tempToken)

                    const botMsgs = activityData.activities?.filter((a: any) =>
                        (a.from?.id !== 'user' && a.from.name !== 'user') &&
                        a.type === 'message' &&
                        a.text
                    ).map((msg: any) => ({
                        from: 'bot' as const,
                        text: msg.text.replace(/(?:📊|✅)?\s*AI-generated content may be incorrect[.\s]*/gi, '').trim(),
                        timestamp: new Date(msg.timestamp)
                    })) || []

                    if (botMsgs.length > 0 && !pollingComplete) {
                        pollingComplete = true // Mark complete BEFORE updating
                        // Take only the LAST message (most recent/complete response)
                        const latestMsg = botMsgs[botMsgs.length - 1]
                        updateMessages([latestMsg])
                        setIsCopilotLoading(false)
                    } else if (!pollingComplete) {
                        setTimeout(poll, 5000)
                    }
                } catch (e) {
                    console.error("Summary poll error", e)
                    setIsCopilotLoading(false)
                }
            }

            poll()
        } catch (error) {
            console.error("Error generating summary:", error)
            setIsCopilotLoading(false)
            updateMessages([{
                from: 'bot',
                text: "Desculpe, houve um erro técnico ao iniciar a conversa com o Copilot. Você ainda pode baixar o resultado acima!",
                timestamp: new Date()
            }])
        }
    }

    return {
        copilotMessages,
        chatHistory,
        isCopilotLoading,
        isSending,
        userMessage,
        setUserMessage,
        sendUserMessage,
        sendSilentMessage,
        injectMessage,
        generateExecutiveSummary,
        resetChat,
        isLocked,
    }
}
