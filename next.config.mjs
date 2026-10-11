// `npm run desktop:build` sets AERO_DESKTOP=1 to emit a static export for the Electron shell.
// That build gets its own distDir: Next.js may delete its contents, and `next dev` uses .next.
const desktop = process.env.AERO_DESKTOP === '1'

/** @type {import('next').NextConfig} */
const nextConfig = {
  ...(desktop ? { output: 'export', distDir: '.next-desktop' } : {}),
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default nextConfig
