import React, { useMemo } from 'react'
import AiAvatar from '@/components/ui/AiAvatar'

interface ProcessingOverlayProps {
  isVisible: boolean
  status?: string
  progress?: number // 0-100
  message?: string
  subMessage?: string
}

const PIPELINE_STEPS = [
  'Ordenando por similaridade',
  'Buscando na Base de Conhec.',
  'Classificando com Grok AI',
  'Validando hierarquia',
] as const

function getAiMessage(progress: number): string {
  if (progress < 5) return 'Preparando o ambiente...'
  if (progress < 15) return 'Ordenando itens por similaridade...'
  if (progress < 30) return 'Consultando a Base de Conhecimento...'
  if (progress < 85) return 'Classificando com Grok AI...'
  if (progress < 95) return 'Validando hierarquia taxonômica...'
  return 'Finalizando classificação...'
}

function getActiveStepIndex(progress: number): number {
  if (progress < 10) return 0
  if (progress < 30) return 1
  if (progress < 90) return 2
  return 3
}

const CheckIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    className={className}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
      clipRule="evenodd"
    />
  </svg>
)

export function ProcessingOverlay({
  isVisible,
  status,
  progress,
  message,
  subMessage,
}: ProcessingOverlayProps) {
  const activeStepIndex = useMemo(
    () => getActiveStepIndex(progress ?? 0),
    [progress]
  )

  const displayMessage = useMemo(() => {
    if (progress !== undefined) return getAiMessage(progress)
    return message || 'Processando...'
  }, [progress, message])

  const displaySubMessage = useMemo(() => {
    if (subMessage) return subMessage
    if (status) return status
    return null
  }, [subMessage, status])

  if (!isVisible) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-primary-900/60 backdrop-blur-md">
      {/* Card with entry animation */}
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-md w-full mx-4 p-8 animate-fade-in"
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
          <div className="mb-5">
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
        {displaySubMessage && (
          <p className="text-sm text-primary-400 text-center mb-6">
            {displaySubMessage}
          </p>
        )}

        {/* Pipeline steps */}
        <div className="mt-2 mb-6">
          {/* Section label */}
          <div className="flex items-center gap-2 mb-3">
            <div className="flex-1 h-px bg-gray-100" />
            <span className="text-xs text-primary-300 uppercase tracking-wider font-medium">
              O que está acontecendo?
            </span>
            <div className="flex-1 h-px bg-gray-100" />
          </div>

          {/* Steps list */}
          <ul className="space-y-2.5">
            {PIPELINE_STEPS.map((step, index) => {
              const isCompleted = index < activeStepIndex
              const isActive = index === activeStepIndex
              const isPending = index > activeStepIndex

              return (
                <li
                  key={step}
                  className="flex items-center justify-between text-sm"
                >
                  <div className="flex items-center gap-2.5">
                    {/* Step number */}
                    <span
                      className={[
                        'w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium flex-shrink-0',
                        isCompleted
                          ? 'bg-mint-100 text-mint-600'
                          : isActive
                            ? 'bg-accent-100 text-accent-600'
                            : 'bg-gray-50 text-gray-300',
                      ].join(' ')}
                    >
                      {index + 1}
                    </span>

                    {/* Step text */}
                    <span
                      className={
                        isCompleted
                          ? 'text-primary-500'
                          : isActive
                            ? 'text-primary-700 font-medium'
                            : 'text-gray-300'
                      }
                    >
                      {step}
                    </span>
                  </div>

                  {/* Status indicator */}
                  <span className="flex-shrink-0 ml-2">
                    {isCompleted && (
                      <CheckIcon className="w-4 h-4 text-mint-500" />
                    )}
                    {isActive && (
                      <span className="inline-flex items-center gap-1 text-accent-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-accent-500 animate-pulse" />
                        <span className="text-xs">...</span>
                      </span>
                    )}
                    {isPending && (
                      <span className="w-3 h-3 rounded-full border-2 border-gray-200 inline-block" />
                    )}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>

        {/* Cancel button */}
        <div className="flex justify-center">
          <button
            type="button"
            className="text-sm text-primary-400 hover:text-red-500 transition-colors cursor-pointer"
            onClick={() => {
              /* placeholder */
            }}
          >
            Cancelar classificação
          </button>
        </div>
      </div>
    </div>
  )
}
