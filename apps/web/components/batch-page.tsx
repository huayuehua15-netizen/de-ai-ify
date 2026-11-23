"use client";

/**
 * 批量改写页（docs §6.5、§10.1 的 /batch，M4）。
 *
 * 交互模型：
 *   1. 左侧输入面板：粘贴多段（用 `---` 分隔行或空行分组）或选多个 .txt/.md 文件；
 *   2. 右侧进度面板：创建任务后轮询 `GET /batch/{job_id}`，逐条展示状态、分数变化；
 *   3. 刷新页面不丢进度——job_id 写进 URL query（`?job=xxx`），重进自动续看。
 *
 * 隐私语义与单篇一致：正文只存服务进程内存，**DB 里只有哈希/长度/分数**。
 * 因此服务重启后旧任务会明确显示「结果已随重启丢失」，而不是假装还能看。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Link from "next/link";

import { ApiError, createBatch, fetchBatchJob, fetchProviderConfigs, fetchStyles } from "@/lib/api";
import { makeDraft, splitDrafts, type DraftItem } from "@/lib/batch-split";
import type { BatchItemOut, BatchJobOut, ProviderConfig, StyleOut } from "@/lib/types";

const BTN_GHOST =
  "rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900";
const BTN_PRIMARY =
  "rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200";

/** 轮询间隔：批量条目少则快，多了放慢，避免把限流（60 次/分钟）打爆。 */
const POLL_MS = 900;

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

const STATUS_LABEL: Record<BatchItemOut["status"], string> = {
  pending: "排队中",
  running: "改写中",
  ok: "完成",
  failed: "失败",
};

const STATUS_CLASS: Record<BatchItemOut["status"], string> = {
  pending: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
  running: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  ok: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
};

export function BatchPage() {
  const [styles, setStyles] = useState<StyleOut[]>([]);
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);
  const [styleId, setStyleId] = useState<string>("natural");
  const [configId, setConfigId] = useState<string>("");
  const [drafts, setDrafts] = useState<DraftItem[]>([]);
  const [raw, setRaw] = useState("");
  const [job, setJob] = useState<BatchJobOut | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const pollAbort = useRef<AbortController | null>(null);

  const enabledConfigs = useMemo(() => configs.filter((c) => c.enabled), [configs]);
  const activeConfig = enabledConfigs.find((c) => c.id === configId) ?? null;

  /* —— 初始化：风格 + 供应商；URL 里带 job 就续看 —— */
  useEffect(() => {
    let cancelled = false;
    void Promise.all([fetchStyles(), fetchProviderConfigs()])
      .then(([s, c]) => {
        if (cancelled) return;
        setStyles(s);
        setConfigs(c);
        const def = c.find((x) => x.is_default && x.enabled) ?? c.find((x) => x.enabled);
        if (def && !configId) setConfigId(def.id);
        if (s.length > 0 && !s.some((x) => x.id === styleId)) setStyleId(s[0].id);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "无法连接 API（先启动 pnpm dev:api）");
      });

    const fromUrl = new URLSearchParams(window.location.search).get("job");
    if (fromUrl) {
      void fetchBatchJob(fromUrl)
        .then((j) => {
          if (!cancelled) setJob(j);
        })
        .catch(() => {
          // URL 里的任务不存在（过期/清库）就当没有，不打扰用户
        });
    }
    return () => {
      cancelled = true;
    };
    // 只在挂载时跑一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* —— 轮询：只在任务未终态时启动；终态立刻停，别浪费请求额度 —— */
  const jobId = job?.job_id ?? null;
  const jobStatus = job?.status ?? null;
  useEffect(() => {
    if (!jobId || (jobStatus !== "queued" && jobStatus !== "running")) return;
    let cancelled = false;
    const ctrl = new AbortController();
    pollAbort.current = ctrl;

    const tick = async () => {
      try {
        const next = await fetchBatchJob(jobId, ctrl.signal);
        if (cancelled) return;
        setJob(next);
        if (next.status === "queued" || next.status === "running") {
          timer = setTimeout(() => void tick(), POLL_MS);
        }
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) return;
        setError(err instanceof ApiError ? err.message : String(err));
      }
    };

    let timer = setTimeout(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [jobId, jobStatus]);

  const applyRaw = useCallback((text: string) => {
    setRaw(text);
    setDrafts(splitDrafts(text));
  }, []);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const picked = Array.from(files).slice(0, 50);
    const loaded = await Promise.all(
      picked.map(async (f) => {
        const text = await f.text();
        return makeDraft(f.name, text);
      }),
    );
    setDrafts((prev) => [...prev, ...loaded].slice(0, 50));
    setRaw("");
  }, []);

  const removeDraft = useCallback((key: string) => {
    setDrafts((prev) => prev.filter((d) => d.key !== key));
  }, []);

  const totalChars = drafts.reduce((n, d) => n + d.text.length, 0);

  const handleSubmit = useCallback(async () => {
    if (drafts.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createBatch({
        items: drafts.map((d) => ({ text: d.text, title: d.title || null })),
        styles: [styleId],
        model: {
          provider: activeConfig?.kind ?? null,
          name: activeConfig?.default_model || null,
          provider_config_id: configId || null,
        },
        gate: true,
      });
      setJob(created);
      const url = new URL(window.location.href);
      url.searchParams.set("job", created.job_id);
      window.history.replaceState(null, "", url.toString());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [drafts, styleId, activeConfig, configId]);

  const toggleExpand = useCallback((index: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    pollAbort.current?.abort();
    setJob(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("job");
    window.history.replaceState(null, "", url.toString());
  }, []);

  const running = job?.status === "queued" || job?.status === "running";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">批量改写</h1>
          <p className="mt-1 text-sm text-zinc-500">
            一次最多 50 段，并发由服务端控制；单条失败不影响其他条目。
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/" className={BTN_GHOST}>
            ← 回到编辑器
          </Link>
          {job && (
            <button type="button" onClick={reset} className={BTN_GHOST}>
              新建一批
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          {error}
        </div>
      )}

      {job ? (
        <JobPanel
          job={job}
          running={running}
          expanded={expanded}
          onToggle={toggleExpand}
          onReset={reset}
        />
      ) : (
        <>
          {/* 参数行 */}
          <div className="flex flex-wrap items-end gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500">改写风格</span>
              <select
                value={styleId}
                onChange={(e) => setStyleId(e.target.value)}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              >
                {styles.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-zinc-500">模型</span>
              <select
                value={configId}
                onChange={(e) => setConfigId(e.target.value)}
                className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
              >
                <option value="">默认供应商</option>
                {enabledConfigs.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                    {c.is_default ? "（默认）" : ""}
                  </option>
                ))}
              </select>
            </label>
            <span className="ml-auto text-xs text-zinc-500">
              已解析 <strong>{drafts.length}</strong> 段 · 共{" "}
              <strong>{totalChars.toLocaleString()}</strong> 字
            </span>
          </div>

          {/* 输入区 */}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">粘贴多段文本</span>
                <span className="text-xs text-zinc-400">
                  用独占一行的 <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">---</code>{" "}
                  分隔；没有分隔行则按空行分段
                </span>
              </div>
              <textarea
                value={raw}
                onChange={(e) => applyRaw(e.target.value)}
                placeholder={"第一段……\n\n---\n\n第二段……"}
                className="h-64 w-full resize-y rounded-xl border border-zinc-300 bg-white p-3 font-mono text-sm leading-relaxed outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-950 dark:focus:border-zinc-500"
              />
              <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-500">
                <input
                  type="file"
                  multiple
                  accept=".txt,.md,.markdown,text/plain"
                  onChange={(e) => void handleFiles(e.target.files)}
                  className="text-xs"
                />
                或选择多个 .txt / .md 文件（最多 50 个）
              </label>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">待处理清单</span>
                {drafts.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setDrafts([]);
                      setRaw("");
                    }}
                    className="text-xs text-zinc-400 hover:text-rose-500"
                  >
                    清空
                  </button>
                )}
              </div>
              <div className="h-64 overflow-auto rounded-xl border border-zinc-200 dark:border-zinc-800">
                {drafts.length === 0 ? (
                  <p className="p-6 text-center text-sm text-zinc-400">
                    还没有条目。左边粘贴或选择文件后这里会列出来。
                  </p>
                ) : (
                  <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                    {drafts.map((d, i) => (
                      <li key={d.key} className="flex items-start gap-2 px-3 py-2 text-sm">
                        <span className="mt-0.5 w-6 shrink-0 text-xs text-zinc-400">{i + 1}</span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-medium text-zinc-700 dark:text-zinc-300">
                            {d.title}
                          </p>
                          <p className="truncate text-xs text-zinc-400">
                            {d.text.length.toLocaleString()} 字 · {d.text.slice(0, 40)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeDraft(d.key)}
                          className="shrink-0 text-xs text-zinc-400 hover:text-rose-500"
                        >
                          移除
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={submitting || drafts.length === 0}
              onClick={() => void handleSubmit()}
              className={BTN_PRIMARY}
            >
              {submitting ? "提交中…" : `开始改写 ${drafts.length} 段`}
            </button>
            {enabledConfigs.length === 0 && (
              <span className="text-xs text-amber-600 dark:text-amber-400">
                还没有可用的模型供应商，先去{" "}
                <Link href="/settings" className="underline">
                  模型设置
                </Link>{" "}
                配一个。
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

interface JobPanelProps {
  job: BatchJobOut;
  running: boolean;
  expanded: Set<number>;
  onToggle: (index: number) => void;
  onReset: () => void;
}

function JobPanel({ job, running, expanded, onToggle, onReset }: JobPanelProps) {
  const statusText: Record<BatchJobOut["status"], string> = {
    queued: "排队中",
    running: "处理中",
    done: "已完成",
    failed: "失败",
  };
  const tone =
    job.status === "done"
      ? "text-emerald-600 dark:text-emerald-400"
      : job.status === "failed"
        ? "text-rose-600 dark:text-rose-400"
        : "text-sky-600 dark:text-sky-400";

  return (
    <div className="flex flex-col gap-4">
      {/* 进度总览 */}
      <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className={`text-sm font-medium ${tone}`}>{statusText[job.status]}</span>
            <span className="text-xs text-zinc-400">
              {job.done} 成功 / {job.failed} 失败 / {job.pending} 待处理 · 共 {job.total} 段
            </span>
          </div>
          <span className="font-mono text-xs text-zinc-400">{job.job_id.slice(0, 8)}</span>
        </div>

        <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              job.status === "failed" ? "bg-rose-500" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.max(2, Math.round(job.progress * 100))}%` }}
          />
        </div>
        <p className="mt-2 text-xs text-zinc-400">
          {pct(job.progress)} · 风格 {job.style} · 模型 {job.model || "默认"}
          {running && " · 每 0.9 秒自动刷新，可离开本页，回来后进度还在"}
        </p>

        {job.error && (
          <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950 dark:text-rose-300">
            {job.error}
          </p>
        )}
      </div>

      {/* 逐条结果 */}
      <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">标题</th>
              <th className="px-3 py-2 font-medium">状态</th>
              <th className="px-3 py-2 font-medium">AI 味</th>
              <th className="px-3 py-2 font-medium">结果</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {job.items.map((it) => {
              const open = expanded.has(it.index);
              return (
                <tr key={it.index} className="align-top hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
                  <td className="px-3 py-2 text-xs text-zinc-400">{it.index + 1}</td>
                  <td className="max-w-[180px] px-3 py-2">
                    <span className="line-clamp-1 text-zinc-700 dark:text-zinc-300">
                      {it.title || `第 ${it.index + 1} 段`}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] ${STATUS_CLASS[it.status]}`}
                    >
                      {STATUS_LABEL[it.status]}
                    </span>
                    {it.gate && it.gate !== "off" && (
                      <span className="ml-1 text-[11px] text-zinc-400">闸门 {it.gate}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums text-xs">
                    {it.score_before !== null && it.score_after !== null ? (
                      <>
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
                        <span className="ml-1 text-zinc-400">({it.delta})</span>
                      </>
                    ) : (
                      <span className="text-zinc-300 dark:text-zinc-700">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {it.error && (
                      <p className="mb-1 line-clamp-2 text-xs text-rose-600 dark:text-rose-400">
                        {it.error}
                      </p>
                    )}
                    {it.text ? (
                      <>
                        <p
                          className={`whitespace-pre-wrap text-xs text-zinc-600 dark:text-zinc-400 ${
                            open ? "" : "line-clamp-2"
                          }`}
                        >
                          {it.text}
                        </p>
                        <button
                          type="button"
                          onClick={() => onToggle(it.index)}
                          className="mt-1 text-[11px] text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
                        >
                          {open ? "收起" : "展开全文"}
                        </button>
                      </>
                    ) : it.status === "ok" ? (
                      <span className="text-xs text-zinc-400">
                        服务重启后正文不保留（隐私设计）
                      </span>
                    ) : it.status === "failed" ? null : (
                      <span className="text-xs text-zinc-300 dark:text-zinc-700">等待中…</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onReset} className={BTN_GHOST}>
          再来一批
        </button>
        <p className="text-xs text-zinc-400">
          批量任务的正文只存在服务进程内，数据库里只有哈希、长度与分数——
          与单篇改写同一套隐私约定。
        </p>
      </div>
    </div>
  );
}
