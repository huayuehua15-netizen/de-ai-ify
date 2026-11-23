import { describe, expect, it } from "vitest";

import { splitDrafts } from "@/lib/batch-split";

describe("splitDrafts", () => {
  it("按独占一行的 --- 切分", () => {
    const out = splitDrafts("第一段内容\n\n---\n\n第二段内容");
    expect(out.map((d) => d.text)).toEqual(["第一段内容", "第二段内容"]);
  });

  it("--- 两侧有无空行都能切", () => {
    const out = splitDrafts("甲\n---\n乙\n--- \n丙");
    expect(out.map((d) => d.text)).toEqual(["甲", "乙", "丙"]);
  });

  it("没有分隔行时按空行分段", () => {
    const out = splitDrafts("第一段\n还是第一段\n\n第二段");
    expect(out.map((d) => d.text)).toEqual(["第一段\n还是第一段", "第二段"]);
  });

  it("多行连续空行不会产生空条目", () => {
    const out = splitDrafts("甲\n\n\n\n乙\n\n\n");
    expect(out).toHaveLength(2);
    expect(out.every((d) => d.text.length > 0)).toBe(true);
  });

  it("空输入返回空数组", () => {
    expect(splitDrafts("")).toEqual([]);
    expect(splitDrafts("   \n\n  ")).toEqual([]);
  });

  it("首行短则用作标题，否则用序号", () => {
    const out = splitDrafts("标题一\n正文\n\n这是一段非常非常长的开头而它超过了三十个字符所以不能当标题使用啊真的超过了吧确实超过了");
    expect(out[0].title).toBe("标题一");
    expect(out[1].title).toBe("第 2 段");
  });

  it("Windows 换行也能正确切分", () => {
    const out = splitDrafts("甲\r\n\r\n乙");
    expect(out.map((d) => d.text)).toEqual(["甲", "乙"]);
  });

  it("单段文本整条返回", () => {
    const out = splitDrafts("就一段，没有分隔");
    expect(out).toHaveLength(1);
    expect(out[0].text).toBe("就一段，没有分隔");
  });
});
