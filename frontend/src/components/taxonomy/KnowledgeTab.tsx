import React, { useState, useEffect, useCallback } from 'react';
import type { KBEntry, KBPage, KBCoverage, KBVersion } from '../../lib/types';
import { KnowledgeTable } from './KnowledgeTable';
import { KnowledgeCoverage } from './KnowledgeCoverage';

// Import api lazily
const getApi = () => import('../../lib/api').then(m => m.apiClient);

interface KnowledgeTabProps {
  projectId: string | null;
  projectHierarchy?: any[] | null;
  sectorName?: string | null;
  useSectorKb?: boolean;
}

export function KnowledgeTab({ projectId, projectHierarchy, sectorName, useSectorKb = true }: KnowledgeTabProps) {
  const [kbPage, setKbPage] = useState<KBPage | null>(null);
  const [sectorKbPage, setSectorKbPage] = useState<KBPage | null>(null);
  const [coverage, setCoverage] = useState<KBCoverage | null>(null);
  const [versions, setVersions] = useState<KBVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [showSectorEntries, setShowSectorEntries] = useState(true);
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(new Set());
  const [isPromoting, setIsPromoting] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const loadKB = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const api = await getApi();
      const [projectData, sectorData] = await Promise.all([
        api.getKnowledgeBase(projectId, { page, pageSize: 50, search: searchQuery || undefined }),
        sectorName && useSectorKb ? api.getSectorKB(sectorName, { page: 1, pageSize: 200, search: searchQuery || undefined }) : Promise.resolve(null),
      ]);
      setKbPage(projectData);
      setSectorKbPage(sectorData);
    } catch (e) {
      console.error('Error loading KB:', e);
    } finally {
      setLoading(false);
    }
  }, [projectId, sectorName, useSectorKb, page, searchQuery]);

  const loadCoverage = useCallback(async () => {
    if (!projectId) return;
    setCoverageLoading(true);
    try {
      const api = await getApi();
      const data = await api.getKBCoverage(projectId);
      setCoverage(data);
    } catch (e) {
      console.error('Error loading KB coverage:', e);
    } finally {
      setCoverageLoading(false);
    }
  }, [projectId]);

  const loadVersions = useCallback(async () => {
    if (!projectId) return;
    try {
      const api = await getApi();
      const data = await api.getKBVersions(projectId);
      setVersions(data);
    } catch (e) {
      console.error('Error loading KB versions:', e);
    }
  }, [projectId]);

  useEffect(() => {
    loadKB();
    loadCoverage();
  }, [loadKB, loadCoverage]);

  useEffect(() => {
    if (showVersions) loadVersions();
  }, [showVersions, loadVersions]);

  const handleDelete = async (entryId: string) => {
    if (!projectId) return;
    const api = await getApi();
    await api.deleteKBEntry(projectId, entryId);
    loadKB();
    loadCoverage();
  };

  const handleUpdate = async (entryId: string, data: any) => {
    if (!projectId) return;
    const api = await getApi();
    await api.updateKBEntry(projectId, entryId, data);
    loadKB();
  };

  const handleExport = async () => {
    if (!projectId) return;
    const api = await getApi();
    const b64 = await api.exportKB(projectId);
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `knowledge_base_${projectId}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!projectId || !e.target.files?.[0]) return;
    setIsImporting(true);
    setImportError(null);
    try {
      const file = e.target.files[0];
      const b64 = await new Promise<string>((res, rej) => {
        const reader = new FileReader();
        reader.onload = () => res((reader.result as string).split(',')[1]);
        reader.onerror = rej;
        reader.readAsDataURL(file);
      });
      const api = await getApi();
      const result = await api.importKB(projectId, b64);
      await loadKB();
      alert(`Importacao concluida: ${result.added} entradas adicionadas. Total: ${result.total}`);
    } catch (e: any) {
      setImportError(e.message || 'Erro ao importar');
    } finally {
      setIsImporting(false);
      e.target.value = '';
    }
  };

  const handleRollback = async (versionId: string) => {
    if (!projectId) return;
    if (!confirm(`Reverter para a versao ${versionId}? As entradas atuais serao substituidas.`)) return;
    const api = await getApi();
    await api.rollbackKB(projectId, versionId);
    await loadKB();
    setShowVersions(false);
  };

  const handlePromoteToSector = async () => {
    if (!projectId || !sectorName || selectedEntries.size === 0) return;
    setIsPromoting(true);
    try {
      const api = await getApi();
      const result = await api.promoteToSectorKB(projectId, sectorName, Array.from(selectedEntries));
      setSelectedEntries(new Set());
      await loadKB();
      alert(`${result.promoted_count} entrada(s) promovida(s) para o setor.`);
    } catch (e: any) {
      alert(e.message || 'Erro ao promover entradas');
    } finally {
      setIsPromoting(false);
    }
  };

  // Merge project + sector entries for display
  const mergedEntries: KBEntry[] = React.useMemo(() => {
    const rawProjectEntries = kbPage?.entries || [];
    const sectorNorms = new Set((sectorKbPage?.entries || []).map(e => e.description_norm));

    // Tag project entries: 'both' if also in sector, else 'project'
    const projectEntries = rawProjectEntries.map(e => ({
      ...e,
      _origin: (sectorNorms.has(e.description_norm) ? 'both' : 'project') as 'project' | 'sector' | 'both',
    }));

    if (!showSectorEntries || !sectorKbPage?.entries?.length) return projectEntries;

    // Sector entries that are NOT already in project (by description_norm)
    const projectNorms = new Set(rawProjectEntries.map(e => e.description_norm));
    const sectorOnly = sectorKbPage.entries
      .filter(e => !projectNorms.has(e.description_norm))
      .map(e => ({ ...e, _origin: 'sector' as const }));

    // Sector entries first so they're always visible
    return [...sectorOnly, ...projectEntries];
  }, [kbPage, sectorKbPage, showSectorEntries]);

  const projectTotal = kbPage?.total ?? 0;
  const sectorTotal = sectorKbPage?.total ?? 0;

  if (!projectId) {
    return (
      <div className="text-center py-16 text-gray-400">
        <svg className="w-12 h-12 mx-auto mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <p className="text-sm font-medium text-gray-500">Selecione um projeto para ver sua Base de Conhecimento</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with stats and actions */}
      <div className="px-6 pt-4 pb-3 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-500">
            {kbPage ? (
              <>
                {projectTotal + sectorTotal} exemplos
                {sectorTotal > 0 && (
                  <span className="text-gray-400">
                    {' '}({sectorTotal} do setor + {projectTotal} do projeto)
                  </span>
                )}
              </>
            ) : 'Carregando...'}
          </p>
          <div className="flex items-center gap-1.5">
            {/* Version history button */}
            <button
              onClick={() => setShowVersions(!showVersions)}
              className={`p-1.5 rounded-lg transition-colors ${
                showVersions
                  ? 'bg-[#eff8ff] text-[#0693e3]'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title="Historico de versoes"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </button>
            {/* Import */}
            <label className={`p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 cursor-pointer transition-colors ${isImporting ? 'opacity-50' : ''}`} title="Importar">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
              <input type="file" accept=".xlsx" onChange={handleImport} className="hidden" disabled={isImporting} />
            </label>
            {/* Export */}
            <button onClick={handleExport} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors" title="Exportar">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10" /></svg>
            </button>
            {/* Promote to sector */}
            {sectorName && useSectorKb && selectedEntries.size > 0 && (
              <button
                onClick={handlePromoteToSector}
                disabled={isPromoting}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#0693e3] text-white rounded-lg hover:bg-[#0576b8] disabled:opacity-50 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>
                {isPromoting ? 'Promovendo...' : `Promover p/ Setor (${selectedEntries.size})`}
              </button>
            )}
          </div>
        </div>

        {importError && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">{importError}</div>
        )}

        {/* Version history panel (inline, toggled by icon button) */}
        {showVersions && (
          <div className="mb-3 border border-gray-100 rounded-xl overflow-hidden">
            <div className="px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-600">Historico de Versoes</span>
              <button onClick={() => setShowVersions(false)} className="text-gray-400 hover:text-gray-600 p-0.5">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="max-h-48 overflow-y-auto">
              {versions.length === 0 ? (
                <p className="text-xs text-gray-400 text-center py-6">Nenhuma versao salva ainda.</p>
              ) : (
                <div className="divide-y divide-gray-50">
                  {versions.map(v => (
                    <div key={v.version_id} className="flex items-center justify-between px-3 py-2.5 hover:bg-gray-50">
                      <div className="min-w-0">
                        <span className="text-xs font-medium text-gray-800">{v.version_id}</span>
                        <span className="text-xs text-gray-400 ml-2">{new Date(v.created_at).toLocaleString('pt-BR')}</span>
                        <span className="text-xs text-gray-500 ml-2">{v.entry_count} entradas</span>
                      </div>
                      <button
                        onClick={() => handleRollback(v.version_id)}
                        className="flex-shrink-0 text-xs px-2.5 py-1 border border-orange-200 text-orange-600 hover:bg-orange-50 rounded-lg transition-colors"
                      >
                        Reverter
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Coverage section (collapsible, collapsed by default) */}
        <KnowledgeCoverage coverage={coverage} loading={coverageLoading} />
      </div>

      {/* Search bar - always visible */}
      <div className="px-6 py-3 border-b border-gray-100 flex-shrink-0">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Buscar na base de conhecimento..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] transition-all"
          />
        </div>
      </div>

      {/* Table area - scrollable */}
      <div className="flex-1 overflow-y-auto px-6 py-3">
        <KnowledgeTable
          kbPage={kbPage}
          entries={mergedEntries}
          loading={loading}
          onPageChange={setPage}
          onDelete={handleDelete}
          onUpdate={handleUpdate}
          onSearch={setSearchQuery}
          searchQuery={searchQuery}
          selectable={!!sectorName && useSectorKb}
          selectedIds={selectedEntries}
          onSelectionChange={setSelectedEntries}
          showSectorEntries={showSectorEntries}
          onToggleSectorEntries={useSectorKb ? setShowSectorEntries : undefined}
          hasSectorKB={useSectorKb && sectorTotal > 0}
        />
      </div>
    </div>
  );
}
