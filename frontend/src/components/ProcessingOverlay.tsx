import React, { useMemo } from 'react'
import AiAvatar from '@/components/ui/AiAvatar'

interface ProcessingOverlayProps {
  isVisible: boolean
  status?: string
  progress?: number // 0-100
  message?: string
  subMessage?: string
  onCancel?: () => void
  cancelling?: boolean
}

export function ProcessingOverlay({
  isVisible,
  status,
  progress,
  message,
  subMessage,
  onCancel,
  cancelling,
}: ProcessingOverlayProps) {
  const displayMessage = useMemo(() => {
    if (status && status !== 'Processando...') return status
    return message || 'Processando...'
  }, [status, message])

  if (!isVisible) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-primary-900/60 backdrop-blur-md">
      {/* Card with entry animation */}
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-sm w-full mx-4 p-8 animate-fade-in"
        style={{ animationDuration: '300ms' }}
      >
        {/* AI Avatar */}
        <div className="flex justify-center mb-6">
          <AiAvatar size="lg" pulse className="animate-glow-pulse" />
        </div>

        {/* Dynamic title */}
        <h3 className="text-lg font-semibold text-[#32373c] text-center mb-5">
          {displayMessage}
        </h3>

        {/* Progress bar section */}
        {progress !== undefined && (
          <div className="mb-4">
            {/* Percentage right-aligned above bar */}
            <div className="flex justify-end mb-1.5">
              <span className="text-sm text-accent-500 font-medium">
                {Math.round(progress)}%
              </span>
            </div>

            {/* Progress track */}
            <div className="w-full h-2 rounded-full bg-gray-100">
              <div
                className="h-2 rounded-full transition-all duration-500 ease-out"
                style={{
                  width: `${progress}%`,
                  background: 'linear-gradient(to right, #0693e3, #9b51e0)',
                }}
              />
            </div>
          </div>
        )}

        {/* Subtitle */}
        {subMessage && (
          <p className="text-sm text-primary-400 text-center mb-4">
            {subMessage}
          </p>
        )}

        {/* Cancel button */}
        <div className="flex justify-center pt-2">
          <button
            type="button"
            disabled={cancelling}
            className={`text-sm transition-colors cursor-pointer ${
              cancelling
                ? 'text-primary-300 cursor-not-allowed'
                : 'text-primary-400 hover:text-red-500'
            }`}
            onClick={onCancel}
          >
            {cancelling ? 'Cancelando...' : 'Cancelar classificação'}
          </button>
        </div>
      </div>
    </div>
  )
}
