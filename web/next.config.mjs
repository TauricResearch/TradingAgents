/** @type {import('next').NextConfig} */
const nextConfig = {
  // Output a standalone build so the production Docker image only needs
  // the ``.next/standalone`` directory to run — drops final image size
  // dramatically.
  output: "standalone",
  reactStrictMode: true,

  // Proxy /api/* to the FastAPI backend in dev. In production the
  // reverse proxy (Synology) handles routing.
  async rewrites() {
    const api = process.env.API_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${api}/:path*` },
    ];
  },
};

export default nextConfig;
