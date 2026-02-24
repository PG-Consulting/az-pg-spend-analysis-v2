import React from 'react';

interface BulkActionBarProps {
  totalItems: number;
  selectedCount: number;
  filteredCount: number;
  onSelectAll: () => void;
  onApproveSelected: () => void;
  onRejectSelected: () => void;
  onApproveHighConfidence: () => void;
  highConfidenceCount: number;
}

export function BulkActionBar({
  totalItems,
  selectedCount,
  filteredCount,
  onSelectAll,
  onApproveSelected,
  onRejectSelected,
  onApproveHighConfidence,
  highConfidenceCount,
}: BulkActionBarProps) {
  const allSelected = selectedCount === filteredCount && filteredCount > 0;

  return (
    <div className="flex items-center gap-3 py-2 px-1">
      {/* Select all checkbox */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={allSelected}
          onChange={onSelectAll}
          className="w-4 h-4 rounded accent-[#0693e3]"
        />
        <span className="text-xs text-gray-500">
          {selectedCount > 0 ? `${selectedCount} selecionados` : 'Selecionar todos'}
        </span>
      </label>

      {selectedCount > 0 && (
        <>
          <div className="h-4 w-px bg-gray-300" />
          <button
            onClick={onApproveSelected}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-50 text-green-700 border border-green-200 rounded-lg hover:bg-green-100 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Aprovar ({selectedCount})
          </button>
          <button
            onClick={onRejectSelected}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            Rejeitar ({selectedCount})
          </button>
        </>
      )}

      <div className="flex-1" />

      {highConfidenceCount > 0 && (
        <button
          onClick={onApproveHighConfidence}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#eff8ff] text-[#045d94] border border-[#7ac8ff] rounded-lg hover:bg-[#b3dfff] transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Aprovar alta confiança ({highConfidenceCount})
        </button>
      )}
    </div>
  );
}
