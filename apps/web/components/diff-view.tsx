"use client";

/**
 * Diff 视图（docs §10.4）：双栏 / 内联两种模式，顶部固定 score before → after。
 */

import { useMemo, useState } from "react";

import { computeDiff, diffStats } from "@/lib/diff";

export interface DiffViewProps {
  original: string;
  rewritten: string;
  scoreBefore: number | null;
  scoreAfter: number | null;
}

type Mode = "split" | "inline";

export function DiffView({ original, rewritten, scoreBefore, scoreAfter }: DiffViewProps) {
  const [mode, setMode] = useState<Mode>("split");
  const parts = useMemo(() => computeDiff(original, rewritten), [original, rewritten]);
  const stats = useMemo(() => diffStats(parts), [parts]);

  const addedCls =
    "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  const removedCls =
    "bg-rose-100 text-rose-900 decoration-rose-400 line-through dark:bg-rose-950 dark:text-rose-200";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        {/* 分数徽章 */}
        {scoreBefore !== null && scoreAfter !== null && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
            AI 味 {scoreBefore}
            <span aria-hidden>→</span>
            <span
              className={
                scoreAfter < scoreBefore
                  ? "text-emerald-600 dark:text-emerald-400"
                  : scoreAfter > scoreBefore
                    ? "text-rose-600 dark:text-rose-400"
                    : ""
              }
            >
              {scoreAfter}
            </span>
            <span className="tabular-nums text-zinc-400">
              （{scoreAfter - scoreBefore >= 0 ? "+" : ""}
              {scoreAfter - scoreBefore}）
            </span>
          </span>
        )}
        <span className="text-xs text-zinc-500">
          +{stats.added} / −{stats.removed} 字符
        </span>
        <div className="ml-auto flex overflow-hidden rounded-lg border border-zinc-200 text-xs dark:border-zinc-700">
          {(["split", "inline"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`px-3 py-1.5 transition-colors ${
                mode === m
                  ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                  : "bg-white text-zinc-600 hover:bg-zinc-50 dark:bg-zinc-950 dark:text-zinc-400 dark:hover:bg-zinc-900"
              }`}
            >
              {m === "split" ? "双栏" : "内联"}
            </button>
          ))}
        </div>
      </div>

      {mode === "split" ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <section className="flex flex-col gap-1.5">
            <h4 className="text-xs font-semibold text-zinc-500">原稿</h4>
            <div className="max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 p-3 text-sm leading-6 text-zinc-700 dark:border-zinc-800 dark:text-zinc-300">
              {parts
                .filter((p) => p.type !== "added")
                .map((p, i) => (
                  <span key={i} className={p.type === "removed" ? removedCls : ""}>
                    {p.text}
                  </span>
                ))}
            </div>
          </section>
          <section className="flex flex-col gap-1.5">
            <h4 className="text-xs font-semibold text-zinc-500">改写稿</h4>
            <div className="max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 p-3 text-sm leading-6 text-zinc-700 dark:border-zinc-800 dark:text-zinc-300">
              {parts
                .filter((p) => p.type !== "removed")
                .map((p, i) => (
                  <span key={i} className={p.type === "added" ? addedCls : ""}>
                    {p.text}
                  </span>
                ))}
            </div>
          </section>
        </div>
      ) : (
        <div className="max-h-[300px] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 p-3 text-sm leading-6 text-zinc-700 dark:border-zinc-800 dark:text-zinc-300">
          {parts.map((p, i) => (
            <span
              key={i}
              className={
                p.type === "added" ? addedCls : p.type === "removed" ? removedCls : ""
              }
            >
              {p.text}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
