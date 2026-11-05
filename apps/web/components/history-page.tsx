"use client";

/**
 * 改写历史页（docs §10.1 的 /history，M4）。
 *
 * 隐私语义（重点）：
 *   默认 never 模式只落哈希/长度/分数，stored_text 恒为 null——
 *   本页在这种情况下显示"看不到原文是设计如此"，而不是报错或空白。
 *   只有 DEAIIFY_STORE=optin 且当时勾选了保存，才会有原文。
 */

import { useCallback, useEffect, useState } from "react";

import Link from "next/link";

import { clearHistory, fetchHistory } from "@/lib/api";
import type { HistoryItem } from "@/lib/types";

const BTN_GHOST =
  "rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900";

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cleared, setCleared] = useState<number | null>(null);

  const reload = useCallback(async () => {
    try {
      setItems(await fetchHistory(200));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const h = setTimeout(() => void reload(), 0);
    return () => clearTimeout(h);
  }, [reload]);

  const handleClear = async () => {
    if (!confirm("清空全部改写历史？此操作不可撤销。")) return;
    setBusy(true);
    try {
      const res = await clearHistory();
      setCleared(res.deleted);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const hasAnyText = items.some((i) => i.stored_text);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">改写历史</h1>
          <p className="mt-1 text-sm text-zinc-500">
            {hasAnyText
              ? "已开启保存原文（optin）。可随时一键清空。"
              : "隐私模式：只记录分数与哈希，不保存原文内容。"}
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/" className={BTN_GHOST}>
            ← 回到编辑器
          </Link>
          <button
            type="button"
            disabled={busy || items.length === 0}
            onClick={() => void handleClear()}
            className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-40 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-950"
          >
            一键清除
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          {error}
        </div>
      )}

      {cleared !== null && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
          已删除 {cleared} 条历史记录。
        </div>
      )}

      {/* 隐私模式说明 */}
      {!hasAnyText && items.length > 0 && (
        <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300">
          <strong>看不到原文是设计如此。</strong>当前为隐私模式（
          <code className="rounded bg-sky-100 px-1 dark:bg-sky-900">DEAIIFY_STORE=never</code>
          ），数据库只保存文本哈希、长度和分数，不保存内容本身。
          如需保存原文，把它设为 <code className="rounded bg-sky-100 px-1 dark:bg-sky-900">optin</code>
          ，并在改写请求里勾选「保存这次」。
        </div>
      )}

      {loading ? (
        <p className="py-10 text-center text-sm text-zinc-400">加载中…</p>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 p-10 text-center dark:border-zinc-700">
          <p className="text-sm text-zinc-500">还没有改写记录。</p>
          <p className="mt-1 text-xs text-zinc-400">
            去编辑器改写一段文本后，这里会显示分数变化。
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900">
              <tr>
                <th className="px-4 py-2.5 font-medium">时间</th>
                <th className="px-4 py-2.5 font-medium">风格</th>
                <th className="px-4 py-2.5 font-medium">模型</th>
                <th className="px-4 py-2.5 font-medium">AI 味变化</th>
                <th className="px-4 py-2.5 font-medium">字数</th>
                <th className="px-4 py-2.5 font-medium">原文</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {items.map((it) => (
                <tr key={it.id} className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-zinc-500">
                    {fmtTime(it.created_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs dark:bg-zinc-800">
                      {it.style}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-zinc-500">{it.model}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 tabular-nums">
                    <span className="text-zinc-500">{it.score_before}</span>
                    <span className="mx-1 text-zinc-400">→</span>
                    <span
                      className={
                        it.score_after < it.score_before
                          ? "font-medium text-emerald-600 dark:text-emerald-400"
                          : "font-medium text-rose-600 dark:text-rose-400"
                      }
                    >
                      {it.score_after}
                    </span>
                    <span className="ml-1.5 text-xs text-zinc-400">
                      ({it.delta > 0 ? "+" : ""}
                      {it.delta})
                    </span>
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-xs text-zinc-500">
                    {it.text_len}
                  </td>
                  <td className="max-w-[220px] px-4 py-2.5 text-xs">
                    {it.stored_text ? (
                      <span
                        title={it.stored_text}
                        className="line-clamp-1 text-zinc-600 dark:text-zinc-400"
                      >
                        {it.stored_text}
                      </span>
                    ) : (
                      <span className="text-zinc-400">未保存</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-zinc-400">
        共 {items.length} 条记录。文本哈希用于去重统计，无法还原原文。
      </p>
    </div>
  );
}
