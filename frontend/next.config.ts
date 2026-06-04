import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: process.env.SKIP_REACT_COMPILER !== "1",
  output: "standalone",
  ...(process.env.DOCKER_BUILD === "1"
    ? { experimental: { cpus: 1 } as NextConfig["experimental"] }
    : {}),
  async rewrites() {
    const apiBase = process.env.INTERNAL_API_URL ?? 'http://127.0.0.1:5055';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
