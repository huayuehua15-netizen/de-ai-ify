# web

de-ai-ify Web 前端（Next.js 16 App Router + Tailwind CSS 4）。

- 快速开始见仓库根 [README](../../README.md)，开发文档见 [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md)；
- `/api/*` 请求由 `next.config.ts` 的 rewrites 代理到 `http://127.0.0.1:8000`（可用环境变量 `API_PROXY_TARGET` 覆盖）。
