import React from 'react'

interface ModelViewerOverlayProps {
  sector: string
  modelHistory: Array<{
    version_id: string
    timestamp: string
    filename: string
    status?: string
    metrics: { accuracy: number; f1_macro?: number }
  }>
  onClose: () => void
  onRestoreModel: (versionId: string) => void
  onRefresh: () => void
}

export default function ModelViewerOverlay({
  modelHistory,
  onClose,
  onRestoreModel,
}: ModelViewerOverlayProps) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800">Versões do Modelo</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="space-y-2">
          {modelHistory.map((entry) => (
            <div key={entry.version_id} className="flex items-center justify-between p-3 border rounded-lg">
              <div>
                <p className="text-sm font-medium">{entry.version_id}</p>
                <p className="text-xs text-gray-500">{new Date(entry.timestamp).toLocaleDateString('pt-BR')}</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-accent-500">{(entry.metrics.accuracy * 100).toFixed(1)}%</span>
                <button
                  onClick={() => onRestoreModel(entry.version_id)}
                  className="text-xs px-3 py-1 bg-accent-500 text-white rounded-lg hover:bg-accent-600"
                >
                  Restaurar
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
