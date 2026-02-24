import React, { useState, useEffect } from 'react';
import { Modal } from '../ui/Modal';
import type { Project } from '../../lib/types';

interface EditProjectModalProps {
  isOpen: boolean;
  project: Project | null;
  onClose: () => void;
  onSave: (projectId: string, data: { display_name: string; client_context: string; use_sector_kb: boolean }) => Promise<void>;
}

export function EditProjectModal({ isOpen, project, onClose, onSave }: EditProjectModalProps) {
  const [displayName, setDisplayName] = useState('');
  const [clientContext, setClientContext] = useState('');
  const [useSectorKb, setUseSectorKb] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (project) {
      setDisplayName(project.display_name);
      setClientContext(project.client_context || '');
      setUseSectorKb(project.use_sector_kb ?? true);
      setError(null);
    }
  }, [project]);

  const handleSave = async () => {
    if (!project || !displayName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onSave(project.project_id, {
        display_name: displayName.trim(),
        client_context: clientContext.trim(),
        use_sector_kb: useSectorKb,
      });
      onClose();
    } catch (e: any) {
      setError(e.message || 'Erro ao salvar projeto');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Editar Projeto" size="md">
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
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Contexto do Cliente
          </label>
          <textarea
            value={clientContext}
            onChange={e => setClientContext(e.target.value)}
            rows={3}
            placeholder="Descreva o cliente e seu contexto para melhorar a classificação pelo LLM..."
            className="w-full border border-gray-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#0693e3]/25 focus:border-[#0693e3] resize-none"
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

        {project && (
          <div className="rounded-lg bg-gray-50 border border-gray-200 px-3 py-2 text-xs text-gray-500 space-y-1">
            <p><span className="font-medium text-gray-600">ID:</span> <span className="font-mono">{project.project_id}</span></p>
            <p><span className="font-medium text-gray-600">Setor:</span> {project.sector}</p>
            <p><span className="font-medium text-gray-600">Hierarquia:</span> {project.hierarchy_source === 'own' ? 'Própria' : project.hierarchy_source === 'inherited' ? 'Herdada do setor' : 'Padrão UNSPSC'}</p>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
        >
          Cancelar
        </button>
        <button
          onClick={handleSave}
          disabled={!displayName.trim() || loading}
          className="px-5 py-2 text-sm bg-accent-500 text-white rounded-xl hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors active:scale-[0.98]"
        >
          {loading ? 'Salvando...' : 'Salvar'}
        </button>
      </div>
    </Modal>
  );
}
