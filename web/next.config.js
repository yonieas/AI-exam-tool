/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        // BACKEND_URL: Docker service name (http://api:8000) — used server-side.
        // Fallback to localhost:8000 for local dev.
        destination: `${process.env.BACKEND_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};
module.exports = nextConfig;
