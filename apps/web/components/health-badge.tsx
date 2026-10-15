"use client";

import { useEffect, useState } from "react";

type HealthData = {
  service: string;
  version: string;
  engine_version: string;
  db: { status: string };
  redis: { status: string };
};

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
        API 检测中…
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

  const { db, redis } = state.data;
  const healthy = db.status === "ok" && redis.status === "ok";
  return (
    <span
      title={`db: ${db.status} · redis: ${redis.status}`}
      className="inline-flex items-center gap-2 rounded-full border border-emerald-300 px-3 py-1 text-sm text-emerald-700 dark:border-emerald-700 dark:text-emerald-400"
    >
      <span className="h-2 w-2 rounded-full bg-emerald-500" />
      {healthy ? "API · 存储就绪" : "API 已连接"}
    </span>
  );
}
