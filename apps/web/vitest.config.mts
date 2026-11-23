import path from "node:path";

import { defineConfig } from "vitest/config";

// 用 import.meta.dirname 而非 __dirname：Vite 的 native config loader
// （未来默认）不支持 __dirname，会打印 deprecation 警告。
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname),
    },
  },
  test: {
    include: ["lib/**/*.test.ts", "components/**/*.test.tsx"],
    environment: "node",
  },
});
