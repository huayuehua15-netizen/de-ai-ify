import type { NextConfig } from "next";

const API_PROXY_TARGET = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Docker 部署：产出 .next/standalone（自带最小 node_modules），镜像体积可减半以上。
  // 本地 dev 不受影响；CI 的 build 也会走 standalone，但产物未被使用。
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // 开发期将 /api 代理到 FastAPI，避免 CORS（见 docs/DEVELOPMENT.md §12.1）
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
