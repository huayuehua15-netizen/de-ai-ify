/**
 * SSE 客户端：POST /api/v1/rewrite/stream（docs §7.3）。
 *
 * 原生 EventSource 只支持 GET，无法 POST 文本体，故用 fetch + ReadableStream
 * 自行解析 event/data 帧。服务端为 sse-starlette，帧格式：
 *
 *   event: delta\n
 *   data: {"style":"natural",...}\n
 *   \n
 */

import type { ApiErrorBody } from "./types";

export interface SseMessage {
  event: string;
  data: string;
}

/** 把 SSE 字节流解析成事件序列（跨 chunk 的半帧会被缓存）。 */
export async function* parseSse(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseMessage> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // 帧以空行结尾；兼容 \r\n
      let sep: number;
      while ((sep = buffer.search(/\r?\n\r?\n/)) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep).replace(/^\r?\n\r?\n/, "");
        const msg = decodeFrame(raw);
        if (msg) yield msg;
      }
    }
    // 流结束时的残留（服务端未以空行收尾的兜底）
    const msg = decodeFrame(buffer);
    if (msg) yield msg;
  } finally {
    reader.releaseLock();
  }
}

function decodeFrame(raw: string): SseMessage | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue; // 注释/心跳
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join("\n") };
}

export interface StreamCallbacks {
  onEvent: (msg: SseMessage) => void;
}

/** 发起改写流请求并逐帧回调；非 200 抛 ApiError 形状的错误。 */
export async function openRewriteStream(
  body: unknown,
  { onEvent }: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/v1/rewrite/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let code = "http_error";
    let message = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as ApiErrorBody;
      if (err.error) {
        code = err.error.code;
        message = err.error.message;
      }
    } catch {
      // 保留默认信息
    }
    const error = new Error(message) as Error & { code?: string };
    error.code = code;
    throw error;
  }
  for await (const msg of parseSse(res.body)) {
    onEvent(msg);
  }
}
