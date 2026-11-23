import { expect, test } from "@playwright/test";

/**
 * 编辑器对齐与性能（docs §10.3、§15 M3 验收）：
 *  - overlay 与 textarea 的排版必须逐项一致，否则高亮会错位；
 *  - 中文 IME 组词期间文字必须可见（overlay 文字透明、textarea 不透明）；
 *  - 粘贴万字不卡顿（输入延迟 < 50ms）。
 *
 * overlay 用 `[data-testid="editor-overlay"]` 定位，不要用
 * `[aria-hidden]`——页面里第一个 aria-hidden 元素是个 SVG 图标。
 */

const AI_TEXT = "在当今社会，人工智能技术正在快速发展。综上所述，具有重要意义。";

const overlay = (page: import("@playwright/test").Page) => page.getByTestId("editor-overlay");
const ta = (page: import("@playwright/test").Page) => page.locator("textarea");

test.describe("overlay 与 textarea 对齐", () => {
  test("字体/行高/内边距/换行规则逐项一致", async ({ page }) => {
    await page.goto("/");
    await ta(page).fill(AI_TEXT);
    // 等高亮真正渲染出来再比
    await expect(page.locator("mark").first()).toBeVisible({ timeout: 15_000 });

    const metrics = await page.evaluate(() => {
      const t = document.querySelector("textarea") as HTMLTextAreaElement;
      const o = document.querySelector('[data-testid="editor-overlay"]') as HTMLElement;
      const pick = (el: Element) => {
        const s = getComputedStyle(el);
        return {
          fontFamily: s.fontFamily,
          fontSize: s.fontSize,
          fontWeight: s.fontWeight,
          lineHeight: s.lineHeight,
          letterSpacing: s.letterSpacing,
          paddingTop: s.paddingTop,
          paddingBottom: s.paddingBottom,
          paddingLeft: s.paddingLeft,
          whiteSpace: s.whiteSpace,
          overflowWrap: s.overflowWrap,
          wordBreak: s.wordBreak,
          boxSizing: s.boxSizing,
        };
      };
      return { ta: pick(t), ov: pick(o) };
    });

    // 右侧内边距会因滚动条补偿而不同，其余排版属性必须完全一致。
    expect(metrics.ov.fontFamily).toBe(metrics.ta.fontFamily);
    expect(metrics.ov.fontSize).toBe(metrics.ta.fontSize);
    expect(metrics.ov.fontWeight).toBe(metrics.ta.fontWeight);
    expect(metrics.ov.lineHeight).toBe(metrics.ta.lineHeight);
    expect(metrics.ov.letterSpacing).toBe(metrics.ta.letterSpacing);
    expect(metrics.ov.paddingTop).toBe(metrics.ta.paddingTop);
    expect(metrics.ov.paddingBottom).toBe(metrics.ta.paddingBottom);
    expect(metrics.ov.paddingLeft).toBe(metrics.ta.paddingLeft);
    expect(metrics.ov.whiteSpace).toBe(metrics.ta.whiteSpace);
    expect(metrics.ov.overflowWrap).toBe(metrics.ta.overflowWrap);
    expect(metrics.ov.boxSizing).toBe(metrics.ta.boxSizing);
  });

  test("overlay 内容区宽度与 textarea 一致，且右侧按滚动条宽度补偿", async ({ page }) => {
    await page.goto("/");
    await ta(page).fill(AI_TEXT.repeat(40)); // 撑出滚动
    await expect(page.locator("mark").first()).toBeVisible({ timeout: 20_000 });

    const box = await page.evaluate(() => {
      const t = document.querySelector("textarea") as HTMLTextAreaElement;
      const o = document.querySelector('[data-testid="editor-overlay"]') as HTMLElement;
      return {
        overflow: t.scrollHeight > t.clientHeight,
        scrollbar: t.offsetWidth - t.clientWidth,
        taContent: t.clientWidth,
        ovContent: o.clientWidth,
        ovPaddingRight: parseFloat(getComputedStyle(o).paddingRight),
      };
    });

    // 前提：文本确实溢出了（否则这条用例什么也没测）
    expect(box.overflow).toBe(true);
    // 补偿公式：overlay 的右内边距 = 20(p-5) + 滚动条宽度。
    // Chrome / Edge 用覆盖式滚动条时宽度为 0，公式退化成 20，这是对的。
    expect(box.ovPaddingRight).toBeCloseTo(20 + box.scrollbar, 0);
    // 关键不变量：两层画文字的区域宽度必须一样，否则高亮错位
    expect(Math.abs(box.ovContent - box.taContent)).toBeLessThanOrEqual(1);
  });

  test("长文本滚动时高亮跟随（overlay.scrollTop 同步）", async ({ page }) => {
    await page.goto("/");
    await ta(page).fill(AI_TEXT.repeat(40));
    await expect(page.locator("mark").first()).toBeVisible({ timeout: 20_000 });

    await ta(page).evaluate((el: HTMLTextAreaElement) => {
      el.scrollTop = 400;
      el.dispatchEvent(new Event("scroll"));
    });
    await page.waitForTimeout(150);

    const tops = await page.evaluate(() => {
      const t = document.querySelector("textarea") as HTMLTextAreaElement;
      const o = document.querySelector('[data-testid="editor-overlay"]') as HTMLElement;
      return { ta: t.scrollTop, ov: o.scrollTop };
    });
    expect(tops.ta).toBeGreaterThan(0);
    expect(Math.abs(tops.ov - tops.ta)).toBeLessThanOrEqual(1);
  });

  test("overlay 文字透明、textarea 文字不透明（中文仍可见）", async ({ page }) => {
    await page.goto("/");
    await ta(page).fill(AI_TEXT);
    await expect(page.locator("mark").first()).toBeVisible({ timeout: 15_000 });

    const transparentRe = /rgba\(0, 0, 0, 0\)|transparent/;
    await expect(overlay(page)).toHaveCSS("color", "rgba(0, 0, 0, 0)");
    const taColor = await ta(page).evaluate((el) => getComputedStyle(el).color);
    expect(taColor).not.toMatch(transparentRe);
  });
});

/**
 * 直接给 textarea 赋值并让 React 收到变更。
 *
 * 不能用 `el.value = text` —— React 的值追踪器把原生 setter 包了一层，
 * 这样赋值会被追踪器认为"没变化"，onChange 不触发（受控组件不更新）。
 * 必须绕过追踪器，用原型上的原生 setter。
 */
async function setValue(
  page: import("@playwright/test").Page,
  text: string,
): Promise<void> {
  await page.locator("textarea").evaluate((el: HTMLTextAreaElement, t: string) => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(el, t);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
}

test.describe("输入性能", () => {
  test("粘贴一万字后逐字输入 p95 < 50ms", async ({ page }) => {
    await page.goto("/");
    const textarea = ta(page);

    // 造一万字：多段中文，避免被当成超长单行。
    // 段数按需计算——写少了会拿不到一万字。
    const para = "第{n}段：在当今社会，技术正在快速发展，首先提升了效率；其次降低了成本。";
    const unit = para.replace("{n}", "0");
    const count = Math.ceil(10_000 / (unit.length + 1));
    const big = Array.from({ length: count }, (_, i) => para.replace("{n}", String(i)))
      .join("\n")
      .slice(0, 10_000);
    expect(big.length).toBe(10_000);

    await setValue(page, big);
    // 确认受控组件真的收到了这一次变更（不然性能数据毫无意义）
    expect(await textarea.inputValue()).toHaveLength(10_000);

    // 等防抖评分触发并返回（不阻塞输入，但会占一次渲染）
    await page.waitForTimeout(1_500);

    const samples: number[] = [];
    for (let i = 0; i < 20; i += 1) {
      const ms = await page.evaluate(async (ch: string) => {
        const el = document.querySelector("textarea") as HTMLTextAreaElement;
        const setter = Object.getOwnPropertyDescriptor(
          HTMLTextAreaElement.prototype,
          "value",
        )?.set;
        el.focus();
        const t0 = performance.now();
        setter?.call(el, el.value + ch);
        el.setSelectionRange(el.value.length, el.value.length);
        el.dispatchEvent(new Event("input", { bubbles: true }));
        await new Promise((r) => requestAnimationFrame(() => r(null)));
        return performance.now() - t0;
      }, "字");
      samples.push(ms);
    }

    const sorted = [...samples].sort((a, b) => a - b);
    const p95 = sorted[Math.ceil(sorted.length * 0.95) - 1];
    console.log(
      `输入延迟 p50=${sorted[10].toFixed(1)}ms p95=${p95.toFixed(1)}ms max=${sorted.at(-1)!.toFixed(1)}ms`,
    );
    // docs §15 要求 < 50ms
    expect(p95).toBeLessThan(50);
  });

  test("超长文本给出明确提示而不是静默失败", async ({ page }) => {
    await page.goto("/");
    // 先取到后端真实上限
    const limit = await page.evaluate(async () => {
      const r = await fetch("/api/v1/health");
      const j = await r.json();
      return (j.limits?.max_text_chars as number | undefined) ?? 20000;
    });

    await setValue(page, "字".repeat(limit + 10));

    await expect(page.getByText(/超过 [\d,]+ 字上限/)).toBeVisible({ timeout: 15_000 });
  });
});
