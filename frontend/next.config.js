/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'export',
    reactStrictMode: true,
    images: {
        unoptimized: true,
    },
    // Disable webpack caching to avoid RangeError: Array buffer allocation failed on machines with low RAM
    webpack: (config, { dev }) => {
        if (dev) {
            config.cache = false;
        }
        return config;
    },
    // Ensure environment variables are available
    env: {
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
        NEXT_PUBLIC_FUNCTION_KEY: process.env.NEXT_PUBLIC_FUNCTION_KEY,
    },
}

module.exports = nextConfig
