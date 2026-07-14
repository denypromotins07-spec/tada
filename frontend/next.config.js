/** @type {import('next').NextConfig} */
const nextConfig = {
  // Optimize for local hosting and performance
  output: 'standalone',
  
  // Enable React Strict Mode for development
  reactStrictMode: true,
  
  // Image optimization settings
  images: {
    unoptimized: true,
    domains: ['localhost'],
  },
  
  // Webpack configuration for performance
  webpack: (config, { isServer }) => {
    // Reduce bundle size
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };
    }
    
    return config;
  },
  
  // Environment variables
  env: {
    API_URL: process.env.API_URL || 'http://localhost:8000',
    WS_URL: process.env.WS_URL || 'ws://localhost:8000',
  },
  
  // Headers for security
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on',
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
        ],
      },
    ];
  },
  
  // Experimental features for performance
  experimental: {
    optimizePackageImports: ['lightweight-charts', 'recharts', 'framer-motion'],
  },
};

module.exports = nextConfig;
