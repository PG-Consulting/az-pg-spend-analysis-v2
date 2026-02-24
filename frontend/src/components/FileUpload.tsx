import { useState, useRef } from 'react'

interface FileUploadProps {
    onFileSelect: (file: File, fileContent: string) => void
    disabled?: boolean
}

export default function FileUpload({ onFileSelect, disabled }: FileUploadProps) {
    const [isDragging, setIsDragging] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    const handleFileRead = (file: File) => {
        const reader = new FileReader()
        reader.onload = (e) => {
            const base64 = e.target?.result as string
            // Remove data URL prefix to get pure base64
            const base64Content = base64.split(',')[1]
            onFileSelect(file, base64Content)
        }
        reader.readAsDataURL(file)
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)

        if (disabled) return

        const files = e.dataTransfer.files
        if (files.length > 0) {
            handleFileRead(files[0])
        }
    }

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files
        if (files && files.length > 0) {
            handleFileRead(files[0])
        }
    }

    return (
        <div
            onDragOver={(e) => {
                e.preventDefault()
                if (!disabled) setIsDragging(true)
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`
                border-2 border-dashed rounded-xl p-8 text-center transition-all duration-300 relative overflow-hidden group
                ${isDragging
                    ? 'border-[#38a8f5] bg-gradient-to-br from-[#38a8f5]/10 to-[#38a8f5]/5 shadow-lg shadow-[#38a8f5]/10'
                    : 'border-gray-300 bg-gradient-to-br from-gray-50 to-white hover:border-[#38a8f5]/50 hover:shadow-md hover:shadow-gray-200/50'
                }
                ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
            `}
            onClick={() => !disabled && fileInputRef.current?.click()}
        >
            {/* Subtle background pattern */}
            <div className="absolute inset-0 opacity-[0.03] pointer-events-none">
                <div className="absolute inset-0" style={{
                    backgroundImage: 'radial-gradient(circle at 2px 2px, #1c0957 1px, transparent 0)',
                    backgroundSize: '24px 24px'
                }} />
            </div>

            <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx,.xls,.csv"
                onChange={handleFileInput}
                className="hidden"
                disabled={disabled}
            />

            <div className="flex flex-col items-center gap-4 relative z-10">
                {/* Upload icon container */}
                <div className={`
                    w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300
                    ${isDragging
                        ? 'bg-[#38a8f5]/20 text-[#38a8f5] scale-110'
                        : 'bg-gray-100 text-gray-400 group-hover:bg-[#1c0957]/10 group-hover:text-[#1c0957]'
                    }
                `}>
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-8 w-8"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={1.5}
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                        />
                    </svg>
                </div>
                <div>
                    <p className="text-sm font-semibold text-gray-700 group-hover:text-gray-900 transition-colors">
                        Arraste seu arquivo aqui ou clique para selecionar
                    </p>
                    <p className="text-xs text-gray-400 mt-1.5">
                        Formatos aceitos: .xlsx, .xls, .csv
                    </p>
                </div>
            </div>
        </div>
    )
}
