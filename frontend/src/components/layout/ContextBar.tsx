import React from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type StepId = 'classify' | 'review' | 'analyze'
export type StepStatus = 'completed' | 'active' | 'available' | 'locked'

export interface ContextBarProps {
  /** Project display name shown in the breadcrumb */
  projectName: string | null
  /** Uploaded file name shown in the breadcrumb */
  sessionFilename: string | null

  /** Currently active step */
  activeStep: StepId
  /** Status for each step (controls dot color and clickability) */
  stepStatuses: Record<StepId, StepStatus>
  /** Fired when user clicks a step that is not locked */
  onStepClick: (step: StepId) => void

  /** Opens the Knowledge Base slide-over */
  onOpenKB: () => void
  /** When true the KB button is visually disabled */
  kbDisabled?: boolean

  /** If provided, renders a thin progress bar at the bottom of the bar */
  reviewProgress?: { reviewed: number; total: number }

  /** Shows a small notification dot on the Review step */
  hasReviewNotification?: boolean
}

// ---------------------------------------------------------------------------
// Step metadata
// ---------------------------------------------------------------------------

const STEPS: { id: StepId; label: string; number: number }[] = [
  { id: 'classify', label: 'Classificar', number: 1 },
  { id: 'review', label: 'Revisar', number: 2 },
  { id: 'analyze', label: 'Analisar', number: 3 },
]

// ---------------------------------------------------------------------------
// Icons (inline SVG to avoid external dependencies)
// ---------------------------------------------------------------------------

function BookIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
    </svg>
  )
}

function ChevronRight({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M9 18l6-6-6-6" />
    </svg>
  )
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Breadcrumb section (left-aligned) */
function Breadcrumb({
  projectName,
  sessionFilename,
  activeStep,
}: {
  projectName: string | null
  sessionFilename: string | null
  activeStep: StepId
}) {
  const stepLabel = STEPS.find((s) => s.id === activeStep)?.label ?? ''
  const stepNumber = STEPS.find((s) => s.id === activeStep)?.number ?? 1

  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 min-w-0">
      {projectName && (
        <>
          <span className="text-sm font-medium text-[#32373c] truncate max-w-[160px]">
            {projectName}
          </span>
          <ChevronRight className="text-primary-400 flex-shrink-0" />
        </>
      )}
      {sessionFilename && (
        <>
          <span className="text-sm text-primary-400 truncate max-w-[180px]">
            {sessionFilename}
          </span>
          <ChevronRight className="text-primary-400 flex-shrink-0" />
        </>
      )}
      <span className="text-sm font-medium text-accent-500 whitespace-nowrap">
        Passo {stepNumber}: {stepLabel}
      </span>
    </nav>
  )
}

/** Single step dot with label */
function StepDot({
  step,
  status,
  isActive,
  hasNotification,
  onClick,
}: {
  step: (typeof STEPS)[number]
  status: StepStatus
  isActive: boolean
  hasNotification: boolean
  onClick: () => void
}) {
  const isClickable = status !== 'locked'

  // Dot background color by status
  const dotBg =
    status === 'completed'
      ? 'bg-mint-300'
      : status === 'active'
        ? 'bg-accent-500'
        : status === 'available'
          ? 'bg-accent-200'
          : 'bg-gray-300'

  // Active ring glow
  const ringClasses = isActive
    ? 'ring-[3px] ring-accent-500/25'
    : ''

  // Label color
  const labelColor =
    status === 'active'
      ? 'text-accent-600 font-medium'
      : status === 'completed'
        ? 'text-mint-600 font-medium'
        : status === 'available'
          ? 'text-primary-500'
          : 'text-gray-400'

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!isClickable}
      aria-current={isActive ? 'step' : undefined}
      aria-label={`Passo ${step.number}: ${step.label}${status === 'locked' ? ' (bloqueado)' : ''}`}
      className={`
        flex flex-col items-center gap-1 relative group
        ${isClickable ? 'cursor-pointer' : 'cursor-default'}
        focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/30 rounded
      `}
    >
      {/* Dot */}
      <span className="relative flex items-center justify-center">
        <span
          className={`
            w-2.5 h-2.5 rounded-full transition-all duration-200
            ${dotBg} ${ringClasses}
            ${isClickable && !isActive ? 'group-hover:scale-125' : ''}
          `}
        >
          {status === 'completed' && (
            <span className="absolute inset-0 flex items-center justify-center">
              <CheckIcon className="text-white" />
            </span>
          )}
        </span>

        {/* Notification dot */}
        {hasNotification && (
          <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-red-500 border border-white" />
        )}
      </span>

      {/* Label */}
      <span className={`text-[11px] leading-none whitespace-nowrap ${labelColor}`}>
        {step.label}
      </span>
    </button>
  )
}

/** Connector line between dots */
function Connector({ leftStatus, rightStatus }: { leftStatus: StepStatus; rightStatus: StepStatus }) {
  // Line is colored if left step is completed
  const isColored = leftStatus === 'completed'
  const bgClass = isColored ? 'bg-mint-200' : 'bg-gray-200'
  // If right is also completed or active, show a slightly stronger line
  const isFullyColored = leftStatus === 'completed' && (rightStatus === 'completed' || rightStatus === 'active')
  const finalBg = isFullyColored ? 'bg-mint-300' : bgClass

  return <span className={`w-8 h-px ${finalBg} self-start mt-[5px]`} />
}

/** KB button (right-aligned) */
function KBButton({
  onClick,
  disabled,
}: {
  onClick: () => void
  disabled: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label="Abrir Base de Conhecimento"
      className={`
        inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium
        transition-all duration-200
        ${
          disabled
            ? 'text-gray-400 cursor-not-allowed'
            : 'text-primary-600 hover:bg-accent-50 hover:text-accent-600 active:scale-[0.97]'
        }
        focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-500/25
      `}
    >
      <BookIcon className={disabled ? 'text-gray-400' : 'text-accent-500'} />
      <span className="hidden sm:inline">Base de Conhecimento</span>
      <span className="sm:hidden">KB</span>
    </button>
  )
}

/** Review progress thin bar at bottom */
function ReviewProgressBar({
  reviewed,
  total,
}: {
  reviewed: number
  total: number
}) {
  const pct = total > 0 ? Math.min((reviewed / total) * 100, 100) : 0

  return (
    <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-100 overflow-hidden">
      <div
        className="h-full bg-gradient-to-r from-accent-500 to-ai-400 transition-all duration-500 ease-out"
        style={{ width: `${pct}%` }}
        role="progressbar"
        aria-valuenow={reviewed}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={`Revisao: ${reviewed} de ${total} itens revisados`}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function ContextBar({
  projectName,
  sessionFilename,
  activeStep,
  stepStatuses,
  onStepClick,
  onOpenKB,
  kbDisabled = false,
  reviewProgress,
  hasReviewNotification = false,
}: ContextBarProps) {
  const showProgress =
    reviewProgress != null && reviewProgress.total > 0

  return (
    <header
      className="relative bg-white border-b border-gray-100 shadow-[0_1px_3px_rgba(0,0,0,0.04)]"
    >
      <div className="flex items-center justify-between px-5 py-2">
        {/* Left: Breadcrumb */}
        <div className="flex-1 min-w-0">
          <Breadcrumb
            projectName={projectName}
            sessionFilename={sessionFilename}
            activeStep={activeStep}
          />
        </div>

        {/* Center: Step dots */}
        <nav
          aria-label="Etapas do fluxo"
          className="flex items-start gap-0 mx-4 flex-shrink-0"
        >
          {STEPS.map((step, idx) => (
            <React.Fragment key={step.id}>
              {idx > 0 && (
                <Connector
                  leftStatus={stepStatuses[STEPS[idx - 1].id]}
                  rightStatus={stepStatuses[step.id]}
                />
              )}
              <StepDot
                step={step}
                status={stepStatuses[step.id]}
                isActive={activeStep === step.id}
                hasNotification={step.id === 'review' && hasReviewNotification}
                onClick={() => onStepClick(step.id)}
              />
            </React.Fragment>
          ))}
        </nav>

        {/* Right: KB button */}
        <div className="flex-1 flex justify-end min-w-0">
          <KBButton onClick={onOpenKB} disabled={kbDisabled} />
        </div>
      </div>

      {/* Bottom: Review progress bar */}
      {showProgress && (
        <ReviewProgressBar
          reviewed={reviewProgress!.reviewed}
          total={reviewProgress!.total}
        />
      )}
    </header>
  )
}
