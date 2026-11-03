/**
 * Diff 对比（docs §10.4）：英文按词、中文按字符（无空格分词）。
 * 基于 jsdiff 9；输出归一化的片段列表供渲染。
 */

import { diffChars, diffWordsWithSpace } from "diff";

export type DiffPartType = "same" | "added" | "removed";

export interface DiffPart {
  type: DiffPartType;
  text: string;
}

const CJK_RE = /[一-鿿㐀-䶿]/;

function hasCjk(text: string): boolean {
  return CJK_RE.test(text);
}

/** 词级/字符级 diff；中文任一侧含 CJK 则整体退化为字符级，保证左右口径一致。 */
export function computeDiff(original: string, rewritten: string): DiffPart[] {
  const parts =
    hasCjk(original) || hasCjk(rewritten)
      ? diffChars(original, rewritten)
      : diffWordsWithSpace(original, rewritten);
  return parts.map((p) => ({
    type: p.added ? "added" : p.removed ? "removed" : "same",
    text: p.value,
  }));
}

/** 改动摘要统计（用于 Diff 顶部徽章）。 */
export function diffStats(parts: DiffPart[]): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const p of parts) {
    if (p.type === "added") added += p.text.length;
    else if (p.type === "removed") removed += p.text.length;
  }
  return { added, removed };
}
