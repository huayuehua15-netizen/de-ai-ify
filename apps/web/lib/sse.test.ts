/** SSE 解析器单测（docs §13.1：前端 sse 解析器）。 */

import { describe, expect, it } from "vitest";

import { parseSse } from "@/lib/sse";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const out: { event: string; data: string }[] = [];
  for await (const msg of parseSse(stream)) out.push(msg);
  return out;
}

describe("parseSse", () => {
  it("解析完整帧序列", async () => {
    const raw =
      'event: start\ndata: {"before":76}\n\n' +
      'event: delta\ndata: {"text":"你"}\n\n' +
      'event: done\ndata: {"versions":1}\n\n';
    const msgs = await collect(streamOf(raw));
    expect(msgs.map((m) => m.event)).toEqual(["start", "delta", "done"]);
    expect(JSON.parse(msgs[0].data).before).toBe(76);
  });

  it("跨 chunk 的半帧会被拼回", async () => {
    const msgs = await collect(
      streamOf('event: del', 'ta\ndata: {"te', 'xt":"abc"}\n', "\n"),
    );
    expect(msgs).toHaveLength(1);
    expect(msgs[0].event).toBe("delta");
    expect(JSON.parse(msgs[0].data).text).toBe("abc");
  });

  it("一个 chunk 内含多帧时全部产出", async () => {
    const msgs = await collect(
      streamOf('event: a\ndata: 1\n\nevent: b\ndata: 2\n\nevent: c\ndata: 3\n\n'),
    );
    expect(msgs.map((m) => m.event)).toEqual(["a", "b", "c"]);
  });

  it("忽略注释/心跳行（: ping）", async () => {
    const msgs = await collect(streamOf(": ping\n\nevent: x\ndata: 1\n\n"));
    expect(msgs).toHaveLength(1);
    expect(msgs[0].event).toBe("x");
  });

  it("CRLF 帧格式", async () => {
    const msgs = await collect(streamOf("event: e\r\ndata: v\r\n\r\n"));
    expect(msgs).toEqual([{ event: "e", data: "v" }]);
  });

  it("多行 data 合并", async () => {
    const msgs = await collect(streamOf("event: m\ndata: line1\ndata: line2\n\n"));
    expect(msgs[0].data).toBe("line1\nline2");
  });

  it("无 event 字段时默认 message", async () => {
    const msgs = await collect(streamOf("data: solo\n\n"));
    expect(msgs[0].event).toBe("message");
  });

  it("流尾残留帧兜底产出", async () => {
    const msgs = await collect(streamOf("event: tail\ndata: last")); // 无空行结尾
    expect(msgs).toHaveLength(1);
    expect(msgs[0].data).toBe("last");
  });

  it("空数据帧被丢弃", async () => {
    const msgs = await collect(streamOf("event: empty\n\n"));
    expect(msgs).toHaveLength(0);
  });
});
