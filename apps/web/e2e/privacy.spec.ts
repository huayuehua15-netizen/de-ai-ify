import { expect, test } from "@playwright/test";

import { ensureFakeProvider } from "./helpers";

/**
 * 隐私契约的端到端验证（docs §8.2、§13.1 测试表最后一行）。
 *
 * 这条最容易"文档写了但没做"：接口返回体脱敏是一回事，
 * **落库的到底是什么**是另一回事。所以这里不看页面，
 * 直接比对 /history 返回的每一行与刚才提交的原文。
 *
 * 默认 DEAIIFY_STORE=never（compose 与 CI 都是），此时：
 *   - 只写 text_hash / text_len / 分数，stored_text 恒为 NULL
 *   - 列表接口响应里连 text 字段都没有
 *
 * 注意：**只有 /rewrite 落历史，/analyze 不落**（评分是纯本地计算，
 * 没有持久化理由）。所以这条用例走 rewrite。
 */

// 一段有辨识度的文本，用来断言它不会出现在任何地方
const MARKER = "隐私契约标记ZZQ";
const PRIVATE_TEXT =
  `${MARKER}：在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；` +
  "其次，它降低了运营成本；最后，它优化了用户体验。综上所述，人工智能具有重要意义。";

test.describe("隐私：never 模式不留原文", () => {
  test("改写后历史里有记录，但落库与响应都不含原文", async ({ request }) => {
    // 落历史只在 /rewrite 里发生，所以必须先有可用模型（假上游）
    const ready = await ensureFakeProvider(request);
    test.skip(!ready, "假上游未就绪，跳过落库检查");

    const rewrite = await request.post("/api/v1/rewrite", {
      data: {
        text: PRIVATE_TEXT,
        styles: ["natural"],
        store: false,
        gate: true,
      },
      timeout: 90_000,
    });

    if (!rewrite.ok()) {
      const err = await rewrite.text();
      // 没有可用模型时无从验证落库（CI 里由 fake_upstream.py 保证有）
      test.skip(
        /provider|model|未配置|未指定/.test(err),
        `没有可用模型，跳过：${err.slice(0, 120)}`,
      );
      expect(rewrite.ok(), `rewrite 失败：${err.slice(0, 300)}`).toBeTruthy();
    }

    // GET /history 直接返回数组（response_model=list[HistoryOut]），没有外层包裹
    const listed = await request.get("/api/v1/history?limit=10");
    expect(listed.ok()).toBeTruthy();
    const rows = (await listed.json()) as Array<Record<string, unknown>>;
    expect(Array.isArray(rows)).toBeTruthy();

    // 整段响应里都不该出现原文的任何片段
    const raw = JSON.stringify(rows);
    expect(raw).not.toContain(MARKER);
    expect(raw).not.toContain("在当今社会");

    // 刚写的那条：按长度定位（同长度不同文本会命中多条，取第一条即可）
    const hit = rows.find((it) => it.text_len === PRIVATE_TEXT.length);
    expect(hit, "刚改写的这条应该出现在历史里").toBeTruthy();

    // 关键断言：never 模式下 stored_text 恒为 null，且响应里根本没有 text 字段
    expect(hit!.stored_text).toBeNull();
    expect(hit).not.toHaveProperty("text");

    // 有哈希（SHA256 全 64 位十六进制）与长度：能去重统计，不能还原
    expect(String(hit!.text_hash)).toMatch(/^[0-9a-f]{64}$/);
    expect(hit!.text_len).toBe(PRIVATE_TEXT.length);
    expect(hit!.expires_at).toBeNull();
  });

  test("历史页明确说明看不到原文是设计如此", async ({ page }) => {
    await page.goto("/history");
    await expect(page.locator("body")).toContainText(/隐私模式|看不到原文是设计如此/);
  });
});
