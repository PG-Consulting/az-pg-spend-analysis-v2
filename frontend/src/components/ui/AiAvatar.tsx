import React from 'react'

interface AiAvatarProps {
  size?: 'sm' | 'md' | 'lg'
  pulse?: boolean
  className?: string
}

const sizeMap = {
  sm: 'w-6 h-6',
  md: 'w-8 h-8',
  lg: 'w-10 h-10',
} as const

const iconSizeMap = {
  sm: 'w-3 h-3',
  md: 'w-4 h-4',
  lg: 'w-5 h-5',
} as const

const SparkleIcon: React.FC<{ className?: string }> = ({ className }) => (
  <svg
    className={className}
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden="true"
  >
    <path d="M12 2L14.09 8.26L20 9.27L15.55 13.97L16.91 20L12 16.9L7.09 20L8.45 13.97L4 9.27L9.91 8.26L12 2Z" />
  </svg>
)

const AiAvatar: React.FC<AiAvatarProps> = ({
  size = 'md',
  pulse = false,
  className = '',
}) => {
  return (
    <div
      className={[
        'relative inline-flex items-center justify-center rounded-full',
        'bg-gradient-to-br from-[#0693e3] to-[#9b51e0]',
        'ring-2 ring-[#0693e3]/25',
        'text-white flex-shrink-0',
        sizeMap[size],
        pulse ? 'animate-pulse' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      role="img"
      aria-label="AI Assistant"
    >
      <SparkleIcon className={iconSizeMap[size]} />
    </div>
  )
}

export default AiAvatar
