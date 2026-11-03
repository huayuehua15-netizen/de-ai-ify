/** diff 工具单测（docs §13.1、§10.4：中文字符级 / 英文词级）。 */

import { describe, expect, it } from "vitest";

import { computeDiff, diffStats } from "@/lib/diff";

describe("computeDiff", () => {
  it("相同文本只有 same 段", () => {
    const parts = computeDiff("hello world", "hello world");
    expect(parts).toHaveLength(1);
    expect(parts[0].type).toBe("same");
    expect(parts[0].text).toBe("hello world");
  });

  it("中文走字符级：改动段不丢原文", () => {
    const parts = computeDiff("人工智能正在发展", "人工智能快速发展");
    const removed = parts.filter((p) => p.type === "removed").map((p) => p.text).join("");
    const added = parts.filter((p) => p.type === "added").map((p) => p.text).join("");
    expect(removed).toBe("正在");
    expect(added).toBe("快速");
    // 拼回原文 = same + removed
    const rebuilt =
      parts.filter((p) => p.type !== "added").map((p) => p.text).join("");
    expect(rebuilt).toBe("人工智能正在发展");
  });

  it("英文走词级：按词切分", () => {
    const parts = computeDiff("the quick fox", "the slow fox");
    const added = parts.filter((p) => p.type === "added").map((p) => p.text).join("");
    expect(added.trim()).toBe("slow");
  });

  it("中英混排整体退化为字符级（口径一致）", () => {
    const parts = computeDiff("使用 GPT 模型", "使用 Claude 模型");
    expect(parts.some((p) => p.type === "added")).toBe(true);
    expect(parts.some((p) => p.type === "removed")).toBe(true);
  });

  it("空串对比：纯新增", () => {
    const parts = computeDiff("", "新文本");
    expect(parts.every((p) => p.type === "added")).toBe(true);
    expect(diffStats(parts).added).toBe(3);
  });

  it("diffStats 统计增删字符数", () => {
    const parts = computeDiff("一二三", "一X三");
    expect(diffStats(parts)).toEqual({ added: 1, removed: 1 });
  });
});
