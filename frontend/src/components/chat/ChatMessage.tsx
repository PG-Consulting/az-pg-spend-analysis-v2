import React from 'react'
import AiAvatar from '../ui/AiAvatar'

// ─────────────────────────────────────────────────────────────────────────────
// Inline renderer: handles **bold** text
// ─────────────────────────────────────────────────────────────────────────────

function renderInline(text: string): React.ReactNode[] {
    const parts = text.split(/(\*\*[^*]+\*\*)/g)
    return parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
            return (
                <strong key={i} className="font-semibold text-[#32373c]">
                    {part.slice(2, -2)}
                </strong>
            )
        }
        return <React.Fragment key={i}>{part}</React.Fragment>
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// SimpleMarkdown: line-by-line parser for headers, lists, paragraphs, bold
// ─────────────────────────────────────────────────────────────────────────────

function SimpleMarkdown({ text }: { text: string }) {
    const lines = text.split('\n')
    const elements: React.ReactNode[] = []
    let listItems: string[] = []
    let isOrdered = false
    let key = 0

    const flushList = () => {
        if (listItems.length === 0) return
        if (isOrdered) {
            elements.push(
                <ol key={key++} className="list-decimal pl-5 mb-3 space-y-1">
                    {listItems.map((item, i) => (
                        <li key={i} className="text-[#486581] text-sm leading-relaxed">
                            {renderInline(item)}
                        </li>
                    ))}
                </ol>
            )
        } else {
            elements.push(
                <ul key={key++} className="list-disc pl-5 mb-3 space-y-1">
                    {listItems.map((item, i) => (
                        <li key={i} className="text-[#486581] text-sm leading-relaxed">
                            {renderInline(item)}
                        </li>
                    ))}
                </ul>
            )
        }
        listItems = []
    }

    for (const line of lines) {
        if (line.startsWith('#### ')) {
            flushList()
            elements.push(
                <h4 key={key++} className="font-semibold text-[#334e68] mt-3 mb-1 text-sm">
                    {renderInline(line.slice(5))}
                </h4>
            )
        } else if (line.startsWith('### ')) {
            flushList()
            elements.push(
                <h3 key={key++} className="font-semibold text-[#32373c] mt-4 mb-2" style={{ fontSize: '0.9rem' }}>
                    {renderInline(line.slice(4))}
                </h3>
            )
        } else if (line.startsWith('## ')) {
            flushList()
            elements.push(
                <h2 key={key++} className="font-bold text-[#32373c] text-base mt-5 mb-2">
                    {renderInline(line.slice(3))}
                </h2>
            )
        } else if (line.startsWith('# ')) {
            flushList()
            elements.push(
                <h1 key={key++} className="font-bold text-[#32373c] text-lg mt-5 mb-2">
                    {renderInline(line.slice(2))}
                </h1>
            )
        } else if (/^[-*] /.test(line)) {
            isOrdered = false
            listItems.push(line.slice(2))
        } else if (/^\d+\. /.test(line)) {
            isOrdered = true
            listItems.push(line.replace(/^\d+\. /, ''))
        } else if (line.trim() === '') {
            flushList()
        } else if (line.trim()) {
            flushList()
            elements.push(
                <p key={key++} className="text-[#486581] text-sm leading-relaxed mb-2 last:mb-0">
                    {renderInline(line)}
                </p>
            )
        }
    }

    flushList()
    return <>{elements}</>
}

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

export interface Message {
    from: 'user' | 'bot'
    text: string
    timestamp: Date
}

interface ChatMessageProps {
    message: Message
}

// ─────────────────────────────────────────────────────────────────────────────
// ChatMessage component
// Bot messages: AI identity with avatar, accent-50 background
// User messages: compact navy bubble, right-aligned
// ─────────────────────────────────────────────────────────────────────────────

export default function ChatMessage({ message }: ChatMessageProps) {
    const isUser = message.from === 'user'
    const timeStr =
        message.timestamp instanceof Date && !isNaN(message.timestamp.getTime())
            ? message.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
            : ''

    if (isUser) {
        return (
            <div className="flex justify-end mb-4 animate-fade-in">
                <div className="max-w-[70%]">
                    <div className="bg-[#1c0957] text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
                        <p className="text-sm leading-relaxed">{message.text}</p>
                    </div>
                    {timeStr && (
                        <p className="text-[10px] text-primary-400 mt-1 text-right pr-1">{timeStr}</p>
                    )}
                </div>
            </div>
        )
    }

    return (
        <div className="mb-5 animate-fade-in">
            {/* Header row: AI avatar + label + timestamp */}
            <div className="flex items-center gap-2.5 mb-3">
                <AiAvatar size="sm" />
                <span className="text-xs font-semibold text-[#32373c]">PG Agent</span>
                {timeStr && <span className="text-[10px] text-primary-300">{timeStr}</span>}
            </div>
            {/* Content: document style with accent background */}
            <div className="ml-8 bg-accent-50 rounded-xl rounded-tl-sm px-4 py-3 border border-accent-100">
                <SimpleMarkdown text={message.text} />
            </div>
        </div>
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// ChatMessageLoading — animated "thinking" state
// ─────────────────────────────────────────────────────────────────────────────

export function ChatMessageLoading() {
    return (
        <div className="mb-5 animate-fade-in">
            <div className="flex items-center gap-2.5 mb-3">
                <AiAvatar size="sm" pulse />
                <span className="text-xs font-semibold text-[#32373c]">PG Agent</span>
            </div>
            <div className="ml-8 bg-accent-50 rounded-xl rounded-tl-sm px-4 py-3 border border-accent-100">
                <div className="inline-flex items-center gap-2">
                    <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-accent-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-1.5 h-1.5 bg-accent-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-1.5 h-1.5 bg-accent-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                    </div>
                    <span className="text-xs text-primary-400">Analisando dados...</span>
                </div>
            </div>
        </div>
    )
}
