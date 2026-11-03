"use client";

/**
 * 版本 Tabs（docs §10.1 底部）：多风格结果切换 + gate 徽章 + Δ 分数 + 采纳。
 */

import type { GateStatus, RewriteVersion } from "@/lib/types";

const GATE_BADGE: Record<GateStatus, { label: string; cls: string }> = {
  pass: {
    label: "通过",
    cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  },
  weak: {
    label: "弱通过",
    cls: "bg-lime-100 text-lime-700 dark:bg-lime-950 dark:text-lime-300",
  },
  fail: {
    label: "未通过",
    cls: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  },
  off: {
    label: "未校验",
    cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  },
};

export interface VersionTabsProps {
  versions: RewriteVersion[];
  activeStyle: string | null;
  onSelect: (style: string) => void;
  onAdopt: (version: RewriteVersion) => void;
}

export function VersionTabs({ versions, activeStyle, onSelect, onAdopt }: VersionTabsProps) {
  if (versions.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {versions.map((v) => {
        const active = v.style === activeStyle;
        const badge = GATE_BADGE[v.error ? "fail" : v.gate];
        return (
          <div
            key={v.style}
            className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors ${
              active
                ? "border-zinc-400 bg-zinc-100 dark:border-zinc-500 dark:bg-zinc-900"
                : "border-zinc-200 bg-white hover:border-zinc-300 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelect(v.style)}
              className="flex items-center gap-2 text-left"
            >
              <span className="font-medium text-zinc-800 dark:text-zinc-200">{v.style}</span>
              <span className={`rounded-full px-1.5 py-0.5 text-[11px] ${badge.cls}`}>
                {v.error ? "出错" : badge.label}
              </span>
              {v.delta !== null && v.delta !== 0 && (
                <span
                  className={`text-xs tabular-nums ${
                    v.delta < 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-rose-600 dark:text-rose-400"
                  }`}
                >
                  {v.delta > 0 ? "+" : ""}
                  {v.delta}
                </span>
              )}
              {v.streaming && (
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />
              )}
            </button>
            {!v.streaming && !v.error && v.text && (
              <button
                type="button"
                onClick={() => onAdopt(v)}
                title="用这个版本覆盖编辑区"
                className="rounded-md bg-zinc-900 px-2 py-0.5 text-xs text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
              >
                采纳
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
