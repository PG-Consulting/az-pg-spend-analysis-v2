import React from 'react'
import ChatMessage, { ChatMessageLoading } from '@/components/chat/ChatMessage'
import SuggestedPrompts from '@/components/chat/SuggestedPrompts'
import AiAvatar from '@/components/ui/AiAvatar'
import type { Message } from '@/components/chat/ChatMessage'

interface ReviewSummary {
  total: number
  approved: number
  edited: number
  kb_added: number
}

interface AnalyzeTabProps {
  reviewSummary: ReviewSummary | null
  approvedFileContentBase64?: string | null
  approvedDownloadFilename?: string | null
  copilotMessages: Message[]
  isCopilotLoading: boolean
  isSending: boolean
  userMessage: string
  onSetUserMessage: (msg: string) => void
  onSendMessage: (msg: string) => void
  onClose: () => void
  chatContainerRef: React.RefObject<HTMLDivElement>
}

export default function AnalyzeTab({
  reviewSummary,
  approvedFileContentBase64,
  approvedDownloadFilename,
  copilotMessages,
  isCopilotLoading,
  isSending,
  userMessage,
  onSetUserMessage,
  onSendMessage,
  onClose,
  chatContainerRef,
}: AnalyzeTabProps) {
  return (
    <div className="flex flex-col flex-1 min-h-0 max-w-4xl mx-auto w-full">
      {/* Compact summary header + download + close */}
      <div className="flex items-center justify-between bg-white rounded-xl border border-gray-100 px-5 py-3 shadow-sm mb-4 flex-shrink-0">
        <div className="flex items-center gap-6 text-sm">
          {reviewSummary ? (
            <>
              <span><strong className="text-[#32373c]">{reviewSummary.total}</strong> <span className="text-primary-400">total</span></span>
              <span><strong className="text-mint-500">{reviewSummary.approved}</strong> <span className="text-primary-400">aprovados</span></span>
              <span><strong className="text-accent-500">{reviewSummary.edited}</strong> <span className="text-primary-400">editados</span></span>
              <span><strong className="text-accent-500">{reviewSummary.kb_added}</strong> <span className="text-primary-400">na base</span></span>
            </>
          ) : (
            <span className="text-primary-400">Analise Conversacional</span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {approvedFileContentBase64 && approvedDownloadFilename && (
            <button
              onClick={() => {
                const base64 = approvedFileContentBase64!
                const bytes = atob(base64)
                const arr = new Uint8Array(bytes.length)
                for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
                const blob = new Blob([arr], {
                  type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                })
                const url = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = url
                a.download = approvedDownloadFilename!
                a.click()
                URL.revokeObjectURL(url)
              }}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-mint-500 text-white rounded-xl hover:bg-mint-600 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Baixar Excel
            </button>
          )}
          <button
            onClick={onClose}
            title="Fechar analise"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-primary-400 hover:text-[#32373c] hover:bg-gray-100 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Chat messages — fills remaining space */}
      <div
        ref={chatContainerRef}
        className="bg-white rounded-xl border border-gray-100 shadow-sm flex-1 min-h-0 overflow-y-auto p-6"
      >
        {copilotMessages.length === 0 && !isCopilotLoading && (
          <div className="flex flex-col items-center justify-center h-full py-12">
            <AiAvatar size="lg" pulse className="mb-4" />
            <p className="text-sm text-primary-400 mb-6">Faca perguntas sobre os dados classificados e revisados.</p>
            <SuggestedPrompts onSelect={(prompt) => { onSetUserMessage(prompt); onSendMessage(prompt); }} />
          </div>
        )}

        {copilotMessages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}

        {(isCopilotLoading || isSending) && <ChatMessageLoading />}
      </div>

      {/* Chat input — sticky bottom */}
      <form
        onSubmit={e => {
          e.preventDefault()
          if (userMessage.trim()) onSendMessage(userMessage.trim())
        }}
        className="flex gap-2 mt-4 flex-shrink-0"
      >
        <input
          type="text"
          value={userMessage}
          onChange={e => onSetUserMessage(e.target.value)}
          placeholder="Pergunte sobre os dados classificados..."
          className="flex-1 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-500/25 focus:border-accent-500 transition-all bg-white"
        />
        <button
          type="submit"
          disabled={isCopilotLoading || isSending || !userMessage.trim()}
          className="px-5 py-2.5 bg-accent-500 text-white rounded-xl text-sm font-medium hover:bg-accent-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Enviar
        </button>
      </form>
    </div>
  )
}
