import React, { useState } from 'react';
import { Modal } from '../ui/Modal';
import type { Sector, Project } from '../../lib/types';

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
  sectors: Sector[];
  onCreateSector: (data: { name: string; display_name: string }) => Promise<Sector>;
  existingProjects: Project[];
  createProject: (data: any) => Promise<Project>;
}

type Step = 'basic' | 'hierarchy';

const STEPS: Step[] = ['basic', 'hierarchy'];

const STEP_LABELS: Record<Step, string> = {
  basic: 'Básico',
  hierarchy: 'Hierarquia',
};

export function CreateProjectModal({
  isOpen,
  onClose,
  onCreated,
  sectors,
  onCreateSector,
  existingProjects,
  createProject,
}: CreateProjectModalProps) {
  const [step, setStep] = useState<Step>('basic');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Basic info
  const [displayName, setDisplayName] = useState('');
  const [selectedSector, setSelectedSector] = useState('');
  const [newSectorDisplay, setNewSectorDisplay] = useState('');
  // slug gerado automaticamente a partir do display name
  const newSectorName = newSectorDisplay
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  const [isNewSector, setIsNewSector] = useState(false);
  const [clientContext, setClientContext] = useState('');
  const [useSectorKb, setUseSectorKb] = useState(true);

  // Step 2: Hierarchy
  const [hierarchyOption, setHierarchyOption] = useState<'none' | 'upload'>('none');
  const [hierarchyFile, setHierarchyFile] = useState<File | null>(null);

  const handleClose = () => {
    // Reset form
    setStep('basic');
    setDisplayName('');
    setSelectedSector('');
    setNewSectorDisplay('');
    setIsNewSector(false);
    setClientContext('');
    setUseSectorKb(true);
    setHierarchyOption('none');
    setHierarchyFile(null);
    setError(null);
    onClose();
  };

  const handleCreate = async () => {
    setLoading(true);
    setError(null);
    try {
      let sectorName = selectedSector;

      // Create new sector if needed
      if (isNewSector && newSectorName && newSectorDisplay) {
        const sector = await onCreateSector({ name: newSectorName, display_name: newSectorDisplay });
        sectorName = sector.name;
      }

      // Read hierarchy file if provided
      let hierarchyBase64: string | null = null;
      let hierarchyFilename: string | null = null;
      if (hierarchyOption === 'upload' && hierarchyFile) {
        hierarchyBase64 = await fileToBase64(hierarchyFile);
        hierarchyFilename = hierarchyFile.name;
      }

      const hierarchySourceMap: Record<string, string> = {
        upload: 'own',
        none: 'padrao',
      };

      const project = await createProject({
        display_name: displayName,
        sector: sectorName,
        client_context: clientContext,
        hierarchy_file_base64: hierarchyBase64,
        hierarchy_filename: hierarchyFilename,
        hierarchy_source: hierarchySourceMap[hierarchyOption] || 'padrao',
        use_sector_kb: useSectorKb,
      });

      onCreated(project);
      handleClose();
    } catch (e: any) {
      setError(e.message || 'Erro ao criar projeto');
    } finally {
      setLoading(false);
    }
  };

  const canProceedBasic =
    displayName.trim() &&
    ((isNewSector && newSectorName && newSectorDisplay) || (!isNewSector && selectedSector));

  const currentStepIndex = STEPS.indexOf(step);

  const handleNext = () => {
    if (step === 'hierarchy') {
      handleCreate();
    } else {
      setStep(STEPS[currentStepIndex + 1]);
    }
  };

  const handleBack = () => {
    if (step === 'basic') {
      handleClose();
    } else {
      setStep(STEPS[currentStepIndex - 1]);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Criar Novo Projeto" size="lg">
      {/* Step indicator */}
      <div className="flex items-center gap-2 mb-6">
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <div
              className={`flex items-center gap-1.5 text-xs font-medium ${
                step === s
                  ? 'text-accent-500'
                  : i < currentStepIndex
                  ? 'text-mint-500'
                  : 'text-gray-400'
              }`}
            >
              <div
                className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  step === s
                    ? 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0] text-white'
                    : i < currentStepIndex
                    ? 'bg-mint-500 text-white'
                    : 'bg-gray-200 text-gray-500'
                }`}
              >
                {i + 1}
              </div>
              {STEP_LABELS[s]}
            </div>
            {i < STEPS.length - 1 && <div className="flex-1 h-px bg-gray-200" />}
          </React.Fragment>
        ))}
      </div>

      {/* Step 1: Basic */}
      {step === 'basic' && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Nome do Projeto *
            </label>
            <input
              type="text"
              value={displayName}
              onChange={e => setDisplayName(e.target.value)}
              placeholder="Ex: Naval - WARTSILÄ"
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:border-[#0693e3]"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Setor *</label>
            <div className="space-y-2">
              <div className="flex gap-2">
                <button
                  onClick={() => setIsNewSector(false)}
                  className={`flex-1 py-2 text-xs rounded-lg border transition-colors ${
                    !isNewSector
                      ? 'border-[#0693e3] bg-[#eff8ff] text-[#045d94]'
                      : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  Setor existente
                </button>
                <button
                  onClick={() => setIsNewSector(true)}
                  className={`flex-1 py-2 text-xs rounded-lg border transition-colors ${
                    isNewSector
                      ? 'border-[#0693e3] bg-[#eff8ff] text-[#045d94]'
                      : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  Criar novo setor
                </button>
              </div>

              {!isNewSector ? (
                <select
                  value={selectedSector}
                  onChange={e => setSelectedSector(e.target.value)}
                  className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:border-[#0693e3]"
                >
                  <option value="">Selecionar setor...</option>
                  {sectors.map(s => (
                    <option key={s.name} value={s.name}>
                      {s.display_name}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="space-y-1">
                  <input
                    value={newSectorDisplay}
                    onChange={e => setNewSectorDisplay(e.target.value)}
                    placeholder="Ex: Naval, Saúde, Mineração..."
                    className="w-full border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:border-[#0693e3]"
                    autoFocus
                  />
                  {newSectorName && (
                    <p className="text-xs text-gray-400 pl-1">
                      ID interno: <span className="font-mono">{newSectorName}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Contexto do Cliente
            </label>
            <textarea
              value={clientContext}
              onChange={e => setClientContext(e.target.value)}
              rows={3}
              placeholder="Descreva o cliente e seu contexto para melhorar a classificação pelo LLM..."
              className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0693e3] resize-none"
            />
          </div>

          <label className="flex items-center justify-between p-3 rounded-xl border border-gray-200 cursor-pointer hover:bg-gray-50 transition-colors">
            <div>
              <div className="text-sm font-medium text-gray-700">Usar base de conhecimento do setor</div>
              <div className="text-xs text-gray-500 mt-0.5">
                Mescla automaticamente os exemplos do setor na classificação
              </div>
            </div>
            <div
              onClick={() => setUseSectorKb(!useSectorKb)}
              className={`relative w-10 h-5 rounded-full transition-colors cursor-pointer ${useSectorKb ? 'bg-[#14919b]' : 'bg-gray-300'}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${useSectorKb ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </div>
          </label>
        </div>
      )}

      {/* Step 2: Hierarchy */}
      {step === 'hierarchy' && (
        <div className="space-y-4">
          <p className="text-sm text-gray-600">
            Defina como a hierarquia de categorias sera usada neste projeto.
          </p>
          <div className="space-y-3">
            {(
              [
                {
                  value: 'upload',
                  label: 'Fazer upload de hierarquia própria',
                  desc: 'Excel com colunas N1, N2, N3, N4',
                },
                {
                  value: 'none',
                  label: 'Sem hierarquia (padrão UNSPSC)',
                  desc: 'O LLM usa a taxonomia UNSPSC geral',
                },
              ] as { value: 'upload' | 'none'; label: string; desc: string }[]
            ).map(opt => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  hierarchyOption === opt.value
                    ? 'border-[#0693e3] bg-[#eff8ff]'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="hierarchy"
                  value={opt.value}
                  checked={hierarchyOption === opt.value}
                  onChange={() => setHierarchyOption(opt.value)}
                  className="mt-0.5"
                />
                <div>
                  <div className="text-sm font-medium text-gray-900">{opt.label}</div>
                  <div className="text-xs text-gray-500">{opt.desc}</div>
                </div>
              </label>
            ))}
          </div>

          {hierarchyOption === 'upload' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Arquivo Excel da Hierarquia
              </label>
              <input
                type="file"
                accept=".xlsx,.xls"
                onChange={e => setHierarchyFile(e.target.files?.[0] || null)}
                className="w-full text-sm text-gray-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:bg-[#eff8ff] file:text-[#045d94] hover:file:bg-[#d9efff]"
              />
            </div>
          )}

          {/* Info note about sector KB inheritance */}
          <div className="rounded-lg bg-[#eff8ff]/50 border border-accent-200 px-3 py-2.5">
            <div className="flex items-start gap-2">
              <svg className="w-4 h-4 text-accent-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-xs text-[#045d94] leading-relaxed">
                Este projeto herdará automaticamente os exemplos da base de conhecimento do setor.
                Exemplos aprovados podem ser promovidos para o setor depois.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-4 rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Navigation buttons */}
      <div className="flex justify-between mt-6 pt-4 border-t border-gray-100">
        <button
          onClick={handleBack}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
        >
          {step === 'basic' ? 'Cancelar' : 'Voltar'}
        </button>
        <button
          onClick={handleNext}
          disabled={(step === 'basic' && !canProceedBasic) || loading}
          className="px-5 py-2 text-sm bg-gradient-to-r from-[#0693e3] to-[#9b51e0] text-white rounded-xl hover:from-[#0576b8] hover:to-[#7c3aed] disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
        >
          {loading ? 'Criando...' : step === 'hierarchy' ? 'Criar Projeto' : 'Proximo'}
        </button>
      </div>
    </Modal>
  );
}

// Helper: convert File to base64 string (without data: prefix)
async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
