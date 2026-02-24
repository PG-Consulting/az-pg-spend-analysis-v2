import React from 'react';
import type { ReviewFilter } from '../../lib/types';

interface ReviewFiltersProps {
  activeFilter: ReviewFilter;
  onFilterChange: (filter: ReviewFilter) => void;
  counts: Record<ReviewFilter, number>;
}

const FILTER_LABELS: Record<ReviewFilter, string> = {
  all: 'Todos',
  needs_attention: '⚠️ Atenção',
  low_confidence: 'Baixa Conf.',
  corrected: '✏️ Editados',
  approved: '✓ Aprovados',
  rejected: '✗ Rejeitados',
  pending: 'Pendentes',
};

const FILTER_COLORS: Record<ReviewFilter, string> = {
  all: 'bg-gray-800 text-white',
  needs_attention: 'bg-orange-600 text-white',
  low_confidence: 'bg-yellow-600 text-white',
  corrected: 'bg-[#0693e3] text-white',
  approved: 'bg-green-600 text-white',
  rejected: 'bg-red-600 text-white',
  pending: 'bg-gray-500 text-white',
};

const FILTER_INACTIVE: Record<ReviewFilter, string> = {
  all: 'text-gray-600 hover:bg-gray-100',
  needs_attention: 'text-orange-600 hover:bg-orange-50',
  low_confidence: 'text-yellow-600 hover:bg-yellow-50',
  corrected: 'text-[#0693e3] hover:bg-[#eff8ff]',
  approved: 'text-green-600 hover:bg-green-50',
  rejected: 'text-red-600 hover:bg-red-50',
  pending: 'text-gray-600 hover:bg-gray-100',
};

export function ReviewFilters({ activeFilter, onFilterChange, counts }: ReviewFiltersProps) {
  const filters: ReviewFilter[] = ['all', 'pending', 'needs_attention', 'low_confidence', 'corrected', 'approved', 'rejected'];

  return (
    <div className="flex flex-wrap gap-2">
      {filters.map(f => (
        <button
          key={f}
          onClick={() => onFilterChange(f)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
            activeFilter === f ? FILTER_COLORS[f] : `bg-transparent border border-gray-200 ${FILTER_INACTIVE[f]}`
          }`}
        >
          {FILTER_LABELS[f]}
          <span className={`px-1.5 py-0.5 rounded-full text-xs ${activeFilter === f ? 'bg-white/20' : 'bg-gray-100 text-gray-500'}`}>
            {counts[f] || 0}
          </span>
        </button>
      ))}
    </div>
  );
}
