import React, { useState, useMemo, useCallback } from 'react';
import type { ClassifiedItem, HierarchyEntry, ReviewFilter } from '../../lib/types';
import { useReview } from '../../hooks/useReview';
import { ReviewTable } from './ReviewTable';
import { ItemDetailPanel } from './ItemDetailPanel';
import { RejectModal } from './RejectModal';
import { StickyFooter } from '../ui/StickyFooter';
import FilterDropdown from '../ui/FilterDropdown';

interface ReviewTabProps {
  sessionId: string;
  items: ClassifiedItem[];
  hierarchy: HierarchyEntry[] | null;
  jobId: string;
  projectId: string;
  onFinalizeReview: (decisions: Array<{
    index: number;
    description: string;
    decision: string;
    N1: string; N2: string; N3: string; N4: string;
    confidence: number;
    source: string;
    contribute_to_kb?: boolean;
    instruction_used?: string;
  }>) => Promise<void>;
  onReclassify: (items: ClassifiedItem[], instruction: string) => Promise<ClassifiedItem[]>;
  isApproving?: boolean;
}

export function ReviewTab({
  sessionId, items, hierarchy, jobId, projectId,
  onFinalizeReview, onReclassify, isApproving = false,
}: ReviewTabProps) {
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [itemsToReject, setItemsToReject] = useState<ClassifiedItem[]>([]);
  const [isReclassifying, setIsReclassifying] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [localItems, setLocalItems] = useState(items);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const {
    filteredItems, filter, setFilter, selectedIndices,
    progress, filterCounts, canFinalize, isLoading,
    approveItem, editItem, rejectItem, rejectItems, reclassifyItems, bulkApprove, bulkApproveHighConfidence,
    toggleSelection, toggleAll, finalizeReview, getItemState,
  } = useReview({
    sessionId,
    items: localItems,
    onComplete: async () => {
      const decisions = localItems.map(item => {
        const state = getItemState(item.index);
        return {
          index: item.index,
          description: item.description,
          decision: state.decision || 'approved',
          N1: state.editedN1 || item.N1,
          N2: state.editedN2 || item.N2,
          N3: state.editedN3 || item.N3,
          N4: state.editedN4 || item.N4,
          confidence: item.confidence,
          source: item.source,
          contribute_to_kb: state.contributeToKB,
          instruction_used: state.instructionUsed,
        };
      });
      await onFinalizeReview(decisions);
    },
  });

  // Apply search filtering on top of hook's filtered items
  const displayItems = useMemo(() => {
    if (!searchQuery.trim()) return filteredItems;
    const query = searchQuery.toLowerCase();
    return filteredItems.filter(item =>
      item.description.toLowerCase().includes(query) ||
      item.N4.toLowerCase().includes(query)
    );
  }, [filteredItems, searchQuery]);

  const highConfidenceCount = localItems.filter(
    i => i.confidence >= 0.7 && getItemState(i.index).decision === 'pending'
  ).length;

  // Active item for detail panel
  const activeItem = useMemo(
    () => activeIndex !== null ? localItems.find(i => i.index === activeIndex) ?? null : null,
    [activeIndex, localItems]
  );

  const activeItemState = useMemo(
    () => activeIndex !== null ? getItemState(activeIndex) : { decision: 'pending' as const },
    [activeIndex, getItemState]
  );

  // Navigation helpers
  const activeDisplayIdx = useMemo(
    () => activeIndex !== null ? displayItems.findIndex(i => i.index === activeIndex) : -1,
    [activeIndex, displayItems]
  );

  const navigatePrev = useCallback(() => {
    if (activeDisplayIdx > 0) {
      setActiveIndex(displayItems[activeDisplayIdx - 1].index);
    }
  }, [activeDisplayIdx, displayItems]);

  const navigateNext = useCallback(() => {
    if (activeDisplayIdx < displayItems.length - 1) {
      setActiveIndex(displayItems[activeDisplayIdx + 1].index);
    }
  }, [activeDisplayIdx, displayItems]);

  // Reject handlers
  const handleRejectSelected = () => {
    const selectedItems = localItems.filter(i => selectedIndices.has(i.index));
    setItemsToReject(selectedItems);
    setRejectModalOpen(true);
  };

  const handleRejectSingle = (index: number) => {
    const item = localItems.find(i => i.index === index);
    if (item) {
      setItemsToReject([item]);
      setRejectModalOpen(true);
    }
  };

  const handleReclassify = async (instruction: string) => {
    setIsReclassifying(true);
    try {
      const reclassified = await onReclassify(itemsToReject, instruction);
      setLocalItems(prev => prev.map(item => {
        const updated = reclassified.find(r => r.index === item.index);
        return updated || item;
      }));
      reclassifyItems(itemsToReject.map(i => i.index), instruction);
    } finally {
      setIsReclassifying(false);
    }
  };

  const handleDownloadAsIs = async () => {
    setIsDownloading(true);
    try {
      const api = await import('../../lib/api').then(m => m.apiClient);
      const result = await api.downloadJobExcel(jobId);
      const bytes = atob(result.file_content_base64);
      const arr = new Uint8Array(bytes.length);
      for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
      const blob = new Blob([arr], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = result.filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      console.error('Download failed:', e);
    } finally {
      setIsDownloading(false);
    }
  };

  // FilterDropdown options
  const filterOptions = useMemo(() => [
    { value: 'all', label: 'Todos', count: filterCounts.all },
    { value: 'pending', label: 'Pendentes', count: filterCounts.pending },
    { value: 'low_confidence', label: 'Baixa confiança', count: filterCounts.low_confidence },
    { separator: true, value: 'approved', label: 'Aprovados', count: filterCounts.approved },
    { value: 'corrected', label: 'Editados', count: filterCounts.corrected },
    { value: 'rejected', label: 'Rejeitados', count: filterCounts.rejected },
  ], [filterCounts]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-10 h-10 border-4 border-accent-100 border-t-accent-500 rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-primary-400">Carregando progresso salvo...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-0 h-full">
      {/* Left side: toolbar + table */}
      <div className="flex-1 min-w-0 flex flex-col">
        {/* Consolidated toolbar */}
        <div className="flex items-center gap-3 px-3 py-2.5 border-b border-gray-100 bg-white flex-shrink-0">
          {/* Left group: select all + filter + search */}
          <label className="flex items-center gap-2 cursor-pointer flex-shrink-0">
            <input
              type="checkbox"
              checked={selectedIndices.size === displayItems.length && displayItems.length > 0}
              onChange={toggleAll}
              className="w-3.5 h-3.5 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25"
            />
            <span className="text-xs text-primary-400">
              {selectedIndices.size > 0 ? `${selectedIndices.size}` : 'Todos'}
            </span>
          </label>

          <div className="h-5 w-px bg-gray-200 flex-shrink-0" />

          <FilterDropdown
            options={filterOptions}
            value={filter}
            onChange={(val) => setFilter(val as ReviewFilter)}
          />

          {/* Search input */}
          <div className="relative flex-1 max-w-xs">
            <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Buscar descrição..."
              className="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg bg-white placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500 transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-300 hover:text-gray-500 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          <button
            onClick={handleDownloadAsIs}
            disabled={isDownloading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-50 text-gray-600 border border-gray-200 hover:bg-gray-100 transition-colors disabled:opacity-50"
            title="Baixar Excel com resultado bruto da classificação"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {isDownloading ? 'Baixando...' : 'Baixar Excel'}
          </button>

          <div className="flex-1" />

          {/* Right group: bulk actions */}
          {selectedIndices.size > 0 && (
            <>
              <button
                onClick={() => bulkApprove(Array.from(selectedIndices))}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-mint-50 text-mint-600 border border-mint-200 hover:bg-mint-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Aprovar sel. ({selectedIndices.size})
              </button>
              <button
                onClick={handleRejectSelected}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                Rejeitar sel. ({selectedIndices.size})
              </button>
            </>
          )}

          {highConfidenceCount > 0 && selectedIndices.size === 0 && (
            <button
              onClick={bulkApproveHighConfidence}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-accent-50 text-accent-600 border border-accent-200 hover:bg-accent-100 transition-colors"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Aprovar alta conf. ({highConfidenceCount})
            </button>
          )}
        </div>

        {/* Progress bar (compact, inline) */}
        <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-50/50 border-b border-gray-50 flex-shrink-0">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden flex">
            {progress.total > 0 && (
              <>
                <div
                  className="h-full bg-mint-400 transition-all duration-500"
                  style={{ width: `${(progress.approved / progress.total) * 100}%` }}
                />
                <div
                  className="h-full bg-accent-400 transition-all duration-500"
                  style={{ width: `${(progress.edited / progress.total) * 100}%` }}
                />
                <div
                  className="h-full bg-red-300 transition-all duration-500"
                  style={{ width: `${(progress.rejected / progress.total) * 100}%` }}
                />
              </>
            )}
          </div>
          <span className="text-[11px] text-primary-400 font-medium tabular-nums flex-shrink-0">
            {progress.reviewed}/{progress.total}
          </span>
          <span className={`text-[11px] font-bold tabular-nums flex-shrink-0 ${progress.pct === 100 ? 'text-mint-500' : 'text-accent-500'}`}>
            {progress.pct}%
          </span>
        </div>

        {/* Table */}
        {displayItems.length > 0 ? (
          <ReviewTable
            items={displayItems}
            getItemState={getItemState}
            activeIndex={activeIndex}
            selectedIndices={selectedIndices}
            onSelectItem={(index) => setActiveIndex(index)}
            onToggleSelect={toggleSelection}
            onApprove={approveItem}
            searchQuery={searchQuery}
            containerHeight={500}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center py-12">
              <div className="w-12 h-12 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <p className="text-sm text-primary-400">
                {searchQuery ? 'Nenhum item encontrado para esta busca.' : 'Nenhum item encontrado para este filtro.'}
              </p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-xs text-accent-500 hover:underline mt-1"
                >
                  Limpar busca
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Right side: detail panel */}
      <ItemDetailPanel
        item={activeItem}
        itemState={activeItemState}
        hierarchy={hierarchy}
        onApprove={approveItem}
        onApproveWithEdit={(index, edits) => editItem(index, edits)}
        onReject={handleRejectSingle}
        onPrev={navigatePrev}
        onNext={navigateNext}
        hasPrev={activeDisplayIdx > 0}
        hasNext={activeDisplayIdx < displayItems.length - 1}
      />

      {/* Finalize sticky footer */}
      <StickyFooter visible={canFinalize}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-mint-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-[#32373c] font-medium">
              Todos os {progress.total.toLocaleString()} itens revisados.
            </span>
          </div>
          <button
            onClick={finalizeReview}
            disabled={!canFinalize || isApproving}
            className="px-6 py-2.5 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-[#2db17f] to-[#7bdcb5] hover:from-[#259e70] hover:to-[#6ad1aa] disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center gap-2 shadow-sm"
          >
            {isApproving ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Finalizando...
              </>
            ) : (
              <>
                Finalizar e Baixar Excel
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </>
            )}
          </button>
        </div>
      </StickyFooter>

      {/* Reject modal */}
      <RejectModal
        isOpen={rejectModalOpen}
        onClose={() => setRejectModalOpen(false)}
        items={itemsToReject}
        onReclassify={handleReclassify}
        onRejectOnly={(instruction) => rejectItems(itemsToReject.map(i => i.index), instruction)}
        isReclassifying={isReclassifying}
      />
    </div>
  );
}
