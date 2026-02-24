import React, { useCallback } from 'react'

interface DownloadCardProps {
    fileContentBase64: string
    downloadFilename: string
}

export default function DownloadCard({ fileContentBase64, downloadFilename }: DownloadCardProps) {
    const safeFilename = downloadFilename || 'resultado.xlsx'
    const fileExtension = safeFilename.split('.').pop()?.toUpperCase() || 'XLSX'

    const handleDownload = useCallback(() => {
        try {
            const cleanBase64 = fileContentBase64.replace(/\s/g, '').split(',').pop() || '';
            if (!cleanBase64) {
                alert('Erro: conteúdo do arquivo está vazio.');
                return;
            }

            const byteCharacters = atob(cleanBase64);
            const byteArrays: Uint8Array[] = [];
            for (let offset = 0; offset < byteCharacters.length; offset += 512) {
                const slice = byteCharacters.slice(offset, offset + 512);
                const byteNumbers = new Uint8Array(slice.length);
                for (let i = 0; i < slice.length; i++) {
                    byteNumbers[i] = slice.charCodeAt(i);
                }
                byteArrays.push(byteNumbers);
            }

            const blob = new Blob(byteArrays, {
                type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            });

            console.log(`[Download] Blob criado: ${blob.size} bytes`);

            if (blob.size === 0) {
                alert('Erro: arquivo gerado com 0 bytes.');
                return;
            }

            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = safeFilename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Erro ao gerar download:', error);
            alert('Erro ao gerar arquivo para download.');
        }
    }, [fileContentBase64, safeFilename]);

    return (
        <div className="flex gap-4 animate-fadeIn">
            {/* AI Avatar */}
            <div className="w-10 h-10 rounded-xl bg-white shadow-md flex items-center justify-center flex-shrink-0 overflow-hidden border border-gray-100">
                <img
                    src="/agent-icon.png"
                    alt="AI Agent"
                    className="w-full h-full object-cover"
                />
            </div>

            {/* Data Asset Card */}
            <div className="flex-1">
                <div className="bg-white rounded-2xl rounded-tl-md shadow-sm border border-[#32373c]/8 overflow-hidden">
                    {/* Success Header */}
                    <div className="px-5 py-3 bg-gradient-to-r from-[#0693e3]/10 to-transparent border-b border-gray-100">
                        <div className="flex items-center gap-2">
                            <div className="w-5 h-5 rounded-full bg-[#0693e3] flex items-center justify-center">
                                <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                </svg>
                            </div>
                            <span className="text-sm font-medium text-[#32373c]">Taxonomia concluída</span>
                        </div>
                    </div>

                    {/* File Info */}
                    <div className="p-5">
                        <div className="flex items-center gap-4">
                            {/* Excel Icon */}
                            <div className="w-14 h-14 rounded-xl bg-[#F5F7FA] flex items-center justify-center border border-gray-200">
                                <div className="text-center">
                                    <svg className="w-7 h-7 text-[#0693e3] mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                    </svg>
                                    <span className="text-[10px] font-bold text-[#0693e3] mt-0.5 block">{fileExtension}</span>
                                </div>
                            </div>

                            {/* File Details */}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold text-[#32373c] truncate" title={downloadFilename}>
                                    {downloadFilename}
                                </p>
                                <p className="text-xs text-[#829ab1] mt-1">
                                    Arquivo classificado • Pronto para download
                                </p>
                            </div>
                        </div>

                        {/* Download Button - Teal Gradient */}
                        <button
                            onClick={handleDownload}
                            className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-[#38a8f5] to-[#0693e3] hover:from-[#7ac8ff] hover:to-[#38a8f5] text-white rounded-lg font-medium text-sm transition-all duration-200 shadow-md hover:shadow-lg shadow-[#38a8f5]/20 group"
                        >
                            <svg className="w-4 h-4 group-hover:translate-y-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            <span>Baixar Arquivo</span>
                        </button>
                    </div>
                </div>

                <p className="text-xs text-[#829ab1] mt-2 pl-1">Agora</p>
            </div>
        </div>
    )
}
