import React from 'react'
import { SlideOver } from '../ui/SlideOver'
import { KnowledgeTab } from './KnowledgeTab'
import type { HierarchyEntry } from '@/lib/types'

interface KnowledgeSlideOverProps {
  isOpen: boolean
  onClose: () => void
  projectId: string | null
  projectHierarchy: HierarchyEntry[] | null
  sectorName: string | null
}

export function KnowledgeSlideOver({ isOpen, onClose, projectId, projectHierarchy, sectorName }: KnowledgeSlideOverProps) {
  return (
    <SlideOver
      isOpen={isOpen}
      onClose={onClose}
      title="Base de Conhecimento"
      subtitle={sectorName ? `Setor: ${sectorName}` : undefined}
      defaultWidth={1100}
      minWidth={600}
      resizable
      storageKey="kb-panel"
    >
      {projectId ? (
        <KnowledgeTab
          projectId={projectId}
          projectHierarchy={projectHierarchy}
          sectorName={sectorName}
        />
      ) : (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <p className="text-sm text-primary-400">Selecione um projeto para ver a Base de Conhecimento.</p>
        </div>
      )}
    </SlideOver>
  )
}
