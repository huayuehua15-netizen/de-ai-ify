import { expect, test } from "@playwright/test";

import { ensureFakeProvider, FAKE_BASE_URL } from "./helpers";

/**
 * 改写链路（docs §15 M2「curl 走通 rewrite/stream」的浏览器版）。
 *
 * **为什么要假上游**：这条链路必须真打一次 HTTP 才能验证——prompt 拼装、
 * SSE 帧序、闸门重算、前端打字机。CI 里没有模型凭据也不该有（花钱且不稳定），
 * 所以用 `.github/scripts/fake_upstream.py` 起一个最小 OpenAI 兼容服务。
 *
 * **前置条件**（CI 与本地一致，由 CI 步骤保证）：
 *   1. `python .github/scripts/fake_upstream.py --port 9100` 在跑；
 *   2. 后端有一条供应商指向 `http://127.0.0.1:9100/v1`，模型 `fake-deaiify-1`；
 *   3. 它必须是默认供应商（或页面里能选中它）。
 *
 * 拿不到前置条件时整组 skip 而不是失败——e2e 的主职责是评分冒烟，
 * 改写链路的额外覆盖不该让「只在本地跑评分」的场景变红。
 */

const AI_TEXT =
  "在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；" +
  "其次，它降低了运营成本；最后，它优化了用户体验。综上所述，" +
  "人工智能具有重要意义，值得我们进行深入探讨与研究。";

test.describe("改写链路（假上游）", () => {
  test.beforeEach(async ({ page, request }) => {
    const ok = await ensureFakeProvider(request);
    test.skip(!ok, `假上游未就绪（${FAKE_BASE_URL}）或供应商创建失败，跳过改写链路用例`);
    await page.goto("/");
  });

  test("一键改写：加载态 → 版本 Tab → 采纳进编辑区", async ({ page }) => {
    // 先确认页面认到了供应商（否则按钮会走「去配置」分支）
    await expect(page.getByRole("button", { name: /一键改写（\d+）/ })).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("textarea").fill(AI_TEXT);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /一键改写（\d+）/ }).click();

    // 加载态：按钮文案变「改写中…」
    await expect(page.getByRole("button", { name: "改写中…" })).toBeVisible({ timeout: 10_000 });

    // 版本出现（默认选 3 个风格 → 应该有 3 个 Tab）
    const adoptButtons = page.getByRole("button", { name: "采纳" });
    await expect(adoptButtons.first()).toBeVisible({ timeout: 30_000 });

    // 每个版本都有 gate 徽章
    await expect(page.getByText(/通过|弱通过|未通过|未校验/).first()).toBeVisible();

    // 采纳第一个版本 → 编辑区文本被替换，且出现撤销
    await adoptButtons.first().click();
    await expect(page.locator("textarea")).not.toHaveValue(AI_TEXT);
    await expect(page.getByText(/已采纳「/)).toBeVisible();
    await expect(page.getByRole("button", { name: /撤销/ })).toBeVisible();
  });

  test("改写后能看 Diff，且分栏显示原文与改写", async ({ page }) => {
    await page.locator("textarea").fill(AI_TEXT);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /一键改写（\d+）/ }).click();

    const adopt = page.getByRole("button", { name: "采纳" }).first();
    await expect(adopt).toBeVisible({ timeout: 30_000 });
    await adopt.click();

    // 采纳时 workspace.tsx 的 handleAdopt 会 setDiffOpen(true)：
    // Diff 默认就展开，按钮当下显示「收起 Diff」。先收起再展开，两条路径都验。
    await expect(page.getByRole("button", { name: /收起 Diff/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "原稿" })).toBeVisible();

    await page.getByRole("button", { name: /收起 Diff/ }).click();
    await expect(page.getByRole("heading", { name: "原稿" })).toHaveCount(0);

    const diffToggle = page.getByRole("button", { name: /查看与原稿的 Diff/ });
    await expect(diffToggle).toBeVisible();
    await diffToggle.click();
    await expect(page.getByRole("button", { name: /收起 Diff/ })).toBeVisible();

    // DiffView 用带背景色的 span（不是 ins/del），双栏模式下左右各一栏
    await expect(page.getByRole("heading", { name: "原稿" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "改写稿" })).toBeVisible();
    // 顶部有增删统计：+N / −M 字符
    await expect(page.getByText(/^\+\d+ \/ −\d+ 字符$/)).toBeVisible();
    // 分数徽章：AI 味 before → after（Δ）
    await expect(page.getByText(/^AI 味 \d+/)).toBeVisible();
  });

  test("撤销能退回改写前的原文", async ({ page }) => {
    await page.locator("textarea").fill(AI_TEXT);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /一键改写（\d+）/ }).click();

    const adopt = page.getByRole("button", { name: "采纳" }).first();
    await expect(adopt).toBeVisible({ timeout: 30_000 });
    await adopt.click();

    const undo = page.getByRole("button", { name: /撤销/ });
    await expect(undo).toBeVisible();
    await undo.click();
    await expect(page.locator("textarea")).toHaveValue(AI_TEXT);
  });

  test("改写后分数下降（闸门真在算，不是摆设）", async ({ page }) => {
    await page.locator("textarea").fill(AI_TEXT);
    const scoreEl = page.getByTestId("score-value");
    await expect(scoreEl).toBeVisible({ timeout: 15_000 });
    const before = Number(((await scoreEl.textContent()) ?? "").trim());

    await page.getByRole("button", { name: /一键改写（\d+）/ }).click();
    await expect(page.getByRole("button", { name: "采纳" }).first()).toBeVisible({
      timeout: 30_000,
    });

    // 版本 Tab 上的 Δ 应该显示为负数（改写使 AI 味下降）
    const deltas = await page.locator("text=/^-\\d+$/").allTextContents();
    expect(deltas.length).toBeGreaterThan(0);

    // 采纳后总分应低于原文
    await page.getByRole("button", { name: "采纳" }).first().click();
    await expect
      .poll(
        async () => {
          const v = await page.getByTestId("score-value").textContent();
          return Number((v ?? "").trim());
        },
        { timeout: 20_000 },
      )
      .toBeLessThan(before);
  });
});
