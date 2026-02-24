import React, { useState } from 'react';
import type { KBCoverage } from '../../lib/types';

interface KnowledgeCoverageProps {
  coverage: KBCoverage | null;
  loading?: boolean;
}

export function KnowledgeCoverage({ coverage, loading = false }: KnowledgeCoverageProps) {
  const [expanded, setExpanded] = useState(false);

  if (loading) {
    return (
      <div className="animate-pulse">
        <div className="h-5 bg-gray-100 rounded w-48" />
      </div>
    );
  }

  if (!coverage) return null;

  const { total_n4s, covered, pct, underserved, project_entries, sector_entries, merged_entries } = coverage;

  // No hierarchy configured
  if (total_n4s === 0) {
    return (
      <div className="flex items-center gap-2 text-xs text-gray-400">
        <svg className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>Cobertura indisponível (sem hierarquia configurada)</span>
      </div>
    );
  }

  const color = pct >= 80 ? 'green' : pct >= 50 ? 'yellow' : 'red';
  const colorClasses = {
    green: { bar: 'bg-green-500', text: 'text-green-700', pctBg: 'bg-green-50 text-green-700' },
    yellow: { bar: 'bg-yellow-500', text: 'text-yellow-700', pctBg: 'bg-yellow-50 text-yellow-700' },
    red: { bar: 'bg-red-500', text: 'text-red-700', pctBg: 'bg-red-50 text-red-700' },
  }[color];

  const hasMergedBreakdown = sector_entries != null && project_entries != null;

  return (
    <div>
      {/* Summary line - always visible, clickable to expand */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 group text-left"
      >
        <svg
          className={`w-3.5 h-3.5 text-gray-400 transition-transform flex-shrink-0 ${expanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        <span className="text-xs text-gray-600">
          Cobertura: {covered}/{total_n4s} N4s
        </span>
        <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${colorClasses.pctBg}`}>
          {pct.toFixed(0)}%
        </span>
        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`${colorClasses.bar} h-1.5 rounded-full transition-all duration-500`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="mt-3 ml-6 pl-3 border-l-2 border-gray-100 space-y-3">
          {hasMergedBreakdown && (sector_entries! > 0 || project_entries! > 0) && (
            <div className="flex items-center gap-3 text-xs text-gray-500">
              <span className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-[#0693e3]" />
                {sector_entries} do setor
              </span>
              <span>+</span>
              <span className="inline-flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                {project_entries} do projeto
              </span>
              <span>=</span>
              <span className="font-medium text-gray-700">{merged_entries} exemplos efetivos</span>
            </div>
          )}

          {underserved.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-2">
                Categorias sem exemplos suficientes ({underserved.length}):
              </p>
              <div className="flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                {underserved.map(n4 => (
                  <span key={n4} className="text-xs px-2 py-0.5 bg-gray-50 border border-gray-200 rounded-full text-gray-600 truncate max-w-[160px]" title={n4}>
                    {n4}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
