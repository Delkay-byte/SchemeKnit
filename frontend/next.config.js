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
};

module.exports = nextConfig;
