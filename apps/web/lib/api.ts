/**
 * REST 客户端：/api/v1/*（经 next.config.ts rewrites 代理到 FastAPI，无 CORS）。
 * 错误体统一为 {"error":{code,message,request_id}}（docs §7.4），此处归一为 ApiError。
 */

import type {
  AnalysisResult,
  ApiErrorBody,
  HealthData,
  ProviderOut,
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
