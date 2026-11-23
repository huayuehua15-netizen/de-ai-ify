/**
 * 批量页的文本切分（纯函数，便于单测；不依赖 React）。
 *
 * 切分规则按「显式优先、隐式兜底」：
 *   1. 有独占一行的 `---` → 按它切（用户显式分段，最可控）；
 *   2. 否则按连续空行切（粘贴文档的常见形态）；
 *   3. 都没有就整段算一条。
 *
 * 标题取首行（≤30 字），否则用序号「第 N 段」——与后端 BatchItemIn.title
 * 的 120 字上限兼容，且不参与改写。
 */

export interface DraftItem {
  /** React key，仅前端使用 */
  key: string;
  title: string;
  text: string;
}

function newKey(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function makeDraft(title: string, text: string): DraftItem {
  return { key: newKey(), title, text };
}

const TITLE_MAX = 30;

export function splitDrafts(raw: string): DraftItem[] {
  const text = raw.replace(/\r\n/g, "\n").trim();
  if (!text) return [];
  const hasRule = /^\s*-{3,}\s*$/m.test(text);
  const chunks = hasRule ? text.split(/^\s*-{3,}\s*$/m) : text.split(/\n\s*\n+/);
  return chunks
    .map((c) => c.trim())
    .filter((c) => c.length > 0)
    .map((c, i) => {
      const firstLine = c.split("\n")[0].trim();
      const title =
        firstLine.length > 0 && firstLine.length <= TITLE_MAX ? firstLine : `第 ${i + 1} 段`;
      return makeDraft(title, c);
    });
}
