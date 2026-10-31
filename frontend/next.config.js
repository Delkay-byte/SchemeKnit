/** @type {import('next').NextConfig} */

// Desktop builds need a fully static export (served by Electron from frontend/out).
// Web builds must stay server-rendered so dynamic routes (/review/[id], /generate/[id],
// /lessons/[id]) work on refresh and direct navigation.
const isDesktopBuild = process.env.NEXT_PUBLIC_BUILD_TARGET === 'desktop';

const nextConfig = {
  reactStrictMode: true,
  ...(isDesktopBuild ? { output: 'export' } : {}),
  trailingSlash: true,
  assetPrefix: '',
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      (isDesktopBuild ? 'http://127.0.0.1:18234' : 'http://localhost:8000'),
    NEXT_PUBLIC_BUILD_TARGET: process.env.NEXT_PUBLIC_BUILD_TARGET || 'web',
  },
  async headers() {
    const csp = [
      "default-src 'self'",
      // Next.js injects inline bootstrap scripts; dynamic code execution is not allowed.
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      "connect-src 'self' https://schemeknit-api.onrender.com https://api.paystack.co https://checkout.paystack.com",
      "frame-src 'self' https://checkout.paystack.com",
      "frame-ancestors 'self'",
      "base-uri 'self'",
      "object-src 'none'",
      "form-action 'self' https://checkout.paystack.com",
    ].join('; ')
    const common = [
      { key: 'Content-Security-Policy', value: csp },
      { key: 'Strict-Transport-Security', value: 'max-age=31536000' },
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
    ]
    return [
      { source: '/(.*)', headers: common },
      {
        source: '/(dashboard|upload|review|generate|lessons|settings|platform-admin|school-admin|templates|weekly-plans|subscription|upgrade|payments)/:path*',
        headers: [{ key: 'Cache-Control', value: 'no-store' }],
      },
    ]
  },
};

module.exports = nextConfig;
