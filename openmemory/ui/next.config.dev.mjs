/**
 * @format
 * @type {import('next').NextConfig}
 */

const nextConfig = {
  basePath: '/config/memory',
  distDir: '/config/memory/.next',
  output: 'standalone',
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  publicRuntimeConfig: {
    hostname: process.env.NEXT_PUBLIC_URL,
  },
};

export default nextConfig;
