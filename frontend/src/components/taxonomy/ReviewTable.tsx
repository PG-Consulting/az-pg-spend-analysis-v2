import React, { useRef, useMemo } from 'react';
import type { ClassifiedItem, ReviewItemState } from '../../lib/types';
import { getSourceLabel } from '../../lib/utils';

const ROW_HEIGHT = 44;
const OVERSCAN = 10;

interface ReviewTableProps {
  items: ClassifiedItem[];
  getItemState: (index: number) => ReviewItemState;
  activeIndex: number | null;
  selectedIndices: Set<number>;
  extraColumns?: string[];
  onSelectItem: (index: number) => void;
  onToggleSelect: (index: number) => void;
  onApprove: (index: number) => void;
  searchQuery?: string;
  containerHeight?: number;
}

/** Highlights matching substring in text */
function HighlightText({ text, query }: { text: string; query?: string }) {
  if (!query || !query.trim()) {
    return <>{text}</>;
  }
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escapedQuery})`, 'gi');
  const parts = text.split(regex);
  return (
    <>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark key={i} className="bg-yellow-100 text-yellow-900 rounded-sm px-0.5">{part}</mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
  );
}

const DECISION_ICONS: Record<string, { icon: string; className: string }> = {
  approved: { icon: '\u2713', className: 'text-mint-500' },
  edited: { icon: '\u270E', className: 'text-accent-500' },
  rejected: { icon: '\u2715', className: 'text-red-400' },
  pending: { icon: '\u00B7', className: 'text-gray-300 text-lg' },
};

function getConfidenceBorderColor(confidence: number): string {
  if (confidence >= 0.7) return 'border-l-mint-200';
  if (confidence >= 0.45) return 'border-l-amber-200';
  return 'border-l-red-200';
}

export function ReviewTable({
  items,
  getItemState,
  activeIndex,
  selectedIndices,
  extraColumns = [],
  onSelectItem,
  onToggleSelect,
  onApprove,
  searchQuery,
  containerHeight = 600,
}: ReviewTableProps) {
  const extraColsTemplate = extraColumns.map(() => '140px').join(' ');
  const gridTemplate = extraColumns.length > 0
    ? `36px 1fr ${extraColsTemplate} 200px 48px`
    : '36px 1fr 200px 48px';
  const gridStyle = { gridTemplateColumns: gridTemplate };

  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = React.useState(0);

  const totalHeight = items.length * ROW_HEIGHT;

  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endIndex = Math.min(items.length - 1, Math.ceil((scrollTop + containerHeight) / ROW_HEIGHT) + OVERSCAN);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  };

  // Check if all filtered items are selected
  const allSelected = useMemo(
    () => items.length > 0 && items.every(i => selectedIndices.has(i.index)),
    [items, selectedIndices]
  );

  return (
    <div className="border border-gray-100 rounded-xl overflow-hidden bg-white flex-1 min-h-0 flex flex-col">
      {/* Header */}
      <div className="grid gap-0 px-3 py-2.5 bg-gray-50/80 border-b border-gray-100 flex-shrink-0" style={gridStyle}>
        <div className="flex items-center justify-center">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() => {
              // Toggle all visible items
              if (allSelected) {
                items.forEach(i => {
                  if (selectedIndices.has(i.index)) onToggleSelect(i.index);
                });
              } else {
                items.forEach(i => {
                  if (!selectedIndices.has(i.index)) onToggleSelect(i.index);
                });
              }
            }}
            className="w-3.5 h-3.5 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25 cursor-pointer"
          />
        </div>
        <div className="text-[11px] font-medium text-primary-400 uppercase tracking-wider flex items-center pl-2">
          Descrição
        </div>
        {extraColumns.map(col => (
          <div key={col} className="text-[11px] font-medium text-primary-400 uppercase tracking-wider flex items-center truncate">
            {col}
          </div>
        ))}
        <div className="text-[11px] font-medium text-primary-400 uppercase tracking-wider flex items-center">
          Classificação
        </div>
        <div className="text-[11px] font-medium text-primary-400 uppercase tracking-wider flex items-center justify-center">
          Status
        </div>
      </div>

      {/* Virtualized body */}
      <div
        ref={containerRef}
        style={{ height: containerHeight, overflowY: 'auto' }}
        onScroll={handleScroll}
        className="flex-1 min-h-0"
      >
        <div style={{ height: totalHeight, position: 'relative' }}>
          {items.slice(startIndex, endIndex + 1).map((item, relIdx) => {
            const absIdx = startIndex + relIdx;
            const state = getItemState(item.index);
            const decision = state.decision || 'pending';
            const isActive = activeIndex === item.index;
            const isSelected = selectedIndices.has(item.index);
            const confidenceBorder = getConfidenceBorderColor(item.confidence);
            const decisionInfo = DECISION_ICONS[decision];

            // Display N4 value (edited if applicable)
            const displayN4 = state.editedN4 || item.N4;
            const displaySource = getSourceLabel(item.source);

            return (
              <div
                key={item.index}
                style={{
                  position: 'absolute',
                  top: absIdx * ROW_HEIGHT,
                  width: '100%',
                  height: ROW_HEIGHT,
                  ...gridStyle,
                  display: 'grid',
                }}
                className={[
                  'gap-0 px-3 items-center cursor-pointer transition-colors duration-100 border-l-[3px] border-b border-b-gray-50',
                  confidenceBorder,
                  isActive
                    ? 'bg-accent-50 border-l-accent-500'
                    : isSelected
                      ? 'bg-accent-50/50'
                      : 'hover:bg-gray-50/60',
                  decision === 'rejected' ? 'opacity-50' : '',
                ].join(' ')}
                onClick={() => onSelectItem(item.index)}
              >
                {/* Checkbox */}
                <div
                  className="flex items-center justify-center"
                  onClick={e => { e.stopPropagation(); onToggleSelect(item.index); }}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => {}}
                    className="w-3.5 h-3.5 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25 cursor-pointer"
                  />
                </div>

                {/* Description */}
                <div className="text-sm text-[#32373c] truncate font-medium pl-2 pr-3" title={item.description}>
                  <HighlightText text={item.description} query={searchQuery} />
                </div>

                {/* Extra columns */}
                {extraColumns.map(col => (
                  <div key={col} className="text-xs text-primary-500 truncate pr-2" title={String((item as any)[col] || '')}>
                    {(item as any)[col] || <span className="text-gray-300">--</span>}
                  </div>
                ))}

                {/* Classification (N4 only) */}
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-xs text-primary-600 truncate" title={`${item.N1} > ${item.N2} > ${item.N3} > ${displayN4}`}>
                    {displayN4 || <span className="text-gray-300 italic">--</span>}
                  </span>
                  {displaySource === 'Base de Aprendizado' && (
                    <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-accent-400" title="KB" />
                  )}
                  {displaySource === 'Grok' && (
                    <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-ai-400" title="Grok" />
                  )}
                </div>

                {/* Status icon */}
                <div className="flex items-center justify-center">
                  <span className={`text-sm ${decisionInfo.className}`} title={decision}>
                    {decisionInfo.icon}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
