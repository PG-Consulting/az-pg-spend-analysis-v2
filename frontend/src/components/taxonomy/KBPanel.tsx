import React from 'react'
import { KnowledgeTab } from '@/components/taxonomy/KnowledgeTab'
import { SectorKnowledgeTab } from '@/components/taxonomy/SectorKnowledgeTab'
import { useAuth } from '@/contexts/AuthContext'
import type { HierarchyEntry } from '@/lib/types'

interface KBPanelProps {
  kbTab: 'project' | 'sector'
  onKbTabChange: (tab: 'project' | 'sector') => void
  projectId: string | null
  projectHierarchy: HierarchyEntry[] | null
  sectorName: string | null
  sectorDisplayName: string | null
  useSectorKb: boolean
}

export default function KBPanel({
  kbTab,
  onKbTabChange,
  projectId,
  projectHierarchy,
  sectorName,
  sectorDisplayName,
  useSectorKb,
}: KBPanelProps) {
  const { isAdmin } = useAuth()

  return (
    <div className="flex flex-col h-full">
      {/* Sub-tabs: Projeto / Setor */}
      <div className="px-6 pt-3 pb-0 flex-shrink-0">
        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5 w-fit">
          <button
            onClick={() => onKbTabChange('project')}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
              kbTab === 'project'
                ? 'bg-white text-[#0693e3] shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Projeto
          </button>
          <button
            onClick={() => onKbTabChange('sector')}
            className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
              kbTab === 'sector'
                ? 'bg-white text-[#0693e3] shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Setor{sectorDisplayName ? ` (${sectorDisplayName})` : ''}
          </button>
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">
        {kbTab === 'project' ? (
          <KnowledgeTab
            projectId={projectId}
            projectHierarchy={projectHierarchy}
            sectorName={sectorName}
            useSectorKb={useSectorKb}
            isAdmin={isAdmin}
          />
        ) : useSectorKb ? (
          <SectorKnowledgeTab
            sectorName={sectorName}
            isAdmin={isAdmin}
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
  )
}
