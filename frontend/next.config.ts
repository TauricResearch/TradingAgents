import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'standalone',
  reactCompiler: true,
  
  // Security headers
  async headers() {
    return [
      {
        // Apply to all routes
        source: '/:path*',
        headers: [
          {
            key: 'X-DNS-Prefetch-Control',
            value: 'on'
          },
          {
            key: 'X-XSS-Protection',
            value: '1; mode=block'
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY'
          },
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff'
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin'
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()'
          },
          {
            // Content Security Policy
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",  // Required for Next.js
              "style-src 'self' 'unsafe-inline'",  // Required for Tailwind
              "img-src 'self' data: blob: https:",
              "font-src 'self' data:",
              "connect-src 'self' https://api.openai.com https://api.anthropic.com https://api.x.ai https://api.deepseek.com https://dashscope-intl.aliyuncs.com https://generativelanguage.googleapis.com https://*.alphavantage.co https://api.finmindtrade.com",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
            ].join('; ')
          },
        ],
      },
    ];
  },
  
  async rewrites() {
    // In development: use localhost backend
    // In production (Railway): use BACKEND_URL env var or fallback to Railway URL
    const isDev = process.env.NODE_ENV === 'development';
    // Default to http://backend:8000 in production (Docker) if not set
    const backendUrl = process.env.BACKEND_URL || 
      (isDev ? "http://localhost:8000" : "http://backend:8000");
    
    console.log(`[Next.js] Rewriting API requests to: ${backendUrl}`);
    
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
