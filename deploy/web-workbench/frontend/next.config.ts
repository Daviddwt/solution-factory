import type { NextConfig } from "next";

const backendApiBase = process.env.API_BASE || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  devIndicators: false,
  output: "standalone",
  experimental: {
    middlewareClientMaxBodySize: "200mb",
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendApiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
