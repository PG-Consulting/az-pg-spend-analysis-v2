/**
 * Design Tokens — Procurement Garage Brand
 *
 * Cyan-blue (#0693e3) + Purple (#9b51e0) signature gradient
 * Navy sidebar (#1c0957) as brand anchor
 * Mint (#7bdcb5) for success states
 */

export const colors = {
    navy: {
        50: '#f0f4f8', 100: '#d9e2ec', 200: '#bcccdc', 300: '#9fb3c8',
        400: '#829ab1', 500: '#627d98', 600: '#486581', 700: '#334e68',
        800: '#1c0957', 900: '#0e0330',
    },
    accent: {
        50: '#eff8ff', 100: '#d9efff', 200: '#b3dfff', 300: '#7ac8ff',
        400: '#38a8f5', 500: '#0693e3', 600: '#0576b8', 700: '#045d94',
        800: '#034d7a', 900: '#023f65',
    },
    ai: {
        50: '#f6f0ff', 100: '#ede0ff', 200: '#d4b8ff', 300: '#b88aff',
        400: '#9b51e0', 500: '#7c3aed', 600: '#6525c4',
    },
    mint: {
        50: '#eefbf5', 100: '#d4f6e8', 200: '#a8edd1', 300: '#7bdcb5',
        400: '#4fc89a', 500: '#2db17f', 600: '#1f8f66',
    },
    text: {
        primary: '#32373c',
        secondary: '#486581',
        light: '#829ab1',
        white: '#FFFFFF',
        muted: '#9fb3c8',
    },
    background: {
        primary: '#F8FAFC',
        secondary: '#F1F5F9',
        card: '#FFFFFF',
        sidebar: '#1c0957',
    },
    status: {
        success: '#2db17f',
        warning: '#f0b429',
        error: '#e12d39',
        info: '#0693e3',
    },
} as const

export const gradients = {
    signature: 'from-[#0693e3] to-[#9b51e0]',
    signatureHover: 'from-[#0576b8] to-[#7c3aed]',
    sidebar: 'from-[#1c0957] via-[#180847] to-[#120535]',
    accent: 'from-[#0693e3] to-[#38a8f5]',
    accentSubtle: 'from-[#0693e3]/10 to-[#38a8f5]/10',
    mint: 'from-[#2db17f] to-[#7bdcb5]',
    ai: 'from-[#9b51e0] to-[#b88aff]',
} as const

export const shadows = {
    sm: '0 1px 3px rgba(28, 9, 87, 0.06)',
    md: '0 4px 12px rgba(28, 9, 87, 0.08)',
    lg: '0 8px 24px rgba(28, 9, 87, 0.10)',
    xl: '0 12px 40px rgba(28, 9, 87, 0.14)',
    card: '0 4px 20px rgba(28, 9, 87, 0.06)',
    input: '0 2px 8px rgba(28, 9, 87, 0.04)',
    inputFocus: '0 0 0 3px rgba(6, 147, 227, 0.15)',
    glow: '0 0 20px rgba(6, 147, 227, 0.4)',
    glowSubtle: '0 0 12px rgba(6, 147, 227, 0.2)',
    glowAi: '0 0 20px rgba(155, 81, 224, 0.4)',
} as const

export const tw = {
    glass: 'bg-white/80 backdrop-blur-sm border border-white/50',
    glassStrong: 'bg-white/95 backdrop-blur-xl border border-gray-100',
    glassDark: 'bg-[#1c0957]/80 backdrop-blur-sm border border-white/10',
    gradientText: 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0] bg-clip-text text-transparent',
    buttonPrimary: 'bg-accent-500 text-white hover:bg-accent-600 active:scale-[0.98] transition-all duration-200 shadow-md hover:shadow-lg',
    buttonSecondary: 'bg-white border border-gray-200 text-primary-600 hover:bg-gray-50 hover:border-gray-300 transition-colors',
    buttonGhost: 'text-primary-500 hover:text-primary-700 hover:bg-gray-100 transition-colors',
    buttonAi: 'bg-gradient-to-r from-[#0693e3] to-[#9b51e0] text-white hover:shadow-lg active:scale-[0.98] transition-all duration-200',
    buttonMint: 'bg-mint-500 text-white hover:bg-mint-600 active:scale-[0.98] transition-all duration-200',
    card: 'bg-white rounded-2xl shadow-[0_4px_20px_rgba(28,9,87,0.06)] border border-gray-100',
    cardHover: 'hover:shadow-[0_8px_30px_rgba(28,9,87,0.10)] hover:translate-y-[-2px] transition-all duration-300',
    sidebarItem: 'text-white/70 hover:text-white hover:bg-white/10 transition-all duration-200',
    sidebarItemActive: 'text-white bg-white/15 backdrop-blur-sm border-l-2 border-accent-400',
    input: 'w-full px-4 py-3 rounded-xl border border-gray-200 bg-white shadow-[0_2px_8px_rgba(28,9,87,0.04)] focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-500 transition-all',
    pulseGlow: 'animate-glow-pulse',
    fadeIn: 'animate-fade-in',
    slideUp: 'animate-slide-up',
} as const

export const iconColors = {
    navy: 'text-primary-800',
    accent: 'text-accent-500',
    muted: 'text-primary-400',
    white: 'text-white',
    success: 'text-mint-500',
    warning: 'text-amber-500',
    error: 'text-red-500',
    ai: 'text-ai-400',
} as const

export const typography = {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    heading: 'font-semibold text-[#32373c]',
    body: 'text-[#486581]',
    caption: 'text-sm text-[#829ab1]',
} as const

export default { colors, gradients, shadows, tw, iconColors, typography }
