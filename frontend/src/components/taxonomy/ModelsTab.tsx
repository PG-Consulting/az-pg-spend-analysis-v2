import React, { useState, useEffect } from 'react'
import ModelViewerOverlay from './ModelViewerOverlay'

interface ModelHistoryEntry {
    version_id: string
    timestamp: string
    filename: string
    status?: string
    metrics: {
        accuracy: number
        f1_macro?: number
    }
}

interface MemoryRule {
    id: string
    description: string
    classification: {
        N1: string
        N2: string
        N3: string
        N4: string
    }
    date_added: string
}

interface ModelsTabProps {
    sector: string
    modelHistory: ModelHistoryEntry[]
    isProcessing: boolean
    onRefresh: () => void
    onRestoreModel: (versionId: string) => void
}

export default function ModelsTab({
    sector,
    modelHistory,
    isProcessing,
    onRefresh,
    onRestoreModel
}: ModelsTabProps) {
    const [showOverlay, setShowOverlay] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')
    const [memoryRules, setMemoryRules] = useState<MemoryRule[]>([])
    const [isLoadingMemory, setIsLoadingMemory] = useState(false)

    const isPadrao = sector === 'Padrão' || sector === 'Padrao'

    // Fetch memory rules if Padrão
    useEffect(() => {
        if (isPadrao) {
            fetchMemory()
        }
    }, [isPadrao, sector])

    const fetchMemory = async (query = '') => {
        setIsLoadingMemory(true)
        try {
            const apiBase = window.location.hostname === 'localhost' ? 'http://localhost:7071' : ''
            const response = await fetch(`${apiBase}/api/SearchMemory?query=${encodeURIComponent(query)}`)
            if (response.ok) {
                const data = await response.json()
                setMemoryRules(data)
            }
        } catch (error) {
            console.error("Error fetching memory:", error)
        } finally {
            setIsLoadingMemory(false)
        }
    }

    const handleDeleteRule = async (id: string) => {
        if (!confirm("Tem certeza que deseja excluir esta regra de conhecimento?")) return

        try {
            const apiBase = window.location.hostname === 'localhost' ? 'http://localhost:7071' : ''
            const response = await fetch(`${apiBase}/api/DeleteMemoryRule?id=${id}`, { method: 'DELETE' })
            if (response.ok) {
                setMemoryRules(prev => prev.filter(r => r.id !== id))
            }
        } catch (error) {
            console.error("Error deleting rule:", error)
            alert("Erro ao excluir regra.")
        }
    }

    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault()
        fetchMemory(searchQuery)
    }

    const activeModel = modelHistory.find(h => h.status === 'active') || modelHistory[0]

    return (
        <div className="animate-fade-in space-y-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-xl font-bold text-gray-800">Biblioteca de Conhecimento - {sector}</h2>
                        <p className="text-sm text-gray-500">
                            {isPadrao
                                ? "Gerencie as regras aprendidas pela IA através das suas correções manuais."
                                : "Visualize e restaure o histórico de versões do modelo local."}
                        </p>
                    </div>
                    <button
                        onClick={isPadrao ? () => fetchMemory(searchQuery) : onRefresh}
                        className={`p-2 text-gray-400 hover:text-[#38a8f5] transition-colors ${isLoadingMemory ? 'animate-spin' : ''}`}
                        title="Atualizar"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                </div>

                {isPadrao ? (
                    <div className="space-y-4">
                        {/* Search Bar */}
                        <form onSubmit={handleSearch} className="relative">
                            <input
                                type="text"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                placeholder="Buscar nos itens aprendidos (ex: Tubo, Caneta...)"
                                className="w-full border border-gray-200 rounded-xl pl-11 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-all shadow-sm"
                            />
                            <svg className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                            </svg>
                            <button type="submit" className="hidden">Buscar</button>
                        </form>

                        {/* Rules Table */}
                        <div className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50">
                                        <tr>
                                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Item / Descrição</th>
                                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Classificação (N1)</th>
                                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Data</th>
                                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Ações</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {isLoadingMemory ? (
                                            <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">Carregando memória...</td></tr>
                                        ) : memoryRules.length === 0 ? (
                                            <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400">Nenhuma regra encontrada.</td></tr>
                                        ) : (
                                            memoryRules.map((rule) => (
                                                <tr key={rule.id} className="hover:bg-gray-50 transition-colors group">
                                                    <td className="px-4 py-3">
                                                        <div className="text-sm font-medium text-gray-900">{rule.description}</div>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#38a8f5]/10 text-[#0693e3]">
                                                            {rule.classification.N1}
                                                        </span>
                                                    </td>
                                                    <td className="px-4 py-3 text-xs text-gray-500">
                                                        {rule.date_added}
                                                    </td>
                                                    <td className="px-4 py-3 text-right">
                                                        <button
                                                            onClick={() => handleDeleteRule(rule.id)}
                                                            className="text-gray-400 hover:text-red-500 transition-colors p-1"
                                                            title="Excluir Regra"
                                                        >
                                                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                            </svg>
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                ) : (
                    /* Legacy View for ML Sectors */
                    <>
                        {modelHistory.length === 0 ? (
                            <div className="text-center py-12 bg-gray-50 rounded-lg border border-dashed border-gray-300">
                                <svg className="mx-auto h-12 w-12 text-gray-400 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                                </svg>
                                <p className="text-gray-500">Nenhum conhecimento registrado para este setor.</p>
                                <p className="text-sm text-gray-400 mt-1">Suba suas correções na aba "Refinar Inteligência" para registrar o primeiro conhecimento.</p>
                            </div>
                        ) : (
                            <div className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-6 border border-gray-200">
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-4">
                                            <div className="p-3 bg-green-100 rounded-lg">
                                                <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                </svg>
                                            </div>
                                            <div>
                                                <h3 className="text-lg font-semibold text-gray-800">Conhecimento Ativo</h3>
                                                <p className="text-sm text-gray-500">Versão: {activeModel?.version_id}</p>
                                            </div>
                                        </div>

                                        <div className="grid grid-cols-3 gap-4 mb-4">
                                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                                                <p className="text-xs text-gray-500 mb-1">Acurácia</p>
                                                <p className="text-xl font-bold text-[#0693e3]">
                                                    {activeModel ? (activeModel.metrics.accuracy * 100).toFixed(1) : '—'}%
                                                </p>
                                            </div>
                                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                                                <p className="text-xs text-gray-500 mb-1">Data do Registro</p>
                                                <p className="text-sm font-medium text-gray-800">
                                                    {activeModel ? new Date(activeModel.timestamp).toLocaleDateString('pt-BR') : '—'}
                                                </p>
                                            </div>
                                            <div className="bg-white rounded-lg p-3 border border-gray-200">
                                                <p className="text-xs text-gray-500 mb-1">Versões Disponíveis</p>
                                                <p className="text-xl font-bold text-gray-800">{modelHistory.length}</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <button
                                    onClick={() => setShowOverlay(true)}
                                    className="w-full py-3 px-4 bg-gradient-to-r from-[#38a8f5] to-[#0693e3] text-white rounded-lg hover:from-[#7ac8ff] hover:to-[#38a8f5] transition-all font-medium flex items-center justify-center gap-2 shadow-lg shadow-[#38a8f5]/20"
                                >
                                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                                    </svg>
                                    Visualizar Versões
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* Model Viewer Overlay */}
            {showOverlay && (
                <ModelViewerOverlay
                    sector={sector}
                    modelHistory={modelHistory}
                    onClose={() => setShowOverlay(false)}
                    onRestoreModel={(versionId) => {
                        onRestoreModel(versionId)
                        setShowOverlay(false)
                    }}
                    onRefresh={onRefresh}
                />
            )}
        </div>
    )
}
