"use client";

/**
 * 健康徽标（三态，M4 扩展）：
 *   绿「可改写」  —— 后端活着 + 至少配了一个供应商（UI 配置或 .env 兜底）
 *   青「API 已连接」—— 后端活着，但没配模型（评分仍可用，改写不可用）
 *   黄「API 未连接」—— 后端不可达
 *
 * 注意：这里只反映**配置是否齐备**，不代表上游模型此刻一定可达；
 * 上游真实连通性在 /settings 页按需测试（/providers/{id}/test）。
 */

import { useEffect, useState } from "react";

import type { HealthData } from "@/lib/types";

type State =
  | { phase: "loading" }
  | { phase: "ok"; data: HealthData }
  | { phase: "down"; error: string };

export function HealthBadge() {
  const [state, setState] = useState<State>({ phase: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/health", { cache: "no-store", signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as HealthData;
      })
      .then((data) => setState({ phase: "ok", data }))
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setState({
          phase: "down",
          error: err instanceof Error ? err.message : String(err),
        });
      });
    return () => controller.abort();
  }, []);

  if (state.phase === "loading") {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-zinc-300 px-3 py-1 text-sm text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
        <span className="h-2 w-2 animate-pulse rounded-full bg-zinc-400" />
        检测中…
      </span>
    );
  }

  if (state.phase === "down") {
    return (
      <span
        title={state.error}
        className="inline-flex items-center gap-2 rounded-full border border-amber-300 px-3 py-1 text-sm text-amber-700 dark:border-amber-700 dark:text-amber-400"
      >
        <span className="h-2 w-2 rounded-full bg-amber-500" />
        API 未连接（先启动 pnpm dev:api）
      </span>
    );
  }

  const { db, redis, providers } = state.data;
  const storageOk = db.status === "ok" && (redis.status === "ok" || redis.status === "skipped");

  if (providers?.ready) {
    const source = providers.source === "ui" ? `已配置 ${providers.count} 个` : ".env";
    return (
      <span
        title={[
          `db: ${db.status}`,
          `redis: ${redis.status}`,
          `模型: ${source}${providers.default ? `（默认 ${providers.default}）` : ""}`,
        ].join(" · ")}
        className="inline-flex items-center gap-2 rounded-full border border-emerald-300 px-3 py-1 text-sm text-emerald-700 dark:border-emerald-700 dark:text-emerald-400"
      >
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        可改写
        {storageOk && (
          <span className="text-xs text-emerald-600/70 dark:text-emerald-500/70">
            · 存储就绪
          </span>
        )}
      </span>
    );
  }

  // 后端活着但没模型：评分可用，改写不可用
  return (
    <span
      title={`db: ${db.status} · redis: ${redis.status} · 模型未配置（评分不受影响，改写需在「模型设置」添加供应商）`}
      className="inline-flex items-center gap-2 rounded-full border border-sky-300 px-3 py-1 text-sm text-sky-700 dark:border-sky-800 dark:text-sky-400"
    >
      <span className="h-2 w-2 rounded-full bg-sky-500" />
      API 已连接
      <a
        href="/settings"
        className="text-xs text-sky-600 underline underline-offset-2 hover:text-sky-800 dark:text-sky-400 dark:hover:text-sky-200"
      >
        配置模型
      </a>
    </span>
  );
}
