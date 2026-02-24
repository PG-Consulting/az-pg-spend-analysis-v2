import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Head from 'next/head'
import type { NextPage } from 'next'

// Hooks
import { useTaxonomySession } from '@/hooks/useTaxonomySession'
import { useCopilot } from '@/hooks/useCopilot'
import { useProjects } from '@/hooks/useProjects'

// Layout components
import CollapsibleSidebar from '@/components/layout/CollapsibleSidebar'
import ContextBar from '@/components/layout/ContextBar'
import type { StepId, StepStatus } from '@/components/layout/ContextBar'
import { SlideOver } from '@/components/ui/SlideOver'

// Components
import { ProjectSelect } from '@/components/project/ProjectSelect'
import { CreateProjectModal } from '@/components/project/CreateProjectModal'
import { EditProjectModal } from '@/components/project/EditProjectModal'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import ClassifyTab from '@/components/taxonomy/ClassifyTab'
import { ReviewTab } from '@/components/taxonomy/ReviewTab'
import { KnowledgeTab } from '@/components/taxonomy/KnowledgeTab'
import { SectorKnowledgeTab } from '@/components/taxonomy/SectorKnowledgeTab'
import { ProcessingOverlay } from '@/components/ProcessingOverlay'
import ChatMessage, { ChatMessageLoading } from '@/components/chat/ChatMessage'
import SuggestedPrompts from '@/components/chat/SuggestedPrompts'
import AiAvatar from '@/components/ui/AiAvatar'

// Types
import type { ClassifiedItem, HierarchyEntry, TaxonomySession } from '@/lib/types'

// ============================================================
// Types
// ============================================================

type TabId = 'classify' | 'review' | 'analyze'
type SessionPhase = 'no_session' | 'processing' | 'classified' | 'reviewing' | 'completed'

// ============================================================
// NoProjectGate — shown when no project is selected
// ============================================================

function NoProjectGate({
  hasProjects,
  onCreateProject,
}: {
  hasProjects: boolean
  onCreateProject: () => void
}) {
  const steps = [
    {
      n: '01',
      label: 'Projeto',
      desc: 'Hierarquia + contexto',
      icon: (
        <svg className="w-5 h-5 text-[#1c0957]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      ),
    },
    {
      n: '02',
      label: 'Classificar',
      desc: 'Upload + IA',
      icon: (
        <svg className="w-5 h-5 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      n: '03',
      label: 'Revisar',
      desc: 'Validação humana',
      icon: (
        <svg className="w-5 h-5 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      n: '04',
      label: 'Analisar',
      desc: 'Insights + Copilot',
      icon: (
        <svg className="w-5 h-5 text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      ),
    },
  ]

  return (
    <div className="flex-1 flex items-center justify-center bg-gradient-to-br from-slate-50 via-white to-sky-50/40 p-8">
      <div className="max-w-lg w-full">

        {/* Icon + heading */}
        <div className="text-center mb-10">
          <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-gradient-to-br from-[#1c0957] to-[#0693e3] flex items-center justify-center shadow-xl shadow-[#1c0957]/20">
            <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-[#32373c]">Spend Analysis com IA</h2>
          <p className="text-sm text-primary-500 mt-2 max-w-sm mx-auto leading-relaxed">
            {hasProjects
              ? 'Selecione um projeto no menu lateral para iniciar a classificação dos seus gastos.'
              : 'Crie seu primeiro projeto para configurar a hierarquia taxonômica e a base de conhecimento da IA.'}
          </p>
        </div>

        {/* Workflow steps */}
        <div className="relative flex items-start justify-between mb-10">
          {/* Background connector */}
          <div className="absolute top-6 left-[12.5%] right-[12.5%] h-px bg-gradient-to-r from-gray-100 via-gray-200 to-gray-100" />

          {steps.map((step) => (
            <div key={step.n} className="relative z-10 flex flex-col items-center w-1/4 px-2">
              <div className="w-12 h-12 rounded-2xl bg-white border border-gray-100 shadow-sm flex items-center justify-center mb-3">
                {step.icon}
              </div>
              <span className="text-[10px] font-mono font-bold text-accent-400 tracking-wider mb-0.5">{step.n}</span>
              <span className="text-xs font-semibold text-[#32373c] text-center">{step.label}</span>
              <span className="text-[10px] text-primary-400 text-center mt-0.5 leading-tight">{step.desc}</span>
            </div>
          ))}
        </div>

        {/* CTA */}
        <div className="text-center">
          {!hasProjects ? (
            <button
              onClick={onCreateProject}
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-[#1c0957] to-[#0693e3] text-white text-sm font-medium rounded-xl shadow-lg shadow-[#1c0957]/20 hover:shadow-xl hover:scale-[1.02] transition-all duration-200"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Criar primeiro projeto
            </button>
          ) : (
            <div className="inline-flex items-center gap-2.5 text-sm text-primary-500 bg-white border border-gray-100 rounded-xl px-5 py-3 shadow-sm">
              <svg className="w-4 h-4 text-accent-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 17l-5-5m0 0l5-5m-5 5h12" />
              </svg>
              Selecione um projeto no menu lateral
            </div>
          )}
        </div>

      </div>
    </div>
  )
}

// ============================================================
// Page
// ============================================================

const TaxonomyPage: NextPage = () => {

  // ---- Project state ----
  const [showCreateProject, setShowCreateProject] = useState(false)
  const [editingProject, setEditingProject] = useState<import('@/lib/types').Project | null>(null)
  const [deletingProject, setDeletingProject] = useState<import('@/lib/types').Project | null>(null)

  const {
    projects,
    sectors,
    loading: projectsLoading,
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    createSector,
  } = useProjects()

  // ---- Session state ----
  const {
    sessions,
    activeSessionId,
    activeSession,
    isProcessing,
    progress,
    activeProjectId,
    setActiveProjectId,
    setActiveSessionId,
    setReviewCompleted,
    handleNewUpload,
    handleFileSelect,
    handleClearHistory,
    handleDeleteSession,
  } = useTaxonomySession()

  const activeProject = useMemo(
    () => projects.find(p => p.project_id === activeProjectId) ?? null,
    [projects, activeProjectId]
  )

  // Keep activeProjectId in sync when switching sessions
  useEffect(() => {
    const session = activeSession as (TaxonomySession & { projectId?: string | null }) | undefined
    if (session?.projectId && session.projectId !== activeProjectId) {
      setActiveProjectId(session.projectId)
    }
  }, [activeSession, activeProjectId])

  // ---- Session phase (computed early — needed by useCopilot) ----
  const sessionPhase = useMemo<SessionPhase>(() => {
    if (!activeSession) return 'no_session'
    if (isProcessing) return 'processing'
    const session = activeSession as any
    if (session.reviewState === 'completed') return 'completed'
    if (session.reviewState === 'in_progress') return 'reviewing'
    if (session.items && session.items.length > 0) return 'classified'
    return 'no_session'
  }, [activeSession, isProcessing])

  // ---- Copilot ----
  const reviewCompleted = sessionPhase === 'completed'
  const {
    copilotMessages,
    isCopilotLoading,
    isSending,
    userMessage,
    setUserMessage,
    sendUserMessage,
    generateExecutiveSummary,
  } = useCopilot({ activeSession: activeSession ?? null, reviewCompleted })

  const chatContainerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [copilotMessages, isCopilotLoading, isSending])

  // ---- Active tab ----
  const [activeTab, setActiveTab] = useState<TabId>('classify')

  // ---- KB slide-over state ----
  const [kbOpen, setKbOpen] = useState(false)
  const [kbTab, setKbTab] = useState<'project' | 'sector'>('project')

  // ---- Step statuses for ContextBar ----
  const stepStatuses = useMemo<Record<StepId, StepStatus>>(() => ({
    classify: ['classified', 'reviewing', 'completed'].includes(sessionPhase) ? 'completed' : activeTab === 'classify' ? 'active' : 'available',
    review: sessionPhase === 'no_session' || sessionPhase === 'processing' ? 'locked' : activeTab === 'review' ? 'active' : sessionPhase === 'completed' ? 'completed' : 'available',
    analyze: sessionPhase !== 'completed' ? 'locked' : activeTab === 'analyze' ? 'active' : 'available',
  }), [sessionPhase, activeTab])

  // Auto-navigate to review when classification finishes
  useEffect(() => {
    if (sessionPhase === 'classified' && activeTab === 'classify') {
      setActiveTab('review')
    }
  }, [sessionPhase, activeTab])

  // Auto-navigate to analyze after review completes (finalize button flow)
  useEffect(() => {
    if (sessionPhase === 'completed' && activeTab === 'review') {
      setActiveTab('analyze')
    }
  }, [sessionPhase, activeTab])

  // Auto-navigate to analyze when selecting a completed session from history
  useEffect(() => {
    if (sessionPhase === 'completed') {
      setActiveTab('analyze')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSession?.sessionId])

  // Trigger executive summary when landing on the analyze tab for the first time
  useEffect(() => {
    if (
      activeTab === 'analyze' &&
      sessionPhase === 'completed' &&
      copilotMessages.length === 0 &&
      !isCopilotLoading
    ) {
      generateExecutiveSummary()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, activeSession?.sessionId])

  // ---- Review callbacks ----
  const [isApproving, setIsApproving] = useState(false)

  const handleFinalizeReview = useCallback(async (decisions: Array<{
    index: number
    description: string
    decision: string
    N1: string; N2: string; N3: string; N4: string
    confidence: number
    source: string
    contribute_to_kb?: boolean
    instruction_used?: string
  }>) => {
    const session = activeSession as unknown as TaxonomySession
    if (!session?.jobId || !activeProjectId) return
    setIsApproving(true)
    try {
      const { apiClient } = await import('@/lib/api')
      const result = await (apiClient as any).approveClassifications({
        jobId: session.jobId,
        projectId: activeProjectId,
        decisions,
      })
      console.log('[TaxonomyPage] Review finalized:', result)
      // Update session with approved data -> triggers sessionPhase='completed' -> auto-navigate to Analisar
      await setReviewCompleted(
        result.summary,
        result.file_content_base64 || '',
        result.download_filename || 'resultado_aprovado.xlsx'
      )
    } catch (e) {
      console.error('[TaxonomyPage] ApproveClassifications error:', e)
      alert('Erro ao finalizar revisão. Tente novamente.')
    } finally {
      setIsApproving(false)
    }
  }, [activeSession, activeProjectId, setReviewCompleted])

  const handleReclassify = useCallback(async (
    items: ClassifiedItem[],
    instruction: string
  ): Promise<ClassifiedItem[]> => {
    const session = activeSession as unknown as TaxonomySession
    if (!session?.jobId || !activeProjectId) return items
    try {
      const { apiClient } = await import('@/lib/api')
      const result = await (apiClient as any).reclassifyItems({
        jobId: session.jobId,
        projectId: activeProjectId,
        items: items.map(i => ({ index: i.index, description: i.description })),
        instruction,
      })
      return result.results as ClassifiedItem[]
    } catch (e) {
      console.error('[TaxonomyPage] ReclassifyItems error:', e)
      return items
    }
  }, [activeSession, activeProjectId])

  // ---- Hierarchy from active project ----
  const projectHierarchy = useMemo<HierarchyEntry[] | null>(() => {
    return activeProject?.custom_hierarchy ?? null
  }, [activeProject])

  const typedSession = activeSession as unknown as (TaxonomySession | undefined)
  const progressPct = progress?.pct ?? 0

  // ---- Review progress for ContextBar ----
  const reviewedCount = typedSession?.reviewedCount ?? 0
  const totalItems = typedSession?.totalItems ?? typedSession?.items?.length ?? 0

  // ============================================================
  // Render
  // ============================================================

  return (
    <>
      <Head>
        <title>Spend Analysis | PG Consultoria</title>
        <meta name="description" content="Plataforma de classificação de gastos" />
      </Head>

      <div className="flex h-screen overflow-hidden bg-gray-50">

        {/* ============================================================
            LEFT SIDEBAR (Collapsible)
        ============================================================ */}
        <CollapsibleSidebar
          activeProject={activeProject ? { project_id: activeProject.project_id, display_name: activeProject.display_name, sector: activeProject.sector } : null}
          sessions={sessions.map(s => ({
            sessionId: s.sessionId,
            filename: s.filename,
            timestamp: s.timestamp,
            jobStatus: (s as any).jobStatus,
            reviewState: (s as any).reviewState,
          }))}
          activeSessionId={activeSessionId}
          onSessionSelect={id => setActiveSessionId(id)}
          onNewSession={handleNewUpload}
          onOpenKB={() => setKbOpen(true)}
          onClearHistory={handleClearHistory}
          onDeleteSession={handleDeleteSession}
          renderProjectSelect={({ collapsed }) => collapsed ? null : (
            <ProjectSelect
              projects={projects}
              sectors={sectors}
              selectedProjectId={activeProjectId}
              onSelect={id => setActiveProjectId(id)}
              onCreateProject={() => setShowCreateProject(true)}
              onEditProject={p => setEditingProject(p)}
              onDeleteProject={p => setDeletingProject(p)}
              loading={projectsLoading}
              variant="dark"
            />
          )}
        />

        {/* ============================================================
            MAIN CONTENT
        ============================================================ */}
        <main className="flex-1 flex flex-col overflow-hidden">

          {/* Gate: no project selected */}
          {!activeProjectId ? (
            <NoProjectGate
              hasProjects={projects.length > 0}
              onCreateProject={() => setShowCreateProject(true)}
            />
          ) : (
            <>

              {/* ContextBar (replaces WorkflowStepper) */}
              <ContextBar
                projectName={activeProject?.display_name ?? null}
                sessionFilename={typedSession?.filename ?? null}
                activeStep={activeTab}
                stepStatuses={stepStatuses}
                onStepClick={setActiveTab}
                onOpenKB={() => setKbOpen(true)}
                kbDisabled={sessionPhase === 'processing'}
                reviewProgress={sessionPhase === 'reviewing' || sessionPhase === 'classified' ? { reviewed: reviewedCount, total: totalItems } : undefined}
                hasReviewNotification={sessionPhase === 'classified'}
              />

              {/* Tab content */}
              <div className={`flex-1 ${activeTab === 'analyze' ? 'flex flex-col overflow-hidden' : 'overflow-y-auto'} p-6`}>

                {/* ---- CLASSIFY ---- */}
                {activeTab === 'classify' && (
                  <div className="max-w-4xl mx-auto">
                    <div className="mb-6">
                      <h2 className="text-lg font-semibold text-[#32373c]">Classificar Itens</h2>
                      <p className="text-sm text-primary-500 mt-0.5">
                        Faça upload do arquivo de itens para iniciar a classificação com IA.
                      </p>
                    </div>

                    <ClassifyTab
                      onFileSelect={handleFileSelect}
                      isProcessing={isProcessing}
                      projectId={activeProjectId}
                      projectHierarchy={projectHierarchy}
                    />
                  </div>
                )}

                {/* ---- REVIEW ---- */}
                {activeTab === 'review' && stepStatuses.review !== 'locked' && (
                  typedSession?.items && typedSession.items.length > 0 ? (
                    <ReviewTab
                      sessionId={typedSession.sessionId}
                      items={typedSession.items as ClassifiedItem[]}
                      hierarchy={projectHierarchy}
                      jobId={typedSession.jobId || ''}
                      projectId={activeProjectId || ''}
                      onFinalizeReview={handleFinalizeReview}
                      onReclassify={handleReclassify}
                      isApproving={isApproving}
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full py-16 text-gray-400">
                      <svg className="w-12 h-12 mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                      </svg>
                      <p className="text-sm text-gray-500">Nenhum item para revisar. Classifique um arquivo primeiro.</p>
                    </div>
                  )
                )}

                {/* ---- ANALYZE ---- */}
                {activeTab === 'analyze' && stepStatuses.analyze !== 'locked' && (
                  <div className="flex flex-col flex-1 min-h-0 max-w-4xl mx-auto w-full">
                    {/* Compact summary header + download + close */}
                    <div className="flex items-center justify-between bg-white rounded-xl border border-gray-100 px-5 py-3 shadow-sm mb-4 flex-shrink-0">
                      <div className="flex items-center gap-6 text-sm">
                        {typedSession?.reviewSummary ? (
                          <>
                            <span><strong className="text-[#32373c]">{typedSession.reviewSummary.total}</strong> <span className="text-primary-400">total</span></span>
                            <span><strong className="text-mint-500">{typedSession.reviewSummary.approved}</strong> <span className="text-primary-400">aprovados</span></span>
                            <span><strong className="text-accent-500">{typedSession.reviewSummary.edited}</strong> <span className="text-primary-400">editados</span></span>
                            <span><strong className="text-accent-500">{typedSession.reviewSummary.kb_added}</strong> <span className="text-primary-400">na base</span></span>
                          </>
                        ) : (
                          <span className="text-primary-400">Analise Conversacional</span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {typedSession?.approvedFileContentBase64 && typedSession.approvedDownloadFilename && (
                          <button
                            onClick={() => {
                              const base64 = typedSession.approvedFileContentBase64!
                              const bytes = atob(base64)
                              const arr = new Uint8Array(bytes.length)
                              for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
                              const blob = new Blob([arr], {
                                type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                              })
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url
                              a.download = typedSession.approvedDownloadFilename!
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
                          onClick={() => { setActiveSessionId(null); setActiveTab('classify') }}
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
                          <SuggestedPrompts onSelect={(prompt) => { setUserMessage(prompt); sendUserMessage(prompt); }} />
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
                        if (userMessage.trim()) sendUserMessage(userMessage.trim())
                      }}
                      className="flex gap-2 mt-4 flex-shrink-0"
                    >
                      <input
                        type="text"
                        value={userMessage}
                        onChange={e => setUserMessage(e.target.value)}
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
                )}

              </div>
            </>
          )}
        </main>
      </div>

      {/* ============================================================
          KB SLIDE-OVER
      ============================================================ */}
      <SlideOver
        isOpen={kbOpen}
        onClose={() => setKbOpen(false)}
        title="Base de Conhecimento"
        subtitle={activeProject?.display_name}
        defaultWidth={1100}
        minWidth={600}
        resizable
        storageKey="kb-panel"
      >
        <div className="flex flex-col h-full">
          {/* Sub-tabs: Projeto / Setor */}
          <div className="px-6 pt-3 pb-0 flex-shrink-0">
            <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5 w-fit">
              <button
                onClick={() => setKbTab('project')}
                className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  kbTab === 'project'
                    ? 'bg-white text-[#0693e3] shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Projeto
              </button>
              <button
                onClick={() => setKbTab('sector')}
                className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  kbTab === 'sector'
                    ? 'bg-white text-[#0693e3] shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Setor{activeProject?.sector ? ` (${sectors.find(s => s.name === activeProject.sector)?.display_name || activeProject.sector})` : ''}
              </button>
            </div>
          </div>

          {/* Tab content */}
          <div className="flex-1 min-h-0">
            {kbTab === 'project' ? (
              <KnowledgeTab
                projectId={activeProjectId}
                projectHierarchy={projectHierarchy}
                sectorName={activeProject?.sector ?? null}
                useSectorKb={activeProject?.use_sector_kb ?? true}
              />
            ) : (activeProject?.use_sector_kb ?? true) ? (
              <SectorKnowledgeTab
                sectorName={activeProject?.sector ?? null}
              />
            ) : (
              <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                <svg className="w-12 h-12 mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                </svg>
                <p className="text-sm font-medium text-gray-500">Base do setor desabilitada para este projeto</p>
                <p className="text-xs text-gray-400 mt-1">Ative em Editar Projeto para usar a KB compartilhada do setor.</p>
              </div>
            )}
          </div>
        </div>
      </SlideOver>

      {/* ============================================================
          PROCESSING OVERLAY
      ============================================================ */}
      <ProcessingOverlay
        isVisible={isProcessing}
        message="Classificando itens..."
        subMessage="Aguarde enquanto a IA processa o arquivo."
        progress={progressPct}
        status={progress?.message || 'Processando...'}
      />

      {/* ============================================================
          CREATE PROJECT MODAL
      ============================================================ */}
      <CreateProjectModal
        isOpen={showCreateProject}
        onClose={() => setShowCreateProject(false)}
        onCreated={async project => {
          await fetchProjects()
          setActiveProjectId(project.project_id)
          setShowCreateProject(false)
        }}
        sectors={sectors}
        onCreateSector={createSector}
        existingProjects={projects}
        createProject={createProject}
      />

      {/* ============================================================
          EDIT PROJECT MODAL
      ============================================================ */}
      <EditProjectModal
        isOpen={editingProject !== null}
        project={editingProject}
        onClose={() => setEditingProject(null)}
        onSave={async (projectId, data) => {
          await updateProject(projectId, data)
        }}
      />

      {/* ============================================================
          DELETE PROJECT CONFIRM
      ============================================================ */}
      <ConfirmDialog
        isOpen={deletingProject !== null}
        title="Excluir Projeto"
        message={`Tem certeza que deseja excluir o projeto "${deletingProject?.display_name}"? Todos os dados, incluindo a Base de Conhecimento, serao permanentemente apagados.`}
        confirmLabel="Excluir"
        cancelLabel="Cancelar"
        variant="danger"
        onConfirm={async () => {
          if (!deletingProject) return
          try {
            const id = deletingProject.project_id
            // If we're deleting the active project, deselect it
            if (activeProjectId === id) {
              setActiveProjectId(null)
            }
            await deleteProject(id)
            setDeletingProject(null)
          } catch (e) {
            console.error('[TaxonomyPage] DeleteProject error:', e)
            alert('Erro ao excluir projeto. Tente novamente.')
            setDeletingProject(null)
          }
        }}
        onCancel={() => setDeletingProject(null)}
      />
    </>
  )
}

export default TaxonomyPage
