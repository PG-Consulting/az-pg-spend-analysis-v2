import React, { useState, useEffect, useCallback } from 'react';
import type { KBPage, KBCoverage, KBVersion } from '../../lib/types';
import { KnowledgeTable } from './KnowledgeTable';
import { KnowledgeCoverage } from './KnowledgeCoverage';

const getApi = () => import('../../lib/api').then(m => m.apiClient);

interface SectorKnowledgeTabProps {
  sectorName: string | null;
}

export function SectorKnowledgeTab({ sectorName }: SectorKnowledgeTabProps) {
  const [kbPage, setKbPage] = useState<KBPage | null>(null);
  const [coverage, setCoverage] = useState<KBCoverage | null>(null);
  const [versions, setVersions] = useState<KBVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  const loadKB = useCallback(async () => {
    if (!sectorName) return;
    setLoading(true);
    try {
      const api = await getApi();
      const data = await api.getSectorKB(sectorName, { page, pageSize: 50, search: searchQuery || undefined });
      setKbPage(data);
    } catch (e) {
      console.error('Error loading sector KB:', e);
    } finally {
      setLoading(false);
    }
  }, [sectorName, page, searchQuery]);

  const loadCoverage = useCallback(async () => {
    if (!sectorName) return;
    setCoverageLoading(true);
    try {
      const api = await getApi();
      const data = await api.getSectorKBCoverage(sectorName);
      setCoverage(data);
    } catch (e) {
      console.error('Error loading sector KB coverage:', e);
    } finally {
      setCoverageLoading(false);
    }
  }, [sectorName]);

  const loadVersions = useCallback(async () => {
    if (!sectorName) return;
    try {
      const api = await getApi();
      const data = await api.getSectorKBVersions(sectorName);
      setVersions(data);
    } catch (e) {
      console.error('Error loading sector KB versions:', e);
    }
  }, [sectorName]);

  useEffect(() => {
    loadKB();
    loadCoverage();
  }, [loadKB, loadCoverage]);

  useEffect(() => {
    if (showVersions) loadVersions();
  }, [showVersions, loadVersions]);

  const handleDelete = async (entryId: string) => {
    if (!sectorName) return;
    const api = await getApi();
    await api.deleteSectorKBEntry(sectorName, entryId);
    loadKB();
    loadCoverage();
  };

  const handleBulkDelete = async () => {
    if (!sectorName || selectedEntries.size === 0) return;
    if (!confirm(`Excluir ${selectedEntries.size} entrada(s) do setor? Esta ação não pode ser desfeita.`)) return;
    setIsDeleting(true);
    try {
      const api = await getApi();
      for (const entryId of selectedEntries) {
        await api.deleteSectorKBEntry(sectorName, entryId);
      }
      setSelectedEntries(new Set());
      await loadKB();
      loadCoverage();
    } catch (e: any) {
      alert(e.message || 'Erro ao excluir entradas');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleUpdate = async (entryId: string, data: any) => {
    if (!sectorName) return;
    const api = await getApi();
    await api.updateSectorKBEntry(sectorName, entryId, data);
    loadKB();
  };

  const handleExport = async () => {
    if (!sectorName) return;
    const api = await getApi();
    const b64 = await api.exportSectorKB(sectorName);
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `knowledge_base_sector_${sectorName}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!sectorName || !e.target.files?.[0]) return;
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
      const result = await api.importSectorKB(sectorName, b64);
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
    if (!sectorName) return;
    if (!confirm(`Reverter para a versao ${versionId}? As entradas atuais serao substituidas.`)) return;
    const api = await getApi();
    await api.rollbackSectorKB(sectorName, versionId);
    await loadKB();
    setShowVersions(false);
  };

  if (!sectorName) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-gray-400">
        <svg className="w-12 h-12 mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        <p className="text-sm font-medium text-gray-500">Selecione um projeto para ver a Base de Conhecimento do setor</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with stats and actions */}
      <div className="px-6 pt-4 pb-3 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-500">
            {kbPage ? `${kbPage.total} entradas compartilhadas entre projetos` : 'Carregando...'}
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
            {/* Bulk delete */}
            {selectedEntries.size > 0 && (
              <button
                onClick={handleBulkDelete}
                disabled={isDeleting}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                {isDeleting ? 'Excluindo...' : `Excluir (${selectedEntries.size})`}
              </button>
            )}
          </div>
        </div>

        {importError && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700 mb-3">{importError}</div>
        )}

        {/* Version history panel */}
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

        {/* Coverage */}
        <KnowledgeCoverage coverage={coverage} loading={coverageLoading} />
      </div>

      {/* Search bar */}
      <div className="px-6 py-3 border-b border-gray-100 flex-shrink-0">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Buscar na base de conhecimento do setor..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] transition-all"
          />
        </div>
      </div>

      {/* Table area */}
      <div className="flex-1 overflow-y-auto px-6 py-3">
        <KnowledgeTable
          kbPage={kbPage}
          loading={loading}
          onPageChange={setPage}
          onDelete={handleDelete}
          onUpdate={handleUpdate}
          onSearch={setSearchQuery}
          searchQuery={searchQuery}
          selectable={true}
          selectedIds={selectedEntries}
          onSelectionChange={setSelectedEntries}
        />
      </div>
    </div>
  );
}
