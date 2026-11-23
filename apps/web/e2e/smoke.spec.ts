import { expect, test } from "@playwright/test";

/**
 * 冒烟：首屏 + 评分主流程（docs §15 M3 验收「Playwright 冒烟全过」）。
 *
 * 这些用例只依赖**纯本地评分**，不需要模型凭据——这正是产品卖点之一，
 * 也让 e2e 能在 CI 里稳定跑（不需要 key、不需要假上游）。
 *
 * 选择器原则：优先 data-testid（产品代码里专门为此加的），
 * 其次 role/文本。不用 `span.tabular-nums` 这类样式类——字数计数器
 * 和八维分数都用同一个类，会抓错元素。
 */

const AI_TEXT =
  "在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；" +
  "其次，它降低了运营成本；最后，它优化了用户体验。综上所述，" +
  "人工智能具有重要意义，值得我们进行深入探讨与研究。";

test.describe("首屏与评分", () => {
  test("首页可用：编辑器、评分占位、风格选择器都在", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator("textarea")).toBeVisible();
    // 风格胶囊：默认选 3 个（DEFAULT_STYLE_COUNT）
    await expect(page.getByRole("button", { name: /一键改写（\d+）/ })).toBeVisible();
    // 评分面板空态
    await expect(page.getByTestId("score-empty")).toBeVisible();
    // 顶栏入口齐全
    for (const label of ["批量", "词库", "历史", "模型设置"]) {
      await expect(page.getByRole("link", { name: label, exact: true })).toBeVisible();
    }
  });

  test("粘贴文本后自动评分：出总分、八维、命中列表", async ({ page }) => {
    await page.goto("/");
    await page.locator("textarea").fill(AI_TEXT);

    // 防抖 600ms + 请求；给足时间
    const scoreEl = page.getByTestId("score-value");
    await expect(scoreEl).toBeVisible({ timeout: 15_000 });

    const score = Number((await scoreEl.textContent())?.trim());
    expect(Number.isFinite(score)).toBe(true);
    expect(score).toBeGreaterThanOrEqual(0);
    expect(score).toBeLessThanOrEqual(100);
    // 这段是典型 AI 套话，必然偏高
    expect(score).toBeGreaterThan(40);

    // 八维全部渲染（用后端权威的中文名）
    for (const dim of [
      "套话密度",
      "句长均匀度",
      "连接词密度",
      "名词化倾向",
      "结构重复",
      "模板句式",
      "空泛度",
      "个性化信号",
    ]) {
      await expect(page.getByText(dim, { exact: false }).first()).toBeVisible();
    }

    // 反向维度带 ↻ 标记
    await expect(page.getByText("↻").first()).toBeVisible();

    // 命中列表标题带数量，且至少命中一处
    const hitHeading = page.getByRole("heading", { name: /命中位置（\d+）/ });
    await expect(hitHeading).toBeVisible();
    const hitText = (await hitHeading.textContent()) ?? "";
    const hits = Number(hitText.match(/（(\d+)）/)?.[1] ?? 0);
    expect(hits).toBeGreaterThan(0);

    // 原文里的高亮 mark 数量与命中数一致
    await expect(page.locator("mark")).toHaveCount(hits);
  });

  test("示例文本按钮：空态一键填入并立即出分", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /用示例文本试试/ }).click();

    await expect(page.locator("textarea")).toHaveValue(/人工智能/);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });
  });

  test("命中卡片与原文高亮联动", async ({ page }) => {
    await page.goto("/");
    await page.locator("textarea").fill(AI_TEXT);
    await expect(page.getByRole("heading", { name: /命中位置（\d+）/ })).toBeVisible({
      timeout: 15_000,
    });

    // 点第一张命中卡片 → textarea 的 selection 覆盖那个片段
    await page.locator("ul li button").first().click();
    const sel = await page.locator("textarea").evaluate((el: HTMLTextAreaElement) => ({
      start: el.selectionStart,
      end: el.selectionEnd,
    }));
    expect(sel.end).toBeGreaterThan(sel.start);
  });

  test("清空文本后评分复位", async ({ page }) => {
    await page.goto("/");
    await page.locator("textarea").fill(AI_TEXT);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });

    await page.locator("textarea").fill("");
    await expect(page.getByTestId("score-empty")).toBeVisible();
    await expect(page.getByTestId("score-value")).toHaveCount(0);
  });

  test("全选删除能清空全文（选区不被高亮抢走）", async ({ page }) => {
    // 回归测试：handleSelect 曾在光标落在 finding 内时把选区强行改窄，
    // 导致 Ctrl+A → Delete 只删掉了第一个命中的片段。
    await page.goto("/");
    const ta = page.locator("textarea");
    await ta.fill(AI_TEXT);
    await expect(page.getByTestId("score-value")).toBeVisible({ timeout: 15_000 });

    await ta.click();
    await page.keyboard.press("Control+A");
    await page.keyboard.press("Delete");

    await expect(ta).toHaveValue("");
    await expect(page.getByTestId("score-empty")).toBeVisible();
  });
});

test.describe("其它页面可达", () => {
  for (const [path, expectText] of [
    ["/settings", /模型/],
    ["/lexicon", /词库/],
    ["/history", /历史/],
    ["/batch", /批量/],
  ] as const) {
    test(`${path} 渲染正常`, async ({ page }) => {
      const resp = await page.goto(path);
      expect(resp?.status()).toBe(200);
      await expect(page.locator("body")).toContainText(expectText);
    });
  }
});
