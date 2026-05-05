import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Output a standalone build so the production Docker image only needs
  // the ``.next/standalone`` directory to run — drops final image size
  // dramatically.
  output: "standalone",
  reactStrictMode: true,

  // Belt-and-suspenders: also wire the @/ alias through webpack
  // explicitly. Next 15 *should* honour tsconfig paths but inside the
  // Alpine build container something about the lookup wasn't picking
  // them up; an explicit alias at the bundler level always works.
  webpack: (config) => {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@": path.resolve(__dirname),
    };
    return config;
  },

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
