import React, { useState } from 'react';
import type { ClassifiedItem, HierarchyEntry } from '../../lib/types';
import { useHierarchy } from '../../hooks/useHierarchy';

interface InlineEditorProps {
  item: ClassifiedItem;
  onApproveWithEdit: (edits: { N1: string; N2: string; N3: string; N4: string; contributeToKB: boolean }) => void;
  onReject: () => void;
  onCancel: () => void;
  hierarchy: HierarchyEntry[] | null;
}

export function InlineEditor({ item, onApproveWithEdit, onReject, onCancel, hierarchy }: InlineEditorProps) {
  const { n1Options, getN2Options, getN3Options, getN4Options, hasHierarchy } = useHierarchy(hierarchy);

  const [n1, setN1] = useState(item.N1);
  const [n2, setN2] = useState(item.N2);
  const [n3, setN3] = useState(item.N3);
  const [n4, setN4] = useState(item.N4);
  const [contributeToKB, setContributeToKB] = useState(true);

  // Reset downstream when parent changes
  const handleN1Change = (val: string) => { setN1(val); setN2(''); setN3(''); setN4(''); };
  const handleN2Change = (val: string) => { setN2(val); setN3(''); setN4(''); };
  const handleN3Change = (val: string) => { setN3(val); setN4(''); };

  const n2Options = getN2Options(n1);
  const n3Options = getN3Options(n1, n2);
  const n4Options = getN4Options(n1, n2, n3);

  const canApprove = n1 && n2 && n3 && n4;

  const selectClass = "w-full border border-gray-200 rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#0693e3] focus:border-transparent";
  const inputClass = "w-full border border-gray-200 rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-[#0693e3] focus:border-transparent";

  // When no hierarchy, show text inputs
  const renderField = (label: string, value: string, onChange: (v: string) => void, options: string[]) => (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {hasHierarchy && options.length > 0 ? (
        <select value={value} onChange={e => onChange(e.target.value)} className={selectClass}>
          <option value="">Selecionar...</option>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input type="text" value={value} onChange={e => onChange(e.target.value)} className={inputClass} placeholder={`${label}...`} />
      )}
    </div>
  );

  return (
    <div className="bg-[#eff8ff]/50 border-t border-[#b3dfff] p-4 space-y-3">
      <div className="text-xs font-medium text-gray-600 mb-2">
        Editar classificação: <span className="text-gray-900">{item.description}</span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        {renderField('N1', n1, handleN1Change, n1Options)}
        {renderField('N2', n2, handleN2Change, n2Options)}
        {renderField('N3', n3, handleN3Change, n3Options)}
        {renderField('N4', n4, setN4, n4Options)}
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={`kb-${item.index}`}
          checked={contributeToKB}
          onChange={e => setContributeToKB(e.target.checked)}
          className="w-4 h-4 accent-[#0693e3]"
        />
        <label htmlFor={`kb-${item.index}`} className="text-xs text-gray-600 cursor-pointer">
          Contribuir para a Base de Conhecimento do projeto
        </label>
      </div>

      <div className="flex gap-2 justify-end pt-1">
        <button onClick={onCancel} className="px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
          Cancelar
        </button>
        <button onClick={onReject} className="px-3 py-1.5 text-xs bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
          Rejeitar
        </button>
        <button
          onClick={() => canApprove && onApproveWithEdit({ N1: n1, N2: n2, N3: n3, N4: n4, contributeToKB })}
          disabled={!canApprove}
          className="px-4 py-1.5 text-xs bg-[#0693e3] text-white rounded-lg hover:bg-[#0576b8] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Aprovar com Edição
        </button>
      </div>
    </div>
  );
}
