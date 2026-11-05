/**
 * REST 客户端：/api/v1/*（经 next.config.ts rewrites 代理到 FastAPI，无 CORS）。
 * 错误体统一为 {"error":{code,message,request_id}}（docs §7.4），此处归一为 ApiError。
 */

import type {
  AnalysisResult,
  ApiErrorBody,
  BuiltinInfo,
  ClearResult,
  ConnectivityResult,
  HealthData,
  HistoryItem,
  Lexicon,
  ProviderConfig,
  ProviderOut,
  ProviderPreset,
  StyleOut,
} from "./types";

export const MAX_TEXT_CHARS = 20000; // 与 DEAIIFY_MAX_TEXT_CHARS 默认一致

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let code = "http_error";
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as ApiErrorBody;
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // 非 JSON 错误体（如代理层 502）：保留默认信息
    }
    throw new ApiError(code, message, res.status);
  }
  // 204 No Content / 空体：不解析 JSON
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export function analyze(
  text: string,
  opts: { signal?: AbortSignal } = {},
): Promise<AnalysisResult> {
  return request<AnalysisResult>("/api/v1/analyze", {
    method: "POST",
    body: JSON.stringify({ text, lang: "auto" }),
    signal: opts.signal,
  });
}

export function fetchStyles(): Promise<StyleOut[]> {
  return request<StyleOut[]>("/api/v1/styles");
}

export function fetchModels(): Promise<ProviderOut[]> {
  return request<ProviderOut[]>("/api/v1/models");
}

export function fetchHealth(signal?: AbortSignal): Promise<HealthData> {
  return request<HealthData>("/api/v1/health", { cache: "no-store", signal });
}

/* —— 供应商配置（模型设置页）—— */

export function fetchPresets(): Promise<ProviderPreset[]> {
  return request<ProviderPreset[]>("/api/v1/providers/presets");
}

export function fetchProviderConfigs(): Promise<ProviderConfig[]> {
  return request<ProviderConfig[]>("/api/v1/providers");
}

export function createProviderConfig(body: {
  name: string;
  kind: string;
  base_url?: string | null;
  api_key?: string | null;
  default_model?: string | null;
  is_default?: boolean;
}): Promise<ProviderConfig> {
  return request<ProviderConfig>("/api/v1/providers", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProviderConfig(
  id: string,
  body: Record<string, unknown>,
): Promise<ProviderConfig> {
  return request<ProviderConfig>(`/api/v1/providers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteProviderConfig(id: string): Promise<void> {
  return request<void>(`/api/v1/providers/${id}`, { method: "DELETE" });
}

export function setDefaultProvider(id: string): Promise<ProviderConfig> {
  return request<ProviderConfig>(`/api/v1/providers/${id}/default`, { method: "POST" });
}

export function testProviderConfig(id: string): Promise<ConnectivityResult> {
  return request<ConnectivityResult>(`/api/v1/providers/${id}/test`, { method: "POST" });
}

export function testProviderDraft(body: {
  kind: string;
  base_url?: string | null;
  api_key?: string | null;
}): Promise<ConnectivityResult> {
  return request<ConnectivityResult>("/api/v1/providers/test", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/* —— 词库（M4）—— */

export function fetchLexicons(): Promise<Lexicon[]> {
  return request<Lexicon[]>("/api/v1/lexicons");
}

export function fetchLexicon(id: string): Promise<Lexicon> {
  return request<Lexicon>(`/api/v1/lexicons/${id}`);
}

export function createLexicon(body: {
  name: string;
  description?: string | null;
  lang?: string;
  terms?: Array<Record<string, unknown>>;
}): Promise<Lexicon> {
  return request<Lexicon>("/api/v1/lexicons", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateLexicon(
  id: string,
  body: { name?: string; description?: string | null; lang?: string },
): Promise<Lexicon> {
  return request<Lexicon>(`/api/v1/lexicons/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteLexicon(id: string): Promise<void> {
  return request<void>(`/api/v1/lexicons/${id}`, { method: "DELETE" });
}

export function addLexiconTerms(
  id: string,
  terms: Array<Record<string, unknown>>,
): Promise<Lexicon> {
  return request<Lexicon>(`/api/v1/lexicons/${id}/terms`, {
    method: "POST",
    body: JSON.stringify({ terms }),
  });
}

export function deleteLexiconTerm(id: string, termId: string): Promise<void> {
  return request<void>(`/api/v1/lexicons/${id}/terms/${termId}`, { method: "DELETE" });
}

export function importLexicon(
  id: string,
  format: "csv" | "json",
  content: string,
): Promise<Lexicon> {
  return request<Lexicon>(`/api/v1/lexicons/${id}/import`, {
    method: "POST",
    body: JSON.stringify({ format, content }),
  });
}

/** 导出为文本（CSV/JSON）——直接拿原始响应体，不走 JSON 解析。 */
export async function exportLexicon(id: string, format: "csv" | "json"): Promise<string> {
  const res = await fetch(`/api/v1/lexicons/${id}/export?format=${format}`);
  if (!res.ok) {
    throw new ApiError("export_failed", `导出失败 HTTP ${res.status}`, res.status);
  }
  return await res.text();
}

export function fetchBuiltinInfo(): Promise<BuiltinInfo> {
  return request<BuiltinInfo>("/api/v1/lexicons/builtin");
}

export function setBuiltinDisabled(
  terms: string[],
  disabled: boolean,
): Promise<{ disabled: string[] }> {
  return request<{ disabled: string[] }>("/api/v1/lexicons/builtin/disabled", {
    method: "PUT",
    body: JSON.stringify({ terms, disabled }),
  });
}

/* —— 改写历史（M4）—— */

export function fetchHistory(limit = 50): Promise<HistoryItem[]> {
  return request<HistoryItem[]>(`/api/v1/history?limit=${limit}`);
}

export function clearHistory(): Promise<ClearResult> {
  return request<ClearResult>("/api/v1/history", { method: "DELETE" });
}
