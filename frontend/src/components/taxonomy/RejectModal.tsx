import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import Textarea from '../ui/Textarea';
import type { ClassifiedItem } from '../../lib/types';

interface RejectModalProps {
  isOpen: boolean;
  onClose: () => void;
  items: ClassifiedItem[];
  onReclassify: (instruction: string) => Promise<void>;
  onRejectOnly: (instruction?: string) => void;
  isReclassifying?: boolean;
}

export function RejectModal({ isOpen, onClose, items, onReclassify, onRejectOnly, isReclassifying = false }: RejectModalProps) {
  const [instruction, setInstruction] = useState('');

  const handleClose = () => {
    setInstruction('');
    onClose();
  };

  const handleReclassify = async () => {
    if (!instruction.trim()) return;
    await onReclassify(instruction.trim());
    handleClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Pedir nova classificação" size="lg">
      <div className="space-y-5">
        {/* Items preview */}
        <div className="bg-gray-50 rounded-xl p-3 max-h-32 overflow-y-auto space-y-1">
          {items.slice(0, 8).map((item, i) => (
            <div key={i} className="text-xs text-primary-600 truncate flex items-center gap-2">
              <span className="text-primary-300 font-mono w-5 text-right flex-shrink-0">{i + 1}.</span>
              <span className="truncate">{item.description}</span>
            </div>
          ))}
          {items.length > 8 && (
            <div className="text-xs text-primary-300 pl-7">... e mais {items.length - 8} item(s)</div>
          )}
        </div>

        {/* Instruction textarea (hero element) */}
        <Textarea
          label="Como estes itens devem ser classificados?"
          hint="Descreva a classificação correta para que a IA reclassifique automaticamente"
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          rows={6}
          placeholder={`Ex: "Estes itens são peças de motor e devem ir em N1: Manutenção / N2: Peças / N3: Motor Marítimo"\n\nOu: "Produtos de limpeza devem ser classificados como MRO - Facilities"`}
          className="[&_textarea]:min-h-[140px]"
        />

        {/* Info box when instruction is present */}
        {instruction.trim() && (
          <div className="rounded-xl bg-accent-50 border border-accent-100 px-4 py-3 text-sm text-accent-700 flex items-start gap-2.5">
            <svg className="w-4 h-4 text-accent-400 flex-shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
            </svg>
            <span>
              A IA irá reclassificar {items.length === 1 ? 'este item' : `estes ${items.length} itens`} usando sua instrução como guia prioritário.
            </span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-col items-stretch gap-3 mt-6 pt-5 border-t border-gray-100">
        {/* Primary action: Reclassify */}
        <button
          onClick={handleReclassify}
          disabled={!instruction.trim() || isReclassifying}
          className="w-full py-3 px-5 text-sm font-medium text-white rounded-xl bg-gradient-to-r from-[#0693e3] to-[#9b51e0] hover:from-[#0576b8] hover:to-[#7c3aed] disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center gap-2 shadow-sm"
        >
          {isReclassifying ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Reclassificando...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
              </svg>
              Reclassificar com IA
            </>
          )}
        </button>

        {/* Secondary: discard link */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleClose}
            className="text-sm text-primary-400 hover:text-primary-600 transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={() => { onRejectOnly(instruction.trim() || undefined); handleClose(); }}
            className="text-sm text-primary-400 hover:text-red-500 underline underline-offset-2 transition-colors"
          >
            Só descartar {items.length === 1 ? 'este item' : `estes ${items.length} itens`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
