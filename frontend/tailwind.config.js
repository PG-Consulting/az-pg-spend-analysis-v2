/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
        './src/components/**/*.{js,ts,jsx,tsx,mdx}',
        './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    ],
    theme: {
        extend: {
            colors: {
                primary: {
                    50: '#f0f4f8',
                    100: '#d9e2ec',
                    200: '#bcccdc',
                    300: '#9fb3c8',
                    400: '#829ab1',
                    500: '#627d98',
                    600: '#486581',
                    700: '#334e68',
                    800: '#1c0957',
                    900: '#0e0330',
                },
                accent: {
                    50: '#eff8ff',
                    100: '#d9efff',
                    200: '#b3dfff',
                    300: '#7ac8ff',
                    400: '#38a8f5',
                    500: '#0693e3',
                    600: '#0576b8',
                    700: '#045d94',
                    800: '#034d7a',
                    900: '#023f65',
                },
                ai: {
                    50: '#f6f0ff',
                    100: '#ede0ff',
                    200: '#d4b8ff',
                    300: '#b88aff',
                    400: '#9b51e0',
                    500: '#7c3aed',
                    600: '#6525c4',
                },
                mint: {
                    50: '#eefbf5',
                    100: '#d4f6e8',
                    200: '#a8edd1',
                    300: '#7bdcb5',
                    400: '#4fc89a',
                    500: '#2db17f',
                    600: '#1f8f66',
                },
            },
            animation: {
                'fade-in': 'fadeIn 0.3s ease-out',
                'slide-up': 'slideUp 0.3s ease-out',
                'slide-right': 'slideRight 0.3s ease-out',
                'glow-pulse': 'glowPulse 2s ease-in-out infinite',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0', transform: 'translateY(8px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(16px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                slideRight: {
                    '0%': { opacity: '0', transform: 'translateX(-16px)' },
                    '100%': { opacity: '1', transform: 'translateX(0)' },
                },
                glowPulse: {
                    '0%, 100%': { boxShadow: '0 0 20px rgba(6,147,227,0.3)' },
                    '50%': { boxShadow: '0 0 40px rgba(6,147,227,0.6)' },
                },
            },
        },
    },
    plugins: [],
}
