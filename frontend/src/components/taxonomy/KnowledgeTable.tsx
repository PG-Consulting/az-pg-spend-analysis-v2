import React, { useState } from 'react';
import type { KBEntry, KBPage } from '../../lib/types';

interface KnowledgeTableProps {
  kbPage: KBPage | null;
  entries?: KBEntry[];
  loading?: boolean;
  onPageChange: (page: number) => void;
  onDelete: (entryId: string) => void;
  onUpdate: (entryId: string, data: Partial<KBEntry>) => void;
  onSearch: (query: string) => void;
  searchQuery: string;
  selectable?: boolean;
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  showSectorEntries?: boolean;
  onToggleSectorEntries?: (show: boolean) => void;
  hasSectorKB?: boolean;
}

const ORIGIN_BADGES: Record<string, { label: string; color: string }> = {
  sector: { label: 'Setor', color: 'bg-[#eff8ff] text-[#045d94]' },
  project: { label: 'Projeto', color: 'bg-green-50 text-green-700' },
  both: { label: 'Projeto + Setor', color: 'bg-amber-50 text-amber-700' },
};

export function KnowledgeTable({
  kbPage,
  entries: entriesProp,
  loading,
  onPageChange,
  onDelete,
  onUpdate,
  onSearch,
  searchQuery,
  selectable = false,
  selectedIds,
  onSelectionChange,
  showSectorEntries,
  onToggleSectorEntries,
  hasSectorKB = false,
}: KnowledgeTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<Partial<KBEntry>>({});

  const displayEntries = entriesProp ?? kbPage?.entries ?? [];

  const handleStartEdit = (entry: KBEntry) => {
    setEditingId(entry.id);
    setEditData({ N1: entry.N1, N2: entry.N2, N3: entry.N3, N4: entry.N4 });
  };

  const handleSaveEdit = (entryId: string) => {
    onUpdate(entryId, editData);
    setEditingId(null);
    setEditData({});
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditData({});
  };

  const handleToggleSelect = (entryId: string) => {
    if (!onSelectionChange || !selectedIds) return;
    const next = new Set(selectedIds);
    if (next.has(entryId)) {
      next.delete(entryId);
    } else {
      next.add(entryId);
    }
    onSelectionChange(next);
  };

  const handleSelectAllProject = () => {
    if (!onSelectionChange) return;
    const projectEntryIds = displayEntries
      .filter(e => e._origin === 'project')
      .map(e => e.id);
    const allSelected = projectEntryIds.every(id => selectedIds?.has(id));
    if (allSelected) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(projectEntryIds));
    }
  };

  const editInputClass = "w-full border border-accent-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] transition-colors";

  return (
    <div className="space-y-3">
      {/* Sector entries toggle */}
      {hasSectorKB && onToggleSectorEntries && (
        <div className="flex items-center">
          <label className="flex items-center gap-2 text-xs text-gray-600 whitespace-nowrap cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showSectorEntries}
              onChange={e => onToggleSectorEntries(e.target.checked)}
              className="rounded border-gray-300 text-[#0693e3] focus:ring-[#0693e3]"
            />
            Mostrar entradas do setor
          </label>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="h-12 bg-gray-50 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : displayEntries.length === 0 ? (
        <div className="text-center py-12 text-gray-400 text-sm">
          {searchQuery ? `Nenhum resultado para "${searchQuery}"` : 'Nenhuma entrada na base de conhecimento ainda.'}
        </div>
      ) : (
        <>
          {/* Table */}
          <div className="border border-gray-100 rounded-xl overflow-hidden">
            <table className="w-full text-xs" style={{ tableLayout: 'fixed' }}>
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {selectable && (
                    <th className="px-2 py-2.5" style={{ width: 32 }}>
                      <input
                        type="checkbox"
                        onChange={handleSelectAllProject}
                        checked={
                          displayEntries.filter(e => e._origin === 'project').length > 0 &&
                          displayEntries.filter(e => e._origin === 'project').every(e => selectedIds?.has(e.id))
                        }
                        className="rounded border-gray-300 text-[#0693e3] focus:ring-[#0693e3]"
                      />
                    </th>
                  )}
                  <th className="text-left px-3 py-2.5 font-medium text-gray-500" style={{ width: '30%' }}>Descricao</th>
                  <th className="text-left px-2 py-2.5 font-medium text-gray-500" style={{ width: '13%' }}>N1</th>
                  <th className="text-left px-2 py-2.5 font-medium text-gray-500" style={{ width: '15%' }}>N2</th>
                  <th className="text-left px-2 py-2.5 font-medium text-gray-500" style={{ width: '15%' }}>N3</th>
                  <th className="text-left px-2 py-2.5 font-medium text-gray-500" style={{ width: '15%' }}>N4</th>
                  <th className="text-center px-2 py-2.5 font-medium text-gray-500" style={{ width: 72 }}>Acoes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {displayEntries.map(entry => {
                  const isEditing = editingId === entry.id;
                  const isSector = entry._origin === 'sector' || entry._origin === 'both';
                  const originInfo = entry._origin ? ORIGIN_BADGES[entry._origin] : null;

                  return (
                    <tr
                      key={entry.id}
                      className={`${
                        isEditing
                          ? 'bg-[#eff8ff]'
                          : isSector
                          ? 'bg-[#eff8ff]/30 hover:bg-[#eff8ff]/50'
                          : 'hover:bg-gray-50'
                      } transition-colors`}
                    >
                      {selectable && (
                        <td className="px-2 py-2.5">
                          {!isSector ? (
                            <input
                              type="checkbox"
                              checked={selectedIds?.has(entry.id) || false}
                              onChange={() => handleToggleSelect(entry.id)}
                              className="rounded border-gray-300 text-[#0693e3] focus:ring-[#0693e3]"
                            />
                          ) : (
                            <span className="block w-4" />
                          )}
                        </td>
                      )}
                      {/* Description */}
                      <td className="px-3 py-2.5 overflow-hidden">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-gray-900 text-xs" title={entry.description}>{entry.description}</span>
                          {originInfo && (
                            <span className={`flex-shrink-0 px-1.5 py-0.5 rounded-full text-[10px] leading-none ${originInfo.color}`}>
                              {originInfo.label}
                            </span>
                          )}
                        </div>
                      </td>
                      {/* N1 */}
                      <td className="px-2 py-2.5">
                        {isEditing ? (
                          <input
                            value={editData.N1 || ''}
                            onChange={e => setEditData(prev => ({ ...prev, N1: e.target.value }))}
                            placeholder="N1"
                            className={editInputClass}
                          />
                        ) : (
                          <span className="truncate block text-gray-600 text-xs" title={entry.N1}>{entry.N1 || '—'}</span>
                        )}
                      </td>
                      {/* N2 */}
                      <td className="px-2 py-2.5">
                        {isEditing ? (
                          <input
                            value={editData.N2 || ''}
                            onChange={e => setEditData(prev => ({ ...prev, N2: e.target.value }))}
                            placeholder="N2"
                            className={editInputClass}
                          />
                        ) : (
                          <span className="truncate block text-gray-600 text-xs" title={entry.N2}>{entry.N2 || '—'}</span>
                        )}
                      </td>
                      {/* N3 */}
                      <td className="px-2 py-2.5">
                        {isEditing ? (
                          <input
                            value={editData.N3 || ''}
                            onChange={e => setEditData(prev => ({ ...prev, N3: e.target.value }))}
                            placeholder="N3"
                            className={editInputClass}
                          />
                        ) : (
                          <span className="truncate block text-gray-600 text-xs" title={entry.N3}>{entry.N3 || '—'}</span>
                        )}
                      </td>
                      {/* N4 */}
                      <td className="px-2 py-2.5">
                        {isEditing ? (
                          <input
                            value={editData.N4 || ''}
                            onChange={e => setEditData(prev => ({ ...prev, N4: e.target.value }))}
                            placeholder="N4"
                            className={editInputClass}
                          />
                        ) : (
                          <span className="truncate block text-gray-700 text-xs font-medium" title={entry.N4}>{entry.N4 || '—'}</span>
                        )}
                      </td>
                      {/* Actions */}
                      <td className="px-2 py-2.5">
                        <div className="flex gap-1 justify-center">
                          {isEditing ? (
                            <>
                              <button onClick={() => handleSaveEdit(entry.id)} className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors" title="Salvar">
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                              </button>
                              <button onClick={handleCancelEdit} className="p-1.5 text-gray-400 hover:bg-gray-100 rounded-lg transition-colors" title="Cancelar">
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                              </button>
                            </>
                          ) : isSector ? (
                            <span className="text-[10px] text-gray-300 italic">somente leitura</span>
                          ) : (
                            <>
                              <button onClick={() => handleStartEdit(entry)} className="p-1.5 text-[#0693e3] hover:bg-[#eff8ff] rounded-lg transition-colors" title="Editar">
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                              </button>
                              <button onClick={() => onDelete(entry.id)} className="p-1.5 text-red-400 hover:bg-red-50 rounded-lg transition-colors" title="Excluir">
                                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {kbPage && kbPage.pages > 1 && (
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>{kbPage.total} entradas no total</span>
              <div className="flex gap-1">
                {Array.from({ length: Math.min(kbPage.pages, 7) }, (_, i) => {
                  const page = i + 1;
                  return (
                    <button
                      key={page}
                      onClick={() => onPageChange(page)}
                      className={`w-7 h-7 rounded-lg text-xs transition-colors ${kbPage.page === page ? 'bg-[#0693e3] text-white' : 'text-gray-600 hover:bg-gray-100'}`}
                    >
                      {page}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
