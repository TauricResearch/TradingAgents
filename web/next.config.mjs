/** @type {import('next').NextConfig} */
const nextConfig = {
  serverExternalPackages: ["child_process"],
  experimental: {
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
};

export default nextConfig;
