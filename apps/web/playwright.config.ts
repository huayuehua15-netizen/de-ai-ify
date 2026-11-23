import { defineConfig, devices } from "@playwright/test";

/**
 * E2E 冒烟（docs §13.1、M3 验收）。
 *
 * 关键取舍：**不下载 Playwright 自带浏览器**，用系统已装的 Chrome
 * （`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1` + `channel: "chrome"`）。
 * 理由：CI 上多下一个 ~170MB 的 Chromium 没必要，而 GitHub 的
 * ubuntu-latest 镜像本身带 Chrome；本地也一样。
 *
 * BASE_URL 指向已经跑起来的 Web（Docker compose 的 web 服务在 3000，
 * 或 `pnpm --filter web dev` 的 3001）。默认 3000。
 */
const BASE_URL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  // 冒烟用例之间共享后端状态（批量任务、历史），串行更好读日志
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],
  timeout: 30_000,
  expect: { timeout: 8_000 },
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"], channel: "chrome" },
    },
  ],
});
