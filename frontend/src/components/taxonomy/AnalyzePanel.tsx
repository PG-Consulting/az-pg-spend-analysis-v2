import React from 'react';
import type { TaxonomySession } from '../../lib/types';
import DownloadCard from './DownloadCard';
import { ChatLocked } from '../chat/ChatLocked';

interface AnalyzePanelProps {
  session: TaxonomySession | null;
  reviewCompleted: boolean;
  copilotPanel?: React.ReactNode;
}

export function AnalyzePanel({ session, reviewCompleted, copilotPanel }: AnalyzePanelProps) {
  if (!session) {
    return (
      <div className="text-center py-16 text-gray-400">
        <svg className="w-12 h-12 mx-auto mb-3 text-gray-200" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-sm text-gray-500">Nenhuma sessão ativa.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Download section - approved file takes priority */}
      {session.approvedFileContentBase64 && session.approvedDownloadFilename && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">Download dos Dados Revisados</h3>
          <DownloadCard
            downloadFilename={session.approvedDownloadFilename}
            fileContentBase64={session.approvedFileContentBase64}
          />
        </div>
      )}

      {session.fileContentBase64 && session.downloadFilename && !session.approvedFileContentBase64 && (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">Download</h3>
          <DownloadCard
            downloadFilename={session.downloadFilename}
            fileContentBase64={session.fileContentBase64}
          />
        </div>
      )}

      {/* Review summary if completed */}
      {session.reviewSummary && reviewCompleted && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-green-800 mb-3">Revisão Concluída</h3>
          <div className="grid grid-cols-4 gap-3 text-center">
            {[
              { label: 'Total', value: session.reviewSummary.total, color: 'text-gray-700' },
              { label: 'Aprovados', value: session.reviewSummary.approved, color: 'text-green-700' },
              { label: 'Editados', value: session.reviewSummary.edited, color: 'text-[#0693e3]' },
              { label: 'Rejeitados', value: session.reviewSummary.rejected, color: 'text-red-600' },
            ].map(stat => (
              <div key={stat.label} className="bg-white rounded-lg p-2">
                <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
                <div className="text-xs text-gray-500">{stat.label}</div>
              </div>
            ))}
          </div>
          {session.reviewSummary.kb_added > 0 && (
            <p className="text-xs text-green-600 mt-2">
              +{session.reviewSummary.kb_added} exemplos adicionados a Base de Conhecimento
            </p>
          )}
        </div>
      )}

      {/* Copilot section */}
      <div>
        <h3 className="text-sm font-medium text-gray-700 mb-3">Análise Conversacional</h3>
        {reviewCompleted ? (
          copilotPanel || <p className="text-sm text-gray-400 text-center py-8">Copilot não configurado.</p>
        ) : (
          <div className="border border-gray-100 rounded-xl overflow-hidden">
            <ChatLocked reason="Complete a revisão humana para desbloquear a análise conversacional com o Copilot." />
          </div>
        )}
      </div>
    </div>
  );
}
