import React, { useState, useEffect, useCallback } from 'react';
import type { ClassifiedItem, ReviewItemState, HierarchyEntry } from '../../lib/types';
import { useHierarchy } from '../../hooks/useHierarchy';
import { Badge, ConfidenceBadge } from '../ui/Badge';
import { getSourceLabel } from '../../lib/utils';

interface ItemDetailPanelProps {
  item: ClassifiedItem | null;
  itemState: ReviewItemState;
  hierarchy: HierarchyEntry[] | null;
  onApprove: (index: number) => void;
  onApproveWithEdit: (index: number, edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
  onReject: (index: number) => void;
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  // Bulk edit mode
  selectedItems?: ClassifiedItem[];
  onBulkEdit?: (edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
}

function BulkEditPanel({
  selectedItems,
  hierarchy,
  onBulkEdit,
}: {
  selectedItems: ClassifiedItem[];
  hierarchy: HierarchyEntry[] | null;
  onBulkEdit: (edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
}) {
  const { n1Options, getN2Options, getN3Options, getN4Options, hasHierarchy } = useHierarchy(hierarchy);

  const [n1, setN1] = useState('');
  const [n2, setN2] = useState('');
  const [n3, setN3] = useState('');
  const [n4, setN4] = useState('');
  const [contributeToKB, setContributeToKB] = useState(true);

  const handleN1Change = (val: string) => { setN1(val); setN2(''); setN3(''); setN4(''); };
  const handleN2Change = (val: string) => { setN2(val); setN3(''); setN4(''); };
  const handleN3Change = (val: string) => { setN3(val); setN4(''); };

  const n2Options = getN2Options(n1);
  const n3Options = getN3Options(n1, n2);
  const n4Options = getN4Options(n1, n2, n3);

  // Com hierarquia: exige todos os campos (N4 precisa ser válido no caminho)
  // Sem hierarquia (UNSPSC/aberto): permite edição parcial — campos vazios preservam original
  const canApply = hasHierarchy
    ? !!(n1 && n2 && n3 && n4)
    : !!(n1 || n2 || n3 || n4);
  const isPartial = !hasHierarchy && canApply && !(n1 && n2 && n3 && n4);

  const handleApply = () => {
    onBulkEdit({ N1: n1, N2: n2, N3: n3, N4: n4, contributeToKB });
    setN1(''); setN2(''); setN3(''); setN4('');
  };

  const selectClass = "w-full h-10 rounded-xl border border-gray-200 bg-white pl-3 pr-8 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors appearance-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";
  const inputClass = "w-full h-10 rounded-xl border border-gray-200 bg-white px-3 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";

  const renderField = (label: string, value: string, onChange: (v: string) => void, options: string[]) => (
    <div>
      <label className="block text-[11px] font-medium text-primary-400 uppercase tracking-wider mb-1.5">{label}</label>
      {hasHierarchy && options.length > 0 ? (
        <div className="relative">
          <select
            value={value}
            onChange={e => onChange(e.target.value)}
            className={selectClass}
          >
            <option value="">Selecionar...</option>
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
            <svg className="h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5.22 8.22a.75.75 0 011.06 0L10 11.94l3.72-3.72a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.22 9.28a.75.75 0 010-1.06z" clipRule="evenodd" />
            </svg>
          </div>
        </div>
      ) : (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          className={inputClass}
          placeholder={`${label}...`}
        />
      )}
    </div>
  );

  return (
    <div className="w-96 border-l border-gray-100 bg-white flex flex-col overflow-y-auto">
      <div className="p-5 space-y-5">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-accent-50 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-bold text-accent-600">{selectedItems.length}</span>
          </div>
          <div>
            <p className="text-sm font-medium text-[#32373c]">{selectedItems.length} itens selecionados</p>
            <p className="text-[11px] text-primary-400">Edição em massa</p>
          </div>
        </div>

        {/* Items preview */}
        <div className="max-h-32 overflow-y-auto space-y-1 rounded-xl bg-gray-50 p-3 border border-gray-100">
          {selectedItems.slice(0, 5).map(item => (
            <p key={item.index} className="text-xs text-primary-600 truncate" title={item.description}>
              {item.description}
            </p>
          ))}
          {selectedItems.length > 5 && (
            <p className="text-xs text-primary-400 italic">
              +{selectedItems.length - 5} itens...
            </p>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* N1-N4 Cascading Dropdowns */}
        <div className="space-y-3">
          <p className="text-[11px] font-medium text-primary-400 uppercase tracking-wider">Nova classificação</p>
          {renderField('N1', n1, handleN1Change, n1Options)}
          {renderField('N2', n2, handleN2Change, n2Options)}
          {renderField('N3', n3, handleN3Change, n3Options)}
          {renderField('N4', n4, setN4, n4Options)}
        </div>

        {/* Contribute to KB */}
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={contributeToKB}
            onChange={e => setContributeToKB(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25"
          />
          <span className="text-sm text-primary-600 group-hover:text-[#32373c] transition-colors">
            Contribuir para Base de Conhecimento
          </span>
        </label>

        {/* Hint for partial edit */}
        {isPartial && (
          <p className="text-[11px] text-primary-400 italic">
            Campos vazios mantêm o valor original de cada item.
          </p>
        )}

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* Apply button */}
        <button
          onClick={handleApply}
          disabled={!canApply}
          className="w-full py-2.5 px-4 rounded-xl text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed bg-accent-500 text-white hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-500/25 focus:ring-offset-1"
        >
          Aplicar para {selectedItems.length} itens
        </button>
      </div>
    </div>
  );
}

export function ItemDetailPanel({
  item,
  itemState,
  hierarchy,
  onApprove,
  onApproveWithEdit,
  onReject,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
  selectedItems,
  onBulkEdit,
}: ItemDetailPanelProps) {
  const { n1Options, getN2Options, getN3Options, getN4Options, hasHierarchy } = useHierarchy(hierarchy);

  const [n1, setN1] = useState('');
  const [n2, setN2] = useState('');
  const [n3, setN3] = useState('');
  const [n4, setN4] = useState('');
  const [contributeToKB, setContributeToKB] = useState(true);

  // Sync form state when item changes
  useEffect(() => {
    if (item) {
      const editedN1 = itemState.editedN1 || item.N1;
      const editedN2 = itemState.editedN2 || item.N2;
      const editedN3 = itemState.editedN3 || item.N3;
      const editedN4 = itemState.editedN4 || item.N4;
      setN1(editedN1);
      setN2(editedN2);
      setN3(editedN3);
      setN4(editedN4);
      setContributeToKB(itemState.contributeToKB ?? true);
    }
  }, [item, itemState]);

  // Reset downstream when parent changes
  const handleN1Change = (val: string) => { setN1(val); setN2(''); setN3(''); setN4(''); };
  const handleN2Change = (val: string) => { setN2(val); setN3(''); setN4(''); };
  const handleN3Change = (val: string) => { setN3(val); setN4(''); };

  const n2Options = getN2Options(n1);
  const n3Options = getN3Options(n1, n2);
  const n4Options = getN4Options(n1, n2, n3);

  const hasEdits = item && (n1 !== item.N1 || n2 !== item.N2 || n3 !== item.N3 || n4 !== item.N4);
  const canApprove = n1 && n2 && n3 && n4;

  const decision = itemState.decision || 'pending';
  const isDecided = decision !== 'pending';

  const handleApprove = useCallback(() => {
    if (!item) return;
    if (hasEdits && canApprove) {
      onApproveWithEdit(item.index, { N1: n1, N2: n2, N3: n3, N4: n4, contributeToKB });
    } else {
      onApprove(item.index);
    }
  }, [item, hasEdits, canApprove, n1, n2, n3, n4, contributeToKB, onApprove, onApproveWithEdit]);

  // Keyboard shortcuts
  useEffect(() => {
    if (!item) return;
    const handler = (e: KeyboardEvent) => {
      // Skip if user is typing in an input/select/textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      if (e.key === 'ArrowUp') {
        e.preventDefault();
        onPrev?.();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        onNext?.();
      } else if (e.key === 'Enter' && !e.shiftKey && !isDecided) {
        e.preventDefault();
        handleApprove();
      } else if (e.key === 'Enter' && e.shiftKey && !isDecided) {
        e.preventDefault();
        if (item && canApprove) {
          setContributeToKB(true);
          if (hasEdits) {
            onApproveWithEdit(item.index, { N1: n1, N2: n2, N3: n3, N4: n4, contributeToKB: true });
          } else {
            onApprove(item.index);
          }
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [item, isDecided, handleApprove, onPrev, onNext, canApprove, hasEdits, n1, n2, n3, n4, onApprove, onApproveWithEdit]);

  // Bulk edit mode — takes priority over single item view
  if (selectedItems && selectedItems.length > 1 && onBulkEdit) {
    return (
      <BulkEditPanel
        key={selectedItems.map(i => i.index).join(',')}
        selectedItems={selectedItems}
        hierarchy={hierarchy}
        onBulkEdit={onBulkEdit}
      />
    );
  }

  // Empty state
  if (!item) {
    return (
      <div className="w-96 border-l border-gray-100 bg-white flex flex-col items-center justify-center">
        <div className="text-center px-8">
          <div className="w-12 h-12 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <p className="text-sm text-primary-400">Selecione um item na tabela para ver detalhes</p>
        </div>
      </div>
    );
  }

  const sourceLabel = getSourceLabel(item.source);
  const isKB = sourceLabel === 'Base de Aprendizado';
  const isAI = sourceLabel === 'Grok';

  const selectClass = "w-full h-10 rounded-xl border border-gray-200 bg-white pl-3 pr-8 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors appearance-none focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";
  const inputClass = "w-full h-10 rounded-xl border border-gray-200 bg-white px-3 text-sm shadow-[0_2px_8px_rgba(28,9,87,0.04)] transition-colors focus:ring-2 focus:ring-[#0693e3]/20 focus:border-[#0693e3] focus:outline-none";

  const renderField = (label: string, value: string, onChange: (v: string) => void, options: string[]) => (
    <div>
      <label className="block text-[11px] font-medium text-primary-400 uppercase tracking-wider mb-1.5">{label}</label>
      {hasHierarchy && options.length > 0 ? (
        <div className="relative">
          <select
            value={value}
            onChange={e => onChange(e.target.value)}
            className={selectClass}
            disabled={isDecided}
          >
            <option value="">Selecionar...</option>
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none">
            <svg className="h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M5.22 8.22a.75.75 0 011.06 0L10 11.94l3.72-3.72a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.22 9.28a.75.75 0 010-1.06z" clipRule="evenodd" />
            </svg>
          </div>
        </div>
      ) : (
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          className={inputClass}
          placeholder={`${label}...`}
          disabled={isDecided}
        />
      )}
    </div>
  );

  const decisionBadge = () => {
    if (decision === 'approved') return <Badge variant="mint" dot>Aprovado</Badge>;
    if (decision === 'edited') return <Badge variant="accent" dot>Editado</Badge>;
    if (decision === 'rejected') return <Badge variant="danger" dot>Rejeitado</Badge>;
    return null;
  };

  return (
    <div className="w-96 border-l border-gray-100 bg-white flex flex-col overflow-y-auto">
      <div className="p-5 space-y-5 animate-fade-in" key={item.index}>
        {/* Description */}
        <div>
          <p className="text-[11px] font-medium text-primary-400 uppercase tracking-wider mb-1.5">Descrição</p>
          <p className="text-sm text-[#32373c] font-medium leading-relaxed">{item.description}</p>
        </div>

        {/* Source + Confidence */}
        <div className="flex items-center gap-2">
          <Badge variant={isKB ? 'accent' : isAI ? 'ai' : 'muted'} dot>
            {sourceLabel}
          </Badge>
          <ConfidenceBadge confidence={item.confidence} />
        </div>

        {/* Decision badge if already decided */}
        {isDecided && (
          <div className="flex items-center gap-2 py-2 px-3 rounded-xl bg-gray-50 border border-gray-100">
            {decisionBadge()}
            {itemState.instructionUsed && (
              <span className="text-xs text-primary-400 italic truncate" title={itemState.instructionUsed}>
                com instrução
              </span>
            )}
          </div>
        )}

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* N1-N4 Cascading Dropdowns */}
        <div className="space-y-3">
          <p className="text-[11px] font-medium text-primary-400 uppercase tracking-wider">Classificação</p>
          {renderField('N1', n1, handleN1Change, n1Options)}
          {renderField('N2', n2, handleN2Change, n2Options)}
          {renderField('N3', n3, handleN3Change, n3Options)}
          {renderField('N4', n4, setN4, n4Options)}
        </div>

        {/* Contribute to KB */}
        <label className="flex items-center gap-2.5 cursor-pointer group">
          <input
            type="checkbox"
            checked={contributeToKB}
            onChange={e => setContributeToKB(e.target.checked)}
            disabled={isDecided}
            className="w-4 h-4 rounded border-gray-300 text-accent-500 focus:ring-accent-500/25"
          />
          <span className="text-sm text-primary-600 group-hover:text-[#32373c] transition-colors">
            Contribuir para Base de Conhecimento
          </span>
        </label>

        {/* Divider */}
        <div className="border-t border-gray-100" />

        {/* Action buttons */}
        {!isDecided ? (
          <div className="space-y-2">
            <button
              onClick={handleApprove}
              disabled={!canApprove}
              className="w-full py-2.5 px-4 rounded-xl text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed bg-accent-500 text-white hover:bg-accent-600 focus:outline-none focus:ring-2 focus:ring-accent-500/25 focus:ring-offset-1"
            >
              {hasEdits ? 'Aprovar com Edição' : 'Aprovar'}
            </button>
            <button
              onClick={() => onReject(item.index)}
              className="w-full py-2.5 px-4 rounded-xl text-sm font-medium transition-all duration-150 border border-gray-200 text-primary-600 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-ai-400/25 focus:ring-offset-1 flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4 text-ai-400" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
              </svg>
              Reclassificar
            </button>
          </div>
        ) : (
          <div className="text-center">
            {decisionBadge()}
          </div>
        )}

        {/* Navigation */}
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={onPrev}
            disabled={!hasPrev}
            className="text-sm text-primary-400 hover:text-accent-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center gap-1"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Anterior
          </button>
          <button
            onClick={onNext}
            disabled={!hasNext}
            className="text-sm text-primary-400 hover:text-accent-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center gap-1"
          >
            Próximo
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>

        {/* Keyboard hint */}
        <p className="text-[11px] text-primary-300 text-center">
          <kbd className="px-1 py-0.5 bg-gray-50 rounded text-[10px] border border-gray-100">
            ↑↓
          </kbd>{' '}
          navegar{' '}
          <kbd className="px-1 py-0.5 bg-gray-50 rounded text-[10px] border border-gray-100">
            Enter
          </kbd>{' '}
          aprovar{' '}
          <kbd className="px-1 py-0.5 bg-gray-50 rounded text-[10px] border border-gray-100">
            Shift+Enter
          </kbd>{' '}
          aprovar + KB
        </p>
      </div>
    </div>
  );
}
