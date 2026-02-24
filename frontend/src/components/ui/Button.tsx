import React from 'react'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: 'primary' | 'secondary' | 'ghost' | 'accent' | 'ai-gradient' | 'mint' | 'danger'
    size?: 'sm' | 'md' | 'lg' | 'xl'
    loading?: boolean
    icon?: React.ReactNode
    children: React.ReactNode
}

const sizeMap = {
    sm: 'px-3 py-1.5 text-sm rounded-lg',
    md: 'px-4 py-2 text-sm rounded-xl',
    lg: 'px-6 py-3 text-base rounded-xl',
    xl: 'px-8 py-4 text-base rounded-2xl font-semibold',
}

const variantMap = {
    primary: 'bg-accent-500 text-white hover:bg-accent-600 shadow-md hover:shadow-lg',
    secondary: 'bg-white border border-gray-200 text-primary-600 hover:bg-gray-50 hover:border-gray-300',
    ghost: 'text-primary-500 hover:text-primary-700 hover:bg-gray-100',
    accent: 'bg-accent-500 text-white hover:bg-accent-600 shadow-md hover:shadow-lg',
    'ai-gradient': 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0] text-white hover:shadow-lg hover:shadow-[#0693e3]/25',
    mint: 'bg-mint-500 text-white hover:bg-mint-600 shadow-md hover:shadow-lg',
    danger: 'bg-red-500 text-white hover:bg-red-600 shadow-md hover:shadow-lg',
}

export default function Button({
    variant = 'primary',
    size = 'md',
    loading = false,
    icon,
    children,
    className = '',
    disabled,
    ...props
}: ButtonProps) {
    return (
        <button
            className={[
                'inline-flex items-center justify-center gap-2 font-medium',
                'focus:outline-none focus:ring-2 focus:ring-accent-500/25 focus:ring-offset-1',
                'active:scale-[0.98] transition-all duration-200',
                variantMap[variant],
                sizeMap[size],
                disabled || loading ? 'opacity-50 cursor-not-allowed' : '',
                className,
            ].join(' ')}
            disabled={disabled || loading}
            {...props}
        >
            {loading ? (
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            ) : icon ? (
                icon
            ) : null}
            {children}
        </button>
    )
}
