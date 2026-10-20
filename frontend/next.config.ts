import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: process.cwd(),
  // Local embedding + generation can exceed the default 30-second proxy limit.
  // Keep this bounded and above the backend's two default 120-second stages.
  experimental: { proxyTimeout: 360_000 },
  async rewrites() {
    const backendOrigin = (process.env.API_PROXY_TARGET || 'http://localhost:8000').replace(/\/$/, '');
    return [{ source: '/api/v1/:path*', destination: `${backendOrigin}/api/v1/:path*` }];
  },
};

export default nextConfig;
