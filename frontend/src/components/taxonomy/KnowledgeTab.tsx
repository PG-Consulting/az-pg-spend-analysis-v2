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
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importPreview, setImportPreview] = useState<{
    rows: Array<Record<string, string>>;
    totalRows: number;
    columns: string[];
    file: File;
    b64: string;
  } | null>(null);
  const [importResult, setImportResult] = useState<{ added: number; total: number } | null>(null);
  const [showSectorEntries, setShowSectorEntries] = useState(true);
  const [selectedEntries, setSelectedEntries] = useState<Set<string>>(new Set());
  const [isPromoting, setIsPromoting] = useState(false);
  const [showVersions, setShowVersions] = useState(false);

  // Debounce search query to avoid API flood on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadKB = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const api = await getApi();
      const [projectData, sectorData] = await Promise.all([
        api.getKnowledgeBase(projectId, { page, pageSize: 50, search: debouncedSearch || undefined }),
        sectorName && useSectorKb ? api.getSectorKB(sectorName, { page: 1, pageSize: 200, search: debouncedSearch || undefined }) : Promise.resolve(null),
      ]);
      setKbPage(projectData);
      setSectorKbPage(sectorData);
    } catch (e) {
      console.error('Error loading KB:', e);
    } finally {
      setLoading(false);
    }
  }, [projectId, sectorName, useSectorKb, page, debouncedSearch]);

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
    try {
      const api = await getApi();
      await api.deleteKBEntry(projectId, entryId);
      loadKB();
      loadCoverage();
    } catch (e) {
      console.error('Failed to delete KB entry:', e);
    }
  };

  const handleUpdate = async (entryId: string, data: any) => {
    if (!projectId) return;
    try {
      const api = await getApi();
      await api.updateKBEntry(projectId, entryId, data);
      loadKB();
    } catch (e) {
      console.error('Failed to update KB entry:', e);
    }
  };

  const handleExport = async () => {
    if (!projectId) return;
    try {
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
    } catch (e) {
      console.error('Failed to export KB:', e);
    }
  };

  const handleImportSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!projectId || !e.target.files?.[0]) return;
    setImportError(null);
    setImportResult(null);

    const file = e.target.files[0];
    try {
      const arrayBuffer = await file.arrayBuffer();
      const XLSX = await import('xlsx');
      const workbook = XLSX.read(arrayBuffer, { type: 'array' });
      const sheetName = workbook.SheetNames[0];
      const sheet = workbook.Sheets[sheetName];
      const jsonData = XLSX.utils.sheet_to_json<Record<string, string>>(sheet, { defval: '' });

      const columns = jsonData.length > 0 ? Object.keys(jsonData[0]) : [];

      // Validar colunas obrigatórias
      const requiredAliases: Record<string, string[]> = {
        'Descrição': ['Descrição', 'Descricao', 'description'],
        'N1': ['N1'],
        'N2': ['N2'],
        'N3': ['N3'],
        'N4': ['N4'],
      };

      const missing: string[] = [];
      for (const [label, aliases] of Object.entries(requiredAliases)) {
        if (!aliases.some(a => columns.includes(a))) {
          missing.push(label);
        }
      }

      if (missing.length > 0) {
        setImportError(`Colunas obrigatórias não encontradas: ${missing.join(', ')}. Colunas detectadas: ${columns.join(', ')}`);
        e.target.value = '';
        return;
      }

      // Converter para base64
      const b64 = btoa(
        new Uint8Array(arrayBuffer).reduce((data, byte) => data + String.fromCharCode(byte), '')
      );

      setImportPreview({
        rows: jsonData.slice(0, 5),
        totalRows: jsonData.length,
        columns,
        file,
        b64,
      });
    } catch (err: any) {
      setImportError(err.message || 'Erro ao ler o arquivo');
    } finally {
      e.target.value = '';
    }
  };

  const handleImportConfirm = async () => {
    if (!projectId || !importPreview) return;
    setIsImporting(true);
    setImportError(null);
    try {
      const api = await getApi();
      const result = await api.importKB(projectId, importPreview.b64);
      setImportResult(result);
      setImportPreview(null);
      await loadKB();
      await loadCoverage();
    } catch (err: any) {
      setImportError(err.message || 'Erro ao importar');
    } finally {
      setIsImporting(false);
    }
  };

  const handleImportCancel = () => {
    setImportPreview(null);
    setImportError(null);
  };

  const handleRollback = async (versionId: string) => {
    if (!projectId) return;
    if (!confirm(`Reverter para a versao ${versionId}? As entradas atuais serao substituidas.`)) return;
    try {
      const api = await getApi();
      await api.rollbackKB(projectId, versionId);
      await loadKB();
      setShowVersions(false);
    } catch (e) {
      console.error('Failed to rollback KB:', e);
    }
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
              <input type="file" accept=".xlsx" onChange={handleImportSelect} className="hidden" disabled={isImporting} />
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

        {/* Import preview */}
        {importPreview && (
          <div className="mb-3 border border-accent-200 rounded-xl overflow-hidden bg-accent-50/30">
            <div className="px-3 py-2 bg-accent-50 border-b border-accent-100 flex items-center justify-between">
              <span className="text-xs font-medium text-accent-700">
                Preview: {importPreview.file.name} ({importPreview.totalRows} linhas)
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleImportCancel}
                  className="text-xs px-2.5 py-1 border border-gray-200 text-gray-500 hover:bg-gray-50 rounded-lg transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleImportConfirm}
                  disabled={isImporting}
                  className="text-xs px-2.5 py-1 bg-accent-500 text-white hover:bg-accent-600 rounded-lg transition-colors disabled:opacity-50"
                >
                  {isImporting ? 'Importando...' : `Confirmar Importação (${importPreview.totalRows})`}
                </button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100">
                    {importPreview.columns.slice(0, 7).map(col => (
                      <th key={col} className="px-2 py-1.5 text-left font-medium text-gray-500 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {importPreview.rows.map((row, i) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                      {importPreview.columns.slice(0, 7).map(col => (
                        <td key={col} className="px-2 py-1.5 text-gray-700 whitespace-nowrap max-w-[200px] truncate">
                          {String(row[col] ?? '')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {importPreview.totalRows > 5 && (
                <p className="text-[10px] text-gray-400 px-2 py-1 text-center">
                  ... e mais {importPreview.totalRows - 5} linhas
                </p>
              )}
            </div>
          </div>
        )}

        {/* Import result feedback */}
        {importResult && (
          <div className="mb-3 rounded-lg bg-mint-50 border border-mint-200 px-3 py-2 text-sm text-mint-700 flex items-center justify-between">
            <span>{importResult.added} entradas adicionadas. Total na base: {importResult.total}</span>
            <button onClick={() => setImportResult(null)} className="text-mint-500 hover:text-mint-700 ml-2">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
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
                <p className="text-xs text-gray-400 text-center py-6">Nenhuma versão salva ainda.</p>
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
