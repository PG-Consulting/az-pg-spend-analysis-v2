import React, { useState, useRef, useEffect, useMemo } from 'react'
import type { Project, Sector } from '../../lib/types'

interface ProjectSelectProps {
  projects: Project[]
  sectors: Sector[]
  selectedProjectId: string | null
  onSelect: (projectId: string | null) => void
  onCreateProject: () => void
  onEditProject?: (project: Project) => void
  onDeleteProject?: (project: Project) => void
  onDeleteSector?: (sector: Sector) => void
  loading?: boolean
  className?: string
  variant?: 'light' | 'dark' // kept for API compat
}

export function ProjectSelect({
  projects,
  sectors,
  selectedProjectId,
  onSelect,
  onCreateProject,
  onEditProject,
  onDeleteProject,
  onDeleteSector,
  loading = false,
  className = '',
}: ProjectSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedProject = projects.find(p => p.project_id === selectedProjectId)

  const getSectorDisplay = (sectorName: string) => {
    const s = sectors.find(s => s.name === sectorName)
    return s?.display_name || sectorName
  }

  const getInitial = (name: string) => name.trim().charAt(0).toUpperCase()

  // Group by sector — include all sectors (even empty ones)
  const bySector = useMemo(() => {
    const groups: Record<string, Project[]> = {}
    for (const s of sectors) {
      groups[s.name] = []
    }
    for (const p of projects) {
      if (!groups[p.sector]) groups[p.sector] = []
      groups[p.sector].push(p)
    }
    return groups
  }, [sectors, projects])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [isOpen])

  return (
    <div className={`relative ${className}`} ref={containerRef}>

      {/* Label */}
      <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-white/30 mb-2 px-0.5">
        Projeto Ativo
      </p>

      {/* Trigger */}
      <button
        onClick={() => !loading && setIsOpen(!isOpen)}
        disabled={loading}
        className={[
          'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border transition-all duration-200 text-left',
          isOpen
            ? 'bg-white/10 border-white/20'
            : 'bg-white/[0.06] hover:bg-white/10 border-white/[0.08] hover:border-white/15',
          'disabled:opacity-40',
        ].join(' ')}
      >
        {/* Avatar */}
        {loading ? (
          <div className="w-8 h-8 rounded-lg bg-white/10 animate-pulse shrink-0" />
        ) : selectedProject ? (
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#0693e3] to-[#0576b8] flex items-center justify-center shrink-0 shadow-[0_0_12px_rgba(6,147,227,0.25)]">
            <span className="text-sm font-bold text-white">{getInitial(selectedProject.display_name)}</span>
          </div>
        ) : (
          <div className="w-8 h-8 rounded-lg bg-white/8 border border-white/10 flex items-center justify-center shrink-0">
            <svg className="w-4 h-4 text-white/25" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
          </div>
        )}

        {/* Text */}
        <div className="flex-1 min-w-0">
          {selectedProject ? (
            <>
              <div className="text-sm font-semibold text-white leading-tight truncate">
                {selectedProject.display_name}
              </div>
              <div className="text-[10px] text-white/35 mt-0.5 truncate">
                {getSectorDisplay(selectedProject.sector)}
              </div>
            </>
          ) : (
            <div className="text-sm text-white/30">Selecionar projeto</div>
          )}
        </div>

        {/* Chevron */}
        <svg
          className={`w-3.5 h-3.5 text-white/25 shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div className="absolute left-0 right-0 top-full mt-2 z-50 bg-[#0e1b38] border border-white/[0.08] rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.6)] overflow-hidden">

          <div className="max-h-60 overflow-y-auto">
            {/* Clear selection */}
            <div className="p-2 pb-0">
              <button
                onClick={() => { onSelect(null); setIsOpen(false) }}
                className={[
                  'w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left transition-all text-xs',
                  !selectedProjectId
                    ? 'bg-white/8 text-white/50'
                    : 'text-white/30 hover:bg-white/5 hover:text-white/50',
                ].join(' ')}
              >
                <div className="w-5 h-5 rounded-md bg-white/6 flex items-center justify-center">
                  <svg className="w-3 h-3 text-white/25" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                  </svg>
                </div>
                Nenhum projeto
              </button>
            </div>

            {/* Sector groups */}
            {Object.entries(bySector).map(([sector, sectorProjects]) => (
              <div key={sector} className="px-2 pt-3 pb-1 group/sector">
                <div className="flex items-center justify-between px-2 pb-1.5">
                  <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-white/20">
                    {getSectorDisplay(sector)}
                  </p>
                  {onDeleteSector && (
                    <button
                      onClick={e => { e.stopPropagation(); onDeleteSector(sectors.find(s => s.name === sector)!); setIsOpen(false) }}
                      title="Excluir setor"
                      className="opacity-0 group-hover/sector:opacity-100 w-5 h-5 flex items-center justify-center rounded-md hover:bg-red-500/20 text-white/20 hover:text-red-400 transition-all"
                    >
                      <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  )}
                </div>
                {sectorProjects.length === 0 && (
                  <p className="px-3 py-2 text-[11px] text-white/15 italic">Nenhum projeto</p>
                )}
                {sectorProjects.map(p => {
                  const isSelected = p.project_id === selectedProjectId
                  return (
                    <div
                      key={p.project_id}
                      className={[
                        'w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left transition-all group',
                        isSelected
                          ? 'bg-[#0693e3]/12 text-white'
                          : 'text-white/55 hover:bg-white/[0.05] hover:text-white',
                      ].join(' ')}
                    >
                      <button
                        onClick={() => { onSelect(p.project_id); setIsOpen(false) }}
                        className="flex items-center gap-2.5 flex-1 min-w-0"
                      >
                        <div className={[
                          'w-6 h-6 rounded-lg flex items-center justify-center shrink-0 text-[10px] font-bold transition-all',
                          isSelected
                            ? 'bg-gradient-to-br from-[#0693e3] to-[#38a8f5] text-white shadow-[0_0_8px_rgba(56,190,201,0.25)]'
                            : 'bg-white/8 text-white/35 group-hover:bg-white/12 group-hover:text-white/55',
                        ].join(' ')}>
                          {getInitial(p.display_name)}
                        </div>
                        <span className="text-sm truncate flex-1">{p.display_name}</span>
                        {isSelected && (
                          <svg className="w-3.5 h-3.5 text-[#38a8f5] shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </button>
                      {/* Edit / Delete actions */}
                      <div className="flex gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        {onEditProject && (
                          <button
                            onClick={e => { e.stopPropagation(); onEditProject(p); setIsOpen(false) }}
                            title="Editar projeto"
                            className="w-6 h-6 flex items-center justify-center rounded-md hover:bg-white/10 text-white/30 hover:text-white/70 transition-colors"
                          >
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                          </button>
                        )}
                        {onDeleteProject && (
                          <button
                            onClick={e => { e.stopPropagation(); onDeleteProject(p); setIsOpen(false) }}
                            title="Excluir projeto"
                            className="w-6 h-6 flex items-center justify-center rounded-md hover:bg-red-500/20 text-white/30 hover:text-red-400 transition-colors"
                          >
                            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}

            {projects.length === 0 && (
              <div className="px-4 py-8 text-center text-xs text-white/25">
                Nenhum projeto criado ainda
              </div>
            )}
          </div>

          {/* Footer: create project */}
          <div className="border-t border-white/[0.06] p-2">
            <button
              onClick={() => { onCreateProject(); setIsOpen(false) }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-[#38a8f5] hover:bg-[#38a8f5]/8 transition-all text-sm font-medium group"
            >
              <div className="w-6 h-6 rounded-lg bg-[#38a8f5]/10 group-hover:bg-[#38a8f5]/15 flex items-center justify-center transition-all">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
              </div>
              Criar novo projeto
            </button>
          </div>

        </div>
      )}
    </div>
  )
}
