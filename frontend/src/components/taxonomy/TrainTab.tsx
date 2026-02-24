import React from 'react'
import FileUpload from '@/components/FileUpload'

interface ValidationCheck {
    label: string
    status: 'ok' | 'warning' | 'error'
    message: string
}

interface ValidationStatus {
    isValid: boolean
    score: number
    checks: ValidationCheck[]
}

interface TrainTabProps {
    sector: string
    trainingStep: 'upload' | 'preview' | 'training' | 'result'
    trainingFile: { file: File; content: string } | null
    previewData: any[]
    validationStatus: ValidationStatus | null
    trainingResult: any | null
    onFileSelect: (file: File, fileContent: string) => void
    onConfirmTraining: () => void
    onCancelTraining: () => void
}

export default function TrainTab({
    sector,
    trainingStep,
    trainingFile,
    previewData,
    validationStatus,
    trainingResult,
    onFileSelect,
    onConfirmTraining,
    onCancelTraining,
}: TrainTabProps) {
    return (
        <div className="animate-fadeIn">
            {/* STEP 1: UPLOAD */}
            {trainingStep === 'upload' && (
                <UploadStep sector={sector} onFileSelect={onFileSelect} />
            )}

            {/* STEP 2: PREVIEW & VALIDATE */}
            {trainingStep === 'preview' && validationStatus && (
                <PreviewStep
                    validationStatus={validationStatus}
                    previewData={previewData}
                    onConfirm={onConfirmTraining}
                    onCancel={onCancelTraining}
                />
            )}

            {/* STEP 3: TRAINING PROCESSING */}
            {trainingStep === 'training' && <TrainingStep />}

            {/* STEP 4: RESULT */}
            {trainingStep === 'result' && trainingResult && (
                <ResultStep
                    sector={sector}
                    trainingResult={trainingResult}
                    onTrainAnother={onCancelTraining}
                />
            )}
        </div>
    )
}

// Sub-components
function UploadStep({ sector, onFileSelect }: { sector: string; onFileSelect: (file: File, content: string) => void }) {
    return (
        <>
            <h2 className="text-lg font-semibold text-gray-800 mb-2 text-center">
                Consolidar Conhecimento do Consultor
            </h2>
            <p className="text-sm text-gray-500 mb-2 text-center max-w-sm mx-auto">
                Envie o arquivo final revisado/corrigido. O sistema usará estas correções para <strong>aprender suas regras de ouro</strong> e não cometer os mesmos erros novamente.
            </p>
            <div className="text-xs text-gray-500 bg-[#38a8f5]/10 border border-[#38a8f5]/30 rounded-lg p-3 mb-6 max-w-md mx-auto">
                <strong>Formato Obrigatório:</strong> O arquivo deve conter exatamente as colunas:
                <br />
                <code className="bg-white px-1 rounded border border-[#38a8f5]/30 text-[#0693e3]">Descrição</code>,
                <code className="bg-white px-1 rounded border border-[#38a8f5]/30 text-[#0693e3]">N1</code>,
                <code className="bg-white px-1 rounded border border-[#38a8f5]/30 text-[#0693e3]">N2</code>,
                <code className="bg-white px-1 rounded border border-[#38a8f5]/30 text-[#0693e3]">N3</code>,
                <code className="bg-white px-1 rounded border border-[#38a8f5]/30 text-[#0693e3]">N4</code>
            </div>
            <FileUpload onFileSelect={onFileSelect} disabled={false} />
        </>
    )
}

function PreviewStep({
    validationStatus,
    previewData,
    onConfirm,
    onCancel
}: {
    validationStatus: ValidationStatus
    previewData: any[]
    onConfirm: () => void
    onCancel: () => void
}) {
    const allChecksOk = validationStatus.checks.every(c => c.status === 'ok')
    const isFullyValid = validationStatus.isValid && allChecksOk

    return (
        <div className="space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                {/* Semantic Semaphore Header */}
                <div className={`px-4 py-3 flex items-center justify-between border-b ${isFullyValid
                    ? 'bg-gradient-to-r from-green-50 to-white border-green-100'
                    : 'bg-gradient-to-r from-red-50 to-white border-red-100'
                    }`}>
                    <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center shadow-sm shrink-0 ${isFullyValid ? 'bg-green-100' : 'bg-red-100'
                            }`}>
                            <div className={`w-5 h-5 rounded-full shadow-inner ${isFullyValid ? 'bg-green-500' : validationStatus.isValid ? 'bg-yellow-400' : 'bg-red-500'
                                }`}></div>
                        </div>
                        <div>
                            <h3 className={`text-base font-bold leading-tight ${isFullyValid ? 'text-green-800' : 'text-red-800'
                                }`}>
                                {isFullyValid ? 'Pronto para Refinar' : 'Atenção Necessária'}
                            </h3>
                            <p className="text-[10px] text-gray-500 uppercase tracking-wide font-medium">
                                Qualidade: {validationStatus.score}/100
                            </p>
                        </div>
                    </div>

                    <div className="flex gap-2">
                        <button
                            onClick={onCancel}
                            className="px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-100 rounded-md transition-colors border border-gray-200"
                        >
                            Cancelar
                        </button>
                        <button
                            onClick={onConfirm}
                            disabled={!isFullyValid}
                            className={`px-4 py-1.5 text-xs font-medium text-white rounded-lg transition-all shadow-sm ${isFullyValid
                                ? 'bg-[#0693e3] hover:bg-[#0576b8] hover:shadow hover:scale-[1.02]'
                                : 'bg-gray-300 cursor-not-allowed'
                                }`}
                        >
                            Confirmar
                        </button>
                    </div>
                </div>

                {/* Checks List */}
                <div className="p-3 bg-gray-50/50 grid grid-cols-1 md:grid-cols-2 gap-2">
                    {validationStatus.checks.map((check, idx) => (
                        <div key={idx} className={`flex items-start gap-2 p-2 rounded-lg border text-xs ${check.status === 'ok' ? 'bg-white border-green-100 text-gray-600' :
                            check.status === 'warning' ? 'bg-yellow-50 border-yellow-100 text-yellow-800' :
                                'bg-red-50 border-red-100 text-red-800'
                            }`}>
                            {check.status === 'ok' ? (
                                <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                </svg>
                            ) : check.status === 'warning' ? (
                                <svg className="w-4 h-4 text-yellow-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                            ) : (
                                <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            )}
                            <div>
                                <span className="font-semibold block mb-0.5">{check.label}</span>
                                <span className="opacity-90">{check.message}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Preview Table */}
            <div>
                <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Pré-visualização (Amostra)</h3>
                    <span className="text-xs text-gray-400">Primeiras 5 linhas</span>
                </div>
                <div className="overflow-x-auto border border-gray-200 rounded-lg shadow-sm">
                    <table className="min-w-full divide-y divide-gray-200 text-xs">
                        <thead className="bg-gray-50">
                            <tr>
                                {Object.keys(previewData[0] || {}).slice(0, 5).map((header) => (
                                    <th key={header} className="px-3 py-2 text-left font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">
                                        {header}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {previewData.slice(0, 5).map((row, idx) => (
                                <tr key={idx} className="hover:bg-gray-50 transition-colors">
                                    {Object.values(row).slice(0, 5).map((val: any, i) => (
                                        <td key={i} className="px-3 py-2 text-gray-700 whitespace-nowrap max-w-[200px] truncate" title={val?.toString()}>
                                            {val?.toString()}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    )
}

function TrainingStep() {
    return (
        <div className="mt-6 text-center">
            <div className="inline-block animate-spin rounded-full h-10 w-10 border-4 border-gray-200 border-t-[#0693e3]"></div>
            <p className="text-sm text-gray-600 mt-3 font-medium">Refinando inteligência com base nas suas correções (quase pronto)...</p>
        </div>
    )
}

function ResultStep({
    sector,
    trainingResult,
    onTrainAnother,
}: {
    sector: string
    trainingResult: any
    onTrainAnother: () => void
}) {
    return (
        <div className="text-center animate-fadeIn">
            <div className="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center mx-auto mb-4 border-4 border-white shadow-lg">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
            </div>
            <h3 className="text-xl font-bold text-gray-800 mb-2">Refino Concluído!</h3>
            <p className="text-sm text-gray-600 mb-6">
                {trainingResult?.message || `O modelo para ${sector} foi atualizado com sucesso.`}
            </p>

            <div className="flex flex-col gap-3">
                <button
                    onClick={onTrainAnother}
                    className="w-full px-4 py-3 bg-gradient-to-r from-[#38a8f5] to-[#0693e3] hover:from-[#7ac8ff] hover:to-[#38a8f5] text-white rounded-lg transition-all font-medium shadow-md hover:shadow-lg shadow-[#38a8f5]/20"
                >
                    Refinar Outro Setor
                </button>
            </div>
        </div>
    )
}
