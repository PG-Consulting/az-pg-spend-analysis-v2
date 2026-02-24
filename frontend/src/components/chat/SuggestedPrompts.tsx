import React from 'react'

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void
}

const DEFAULT_PROMPTS = [
  'Quais categorias têm mais itens?',
  'Distribuição por N1?',
  'Itens com baixa confiança?',
  'Resumo executivo da classificação',
] as const

export default function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="flex flex-wrap gap-2 justify-center py-4">
      {DEFAULT_PROMPTS.map((prompt) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSelect(prompt)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full border border-gray-200 bg-white text-sm text-gray-600 hover:border-[#0693e3] hover:text-[#0693e3] hover:bg-[#eff8ff] cursor-pointer transition-all duration-200 shadow-sm hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:ring-offset-1"
        >
          <SparkleIcon />
          <span>{prompt}</span>
        </button>
      ))}
    </div>
  )
}

function SparkleIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0 opacity-50"
    >
      <path d="M12 3l1.912 5.813a2 2 0 0 0 1.275 1.275L21 12l-5.813 1.912a2 2 0 0 0-1.275 1.275L12 21l-1.912-5.813a2 2 0 0 0-1.275-1.275L3 12l5.813-1.912a2 2 0 0 0 1.275-1.275L12 3z" />
    </svg>
  )
}
