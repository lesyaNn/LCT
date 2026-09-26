import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: process.cwd(),
  async rewrites() {
    const backendOrigin = (process.env.API_PROXY_TARGET || 'http://localhost:8000').replace(/\/$/, '');
    return [{ source: '/api/v1/:path*', destination: `${backendOrigin}/api/v1/:path*` }];
  },
};

export default nextConfig;
