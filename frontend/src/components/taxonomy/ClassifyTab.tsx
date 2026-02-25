import React, { useState, useCallback } from 'react'
import * as XLSX from 'xlsx'
import type { FileValidation, ValidationCheck } from '@/components/ui/ValidationCard'

interface ClassifyTabProps {
  onFileSelect: (file: File, fileContent: string, hierarchyContent?: string) => void
  isProcessing: boolean
  projectId?: string | null
  projectHierarchy?: any[] | null
}

export default function ClassifyTab({
  onFileSelect,
  isProcessing,
  projectId,
  projectHierarchy,
}: ClassifyTabProps) {
  const [baseValidation, setBaseValidation] = useState<FileValidation | null>(null)
  const [hierarchyValidation, setHierarchyValidation] = useState<FileValidation | null>(null)
  const [hierarchyOpen, setHierarchyOpen] = useState(false)

  const hasProjectHierarchy = projectHierarchy && projectHierarchy.length > 0
  const n4Count = hasProjectHierarchy
    ? new Set(projectHierarchy!.map((e: any) => e.N4).filter(Boolean)).size
    : 0

  // Row count from the validated base file
  const rowCount = baseValidation?.checks.find(c => c.label === 'Quantidade de Itens')?.message ?? null

  const validateBaseFile = useCallback((file: File, content: string) => {
    try {
      const bytes = Uint8Array.from(atob(content), c => c.charCodeAt(0))
      const workbook = XLSX.read(bytes, { type: 'array' })
      const sheet = workbook.Sheets[workbook.SheetNames[0]]
      const data: any[] = XLSX.utils.sheet_to_json(sheet)
      const columns = data.length > 0 ? Object.keys(data[0]) : []
      const colLower = columns.map(c => c.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''))

      const hasDesc = colLower.some(c =>
        c.includes('descricao') || c.includes('description') || c.includes('item_description')
      )
      const hasSku = colLower.some(c =>
        c.includes('sku') || c.includes('codigo') || c.includes('code')
      )
      const checks: ValidationCheck[] = [
        { label: 'Coluna "Descrição" encontrada', status: hasDesc ? 'ok' : 'error', message: hasDesc ? 'Encontrada' : 'Não encontrada' },
        { label: 'Quantidade de Itens', status: data.length > 0 ? 'ok' : 'error', message: `${data.length.toLocaleString('pt-BR')} linhas válidas` },
        { label: 'Coluna SKU', status: hasSku ? 'ok' : 'warning', message: hasSku ? 'Encontrada' : 'Não encontrada (opcional)' },
      ]
      setBaseValidation({ file, content, isValid: hasDesc && data.length > 0, checks, previewData: data.slice(0, 3) })
    } catch {
      setBaseValidation({
        file, content, isValid: false,
        checks: [{ label: 'Erro', status: 'error', message: 'Não foi possível ler o arquivo' }],
        previewData: [],
      })
    }
  }, [])

  const validateHierarchyFile = useCallback((file: File, content: string) => {
    try {
      const bytes = Uint8Array.from(atob(content), c => c.charCodeAt(0))
      const workbook = XLSX.read(bytes, { type: 'array' })
      const sheet = workbook.Sheets[workbook.SheetNames[0]]
      const data: any[] = XLSX.utils.sheet_to_json(sheet)
      const columns = data.length > 0 ? Object.keys(data[0]) : []
      const colUpper = columns.map(c => c.toUpperCase().trim())
      const missing = ['N1', 'N2', 'N3', 'N4'].filter(c => !colUpper.includes(c))
      const n4Col = columns.find(c => c.toUpperCase().trim() === 'N4')
      const uniqueN4s = n4Col ? new Set(data.map(r => r[n4Col]).filter(Boolean)).size : 0
      const checks: ValidationCheck[] = [
        { label: 'Colunas N1-N4', status: missing.length === 0 ? 'ok' : 'error', message: missing.length === 0 ? 'Todas presentes' : `Faltando: ${missing.join(', ')}` },
        { label: 'Categorias N4', status: uniqueN4s > 0 ? 'ok' : 'warning', message: `${uniqueN4s} categorias únicas` },
      ]
      setHierarchyValidation({ file, content, isValid: missing.length === 0, checks, previewData: data.slice(0, 3) })
    } catch {
      setHierarchyValidation({
        file, content, isValid: false,
        checks: [{ label: 'Erro', status: 'error', message: 'Não foi possível ler o arquivo' }],
        previewData: [],
      })
    }
  }, [])

  const handleSubmit = () => {
    if (baseValidation?.isValid) {
      onFileSelect(
        baseValidation.file,
        baseValidation.content,
        hierarchyValidation?.isValid ? hierarchyValidation.content : undefined
      )
    }
  }

  const canSubmit = baseValidation?.isValid && !isProcessing
  const hierarchyReady = hierarchyValidation === null || hierarchyValidation.isValid

  // Estimate processing time based on row count
  const estimatedMinutes = (() => {
    if (!baseValidation) return null
    const match = baseValidation.checks.find(c => c.label === 'Quantidade de Itens')
    if (!match) return null
    const count = parseInt(match.message.replace(/\D/g, ''), 10)
    if (isNaN(count) || count === 0) return null
    // ~500 items per minute rough estimate
    const mins = Math.max(1, Math.ceil(count / 500))
    return mins
  })()

  return (
    <div className="space-y-5">

      {/* ── Upload zone / File validation card ── */}
      {baseValidation ? (
        <FileValidationCard
          validation={baseValidation}
          onClear={() => setBaseValidation(null)}
          disabled={isProcessing}
        />
      ) : (
        <UploadZone
          onFileSelect={(file, content) => validateBaseFile(file, content)}
          disabled={isProcessing}
        />
      )}

      {/* ── Collapsible hierarchy section (always visible) ── */}
      <div>
        <button
          type="button"
          onClick={() => setHierarchyOpen(prev => !prev)}
          className="flex items-center gap-1.5 text-sm text-primary-500 hover:text-primary-700 transition-colors"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform duration-200 ${hierarchyOpen ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          {hasProjectHierarchy ? 'Substituir hierarquia nesta execução (opcional)' : 'Hierarquia customizada (opcional)'}
        </button>

        {hierarchyOpen && (
          <div className="mt-3">
            {hierarchyValidation ? (
              <FileValidationCard
                validation={hierarchyValidation}
                onClear={() => setHierarchyValidation(null)}
                disabled={isProcessing}
                compact
              />
            ) : (
              <UploadZone
                onFileSelect={(file, content) => validateHierarchyFile(file, content)}
                disabled={isProcessing}
                compact
                label="Arraste o arquivo de hierarquia"
                hint="N1 . N2 . N3 . N4"
              />
            )}
          </div>
        )}
      </div>

      {/* ── CTA Button ── */}
      <div className="flex justify-center pt-1">
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || !hierarchyReady}
          className={[
            'inline-flex flex-col items-center justify-center px-10 py-3 rounded-xl text-white transition-all duration-200',
            canSubmit && hierarchyReady
              ? 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0] shadow-md shadow-[#0693e3]/20 hover:shadow-lg hover:shadow-[#0693e3]/30 active:scale-[0.98]'
              : 'bg-gray-300 opacity-50 cursor-not-allowed',
          ].join(' ')}
        >
          {isProcessing ? (
            <div className="flex items-center gap-2.5">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm font-semibold">Processando...</span>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span className="text-sm font-semibold">Classificar com IA</span>
              </div>
              <span className="text-[11px] text-white/60 mt-0.5">
                Grok AI{estimatedMinutes ? ` · ~${estimatedMinutes} min estimado` : ''}
              </span>
            </>
          )}
        </button>
      </div>

      {/* ── Context status line ── */}
      {projectId && (
        <div className="flex items-center justify-center gap-1.5 text-xs text-primary-400">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" strokeWidth={1.5} />
            <path strokeLinecap="round" strokeWidth={1.5} d="M12 6v6l4 2" />
          </svg>
          {hierarchyValidation?.isValid ? (
            <span>Hierarquia desta execução (sobrescreve projeto)</span>
          ) : hasProjectHierarchy ? (
            <span>Hierarquia do projeto: {n4Count} N4s</span>
          ) : (
            <span>Taxonomia padrão UNSPSC</span>
          )}
        </div>
      )}

    </div>
  )
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// UploadZone — drag-and-drop area with clean dashed border
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function UploadZone({
  onFileSelect,
  disabled,
  compact = false,
  label,
  hint,
}: {
  onFileSelect: (file: File, content: string) => void
  disabled: boolean
  compact?: boolean
  label?: string
  hint?: string
}) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = React.useRef<HTMLInputElement>(null)

  const handleFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = e => {
      const b64 = (e.target?.result as string).split(',')[1]
      onFileSelect(file, b64)
    }
    reader.readAsDataURL(file)
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); if (!disabled) setIsDragging(true) }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={e => {
        e.preventDefault()
        setIsDragging(false)
        if (!disabled && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0])
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={[
        'relative rounded-2xl border-2 border-dashed transition-all duration-300 cursor-pointer',
        compact ? 'px-4 py-5' : 'px-6 py-10',
        isDragging
          ? 'border-accent-400 bg-accent-50 shadow-[0_0_0_4px_rgba(56,190,201,0.1)]'
          : 'border-gray-200 bg-white hover:border-accent-300 hover:bg-accent-50/30',
        disabled && 'opacity-50 cursor-not-allowed',
      ].join(' ')}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls,.csv"
        className="hidden"
        disabled={disabled}
        onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
      />

      <div className={`flex flex-col items-center gap-3 ${compact ? '' : 'py-2'}`}>
        {/* Upload icon */}
        <div className={[
          'rounded-2xl flex items-center justify-center transition-all duration-300',
          compact ? 'w-10 h-10' : 'w-14 h-14',
          isDragging
            ? 'bg-accent-100 text-accent-500 scale-110'
            : 'bg-gray-50 text-accent-400',
        ].join(' ')}>
          <svg
            className={compact ? 'w-5 h-5' : 'w-7 h-7'}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>

        {/* Text */}
        <div className="text-center">
          <p className={`font-medium text-[#32373c] ${compact ? 'text-xs' : 'text-sm'}`}>
            {label || 'Arraste seu arquivo aqui'}
          </p>
          <p className={`text-[#829ab1] mt-1 ${compact ? 'text-[10px]' : 'text-xs'}`}>
            {hint || '.xlsx  .xls  .csv'}
          </p>
        </div>
      </div>
    </div>
  )
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// FileValidationCard — replaces the upload zone after file is selected
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function FileValidationCard({
  validation,
  onClear,
  disabled,
  compact = false,
}: {
  validation: FileValidation
  onClear: () => void
  disabled: boolean
  compact?: boolean
}) {
  const hasError = validation.checks.some(c => c.status === 'error')

  // Extract item count for the header subtitle
  const itemCountCheck = validation.checks.find(c => c.label === 'Quantidade de Itens')
  const itemCountText = itemCountCheck ? itemCountCheck.message : null

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* File header row */}
      <div className={`flex items-center gap-3 ${compact ? 'px-3 py-2.5' : 'px-4 py-3'}`}>
        {/* File icon */}
        <div className="w-8 h-8 rounded-lg bg-accent-50 flex items-center justify-center shrink-0">
          <svg className="w-4 h-4 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>

        {/* File name and item count */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-gray-800 truncate" title={validation.file.name}>
              {validation.file.name}
            </span>
            {itemCountText && (
              <span className="text-xs text-gray-400 shrink-0">
                {itemCountText}
              </span>
            )}
          </div>
        </div>

        {/* Remove button */}
        <button
          onClick={e => { e.stopPropagation(); onClear() }}
          disabled={disabled}
          className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all shrink-0"
          title="Remover arquivo"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Validation checks */}
      <div className={`border-t border-gray-100 ${compact ? 'px-3 py-2' : 'px-4 py-3'} space-y-1.5`}>
        {validation.checks.map((check, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            {check.status === 'ok' ? (
              <svg className="w-3.5 h-3.5 text-mint-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            ) : check.status === 'warning' ? (
              <svg className="w-3.5 h-3.5 text-amber-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            ) : (
              <svg className="w-3.5 h-3.5 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            <span className="text-gray-600">{check.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
