/** @type {import('next').NextConfig} */
const nextConfig = {
  // React strict mode for better development experience
  reactStrictMode: true,

  // Optimize production builds
  swcMinify: true,

  // Webpack optimizations for WebGL/Three.js
  webpack: (config, { isServer }) => {
    // Exclude certain modules from bundle if not needed on server
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };
    }

    // Optimize Three.js bundle
    config.module.rules.push({
      test: /\.worker\.js$/,
      use: { loader: 'worker-loader' },
    });

    return config;
  },

  // Image optimization settings
  images: {
    domains: [],
    formats: ['image/avif', 'image/webp'],
  },

  // Headers for security and caching
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
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
          {
            key: 'X-Frame-Options',
            value: 'SAMEORIGIN',
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block',
          },
        ],
      },
    ];
  },

  // Environment variables exposed to client
  env: {
    NEXT_PUBLIC_WS_URL: process.env.WS_URL || 'ws://localhost:6379',
    NEXT_PUBLIC_API_URL: process.env.API_URL || 'http://localhost:8000',
  },
};

module.exports = nextConfig;
