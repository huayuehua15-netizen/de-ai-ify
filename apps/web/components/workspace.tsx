"use client";

/**
 * 主工作区（docs §10.1、§10.2）：
 *   顶：模型 / 风格 / 隐私徽标
 *   左：编辑器（防抖 600ms → /analyze → 高亮）
 *   右：评分面板（总分环 + 八维 + findings 联动）
 *   底：版本 Tabs + Diff 切换 + 采纳/撤销
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { CharLimit } from "@/components/char-limit";
import { Editor } from "@/components/editor";
import { DiffView } from "@/components/diff-view";
import { ScorePanel } from "@/components/score-panel";
import { VersionTabs } from "@/components/version-tabs";
import {
  ApiError,
  MAX_TEXT_CHARS as FALLBACK_MAX_CHARS,
  analyze,
  fetchHealth,
  fetchProviderConfigs,
  fetchStyles,
} from "@/lib/api";
import { openRewriteStream } from "@/lib/sse";
import type {
  AnalysisResult,
  Finding,
  ProviderConfig,
  RewriteVersion,
  StyleOut,
} from "@/lib/types";

const DEBOUNCE_MS = 600;
const DEFAULT_STYLE_COUNT = 3; // docs §6.1：多版本默认 N=3

/** 空态示例：典型 AI 套话，点一下就能看到评分与高亮效果 */
const EXAMPLE_TEXT =
  "在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；" +
  "其次，它降低了运营成本；最后，它优化了用户体验。综上所述，" +
  "人工智能具有重要意义，值得我们进行深入探讨与研究。";

function emptyVersion(style: string): RewriteVersion {
  return {
    style,
    text: "",
    gate: "off",
    model: "",
    attempts: 1,
    gateReason: null,
    scoreBefore: null,
    scoreAfter: null,
    delta: null,
    error: null,
    streaming: true,
  };
}

export function Workspace() {
  /* —— 文本与评分 —— */
  const [text, setText] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [analyzedText, setAnalyzedText] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const analyzeAbort = useRef<AbortController | null>(null);
  /** 字数上限：初值用兜底常量，拿到 /health 后替换为服务端真实配置 */
  const [maxChars, setMaxChars] = useState<number>(FALLBACK_MAX_CHARS);

  /* —— 目录（风格 / 模型）—— */
  const [styles, setStyles] = useState<StyleOut[]>([]);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);
  const [providerConfigs, setProviderConfigs] = useState<ProviderConfig[]>([]);
  const [selectedConfigId, setSelectedConfigId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [stylesError, setStylesError] = useState<string | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);

  /* —— 改写 —— */
  const [versions, setVersions] = useState<RewriteVersion[]>([]);
  const [activeStyle, setActiveStyle] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const streamAbort = useRef<AbortController | null>(null);

  /* —— Diff 与撤销 —— */
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffBase, setDiffBase] = useState<{ from: string; to: string } | null>(null);
  const [undoStack, setUndoStack] = useState<string | null>(null);
  const [adoptedFrom, setAdoptedFrom] = useState<string | null>(null);

  /* —— 目录加载：风格与模型分成两个独立请求 ——
     /models 含上游可达性探测（可能秒级），不能让它拖死秒回的 /styles，
     否则首屏风格选择器迟迟不出现、还被连坐报错。 */
  useEffect(() => {
    let cancelled = false;
    fetchStyles()
      .then((styleList) => {
        if (cancelled) return;
        setStyles(styleList);
        setSelectedStyles(styleList.slice(0, DEFAULT_STYLE_COUNT).map((s) => s.id));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStylesError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchProviderConfigs()
      .then((configs) => {
        if (cancelled) return;
        setProviderConfigs(configs);
        // 默认选中：默认供应商（后端 is_default）> 第一个
        const def = configs.find((c) => c.is_default) ?? configs[0];
        if (def) {
          setSelectedConfigId(def.id);
          setSelectedModel(def.default_model ?? "");
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setModelsError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* —— 字数上限：以后端配置为准（DEAIIFY_MAX_TEXT_CHARS 可改） —— */
  useEffect(() => {
    let cancelled = false;
    fetchHealth()
      .then((h) => {
        if (cancelled) return;
        const limit = h.limits?.max_text_chars;
        if (typeof limit === "number" && limit > 0) setMaxChars(limit);
      })
      .catch(() => {
        // 拿不到就沿用兜底值，不影响评分
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const enabledConfigs = providerConfigs.filter((c) => c.enabled);
  const anyModelAvailable = enabledConfigs.length > 0;
  const activeConfig = enabledConfigs.find((c) => c.id === selectedConfigId) ?? null;

  /* —— 防抖评分（docs §10.2）——
     effect 只负责调度定时器；清理/请求/写状态全部在回调里做，
     避免 react-hooks/set-state-in-effect。 */
  useEffect(() => {
    if (!text.trim()) return;
    const timer = setTimeout(() => {
      if (text.length > maxChars) {
        setAnalyzeError(`文本超过 ${maxChars.toLocaleString()} 字上限，请拆分后分段评分`);
        return;
      }
      analyzeAbort.current?.abort();
      const ctrl = new AbortController();
      analyzeAbort.current = ctrl;
      setAnalyzing(true);
      analyze(text, { signal: ctrl.signal })
        .then((res) => {
          if (ctrl.signal.aborted) return;
          setAnalysis(res);
          setAnalyzedText(text);
          setAnalyzeError(null);
        })
        .catch((err: unknown) => {
          if (ctrl.signal.aborted || (err instanceof DOMException && err.name === "AbortError")) {
            return;
          }
          setAnalyzeError(
            err instanceof ApiError ? err.message : "无法连接 API（先启动 pnpm dev:api）",
          );
        })
        .finally(() => {
          if (!ctrl.signal.aborted) setAnalyzing(false);
        });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, maxChars]);

  /** 清空文本时同步复位评分状态（由 onChange 触发，非 effect）。 */
  const resetAnalysis = useCallback(() => {
    analyzeAbort.current?.abort();
    setAnalysis(null);
    setAnalyzedText(null);
    setAnalyzeError(null);
    setAnalyzing(false);
  }, []);

  /* —— findings 联动 —— */
  const handleFindingClick = useCallback((f: Finding) => {
    setActiveKey(`${f.start}:${f.end}`);
  }, []);

  /* —— 改写流（docs §7.3）—— */
  const canRewrite =
    text.trim().length > 0 &&
    selectedStyles.length > 0 &&
    anyModelAvailable &&
    !streaming;

  const handleRewrite = useCallback(async () => {
    if (!canRewrite) return;
    streamAbort.current?.abort();
    const ctrl = new AbortController();
    streamAbort.current = ctrl;

    const snapshot = text; // Diff 基准 = 发起改写时的原文
    setStreaming(true);
    setStreamError(null);
    setDiffOpen(false);
    setDiffBase(null);
    setActiveStyle(selectedStyles[0] ?? null);
    setVersions(selectedStyles.map(emptyVersion));

    const patch = (style: string, fn: (v: RewriteVersion) => RewriteVersion) => {
      setVersions((prev) => prev.map((v) => (v.style === style ? fn(v) : v)));
    };

    try {
      await openRewriteStream(
        {
          text: snapshot,
          styles: selectedStyles,
          model: {
            provider: activeConfig?.kind ?? null,
            name: selectedModel || activeConfig?.default_model || null,
            provider_config_id: selectedConfigId,
          },
          gate: true,
        },
        {
          onEvent: ({ event, data }) => {
            let payload: Record<string, unknown>;
            try {
              payload = JSON.parse(data) as Record<string, unknown>;
            } catch {
              return;
            }
            switch (event) {
              case "delta": {
                const s = payload.style as string;
                patch(s, (v) => ({ ...v, text: v.text + (payload.text as string) }));
                break;
              }
              case "retry": {
                // 服务端将重发全文：清空该风格缓冲（docs §7.3）
                const s = payload.style as string;
                patch(s, (v) => ({ ...v, text: "", attempts: 2 }));
                break;
              }
              case "version": {
                const s = payload.style as string;
                patch(s, (v) => ({
                  ...v,
                  text: (payload.text as string) ?? v.text,
                  gate: (payload.gate as RewriteVersion["gate"]) ?? "off",
                  model: (payload.model as string) ?? "",
                  attempts: (payload.attempts as number) ?? 1,
                  gateReason: (payload.gate_reason as string | null) ?? null,
                  streaming: false,
                }));
                break;
              }
              case "score": {
                const s = payload.style as string;
                patch(s, (v) => ({
                  ...v,
                  scoreBefore: payload.before as number,
                  scoreAfter: payload.after as number,
                  delta: payload.delta as number,
                }));
                break;
              }
              case "error": {
                const s = payload.style as string | undefined;
                const message = `${payload.code}: ${payload.message}`;
                if (s) patch(s, (v) => ({ ...v, error: message, streaming: false }));
                else setStreamError(message);
                break;
              }
              case "done":
                break;
              default:
                break;
            }
          },
        },
        ctrl.signal,
      );
      // 流结束时兜底：仍有标记为 streaming 的版本 → 收尾
      setVersions((prev) => prev.map((v) => (v.streaming ? { ...v, streaming: false } : v)));
      setDiffBase({ from: snapshot, to: "" });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const code = (err as { code?: string }).code;
      const message = err instanceof Error ? err.message : String(err);
      setStreamError(
        code === "model_unavailable"
          ? `${message}（在 .env 配置 DEAIIFY_OPENAI_API_KEY / BASE_URL 后重启 API）`
          : message,
      );
      setVersions((prev) => prev.map((v) => (v.streaming ? { ...v, streaming: false, error: message } : v)));
    } finally {
      if (!ctrl.signal.aborted) setStreaming(false);
    }
  }, [canRewrite, activeConfig, selectedConfigId, selectedModel, selectedStyles, text]);

  /* Ctrl/Cmd + Enter 触发改写 */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void handleRewrite();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleRewrite]);

  /* —— 采纳与撤销 —— */
  const handleAdopt = useCallback((v: RewriteVersion) => {
    setUndoStack((prev) => prev ?? text);
    setAdoptedFrom(v.style);
    setText(v.text);
    setActiveStyle(v.style);
    setDiffBase({ from: text, to: v.text });
    setDiffOpen(true);
  }, [text]);

  const handleUndo = useCallback(() => {
    if (undoStack === null) return;
    setText(undoStack);
    setUndoStack(null);
    setAdoptedFrom(null);
  }, [undoStack]);

  const activeVersion =
    versions.find((v) => v.style === activeStyle) ?? versions[0] ?? null;
  const styleName = (id: string) => styles.find((s) => s.id === id)?.name ?? id;
  const diffVersion =
    diffBase && activeVersion && activeVersion.text && activeVersion.style
      ? activeVersion
      : null;

  const toggleStyle = (id: string) => {
    setSelectedStyles((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );
  };

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      {/* 顶栏：左=风格多选 / 右=隐私·模型·主操作 */}
      <div className="sticky top-0 z-10 border-b border-zinc-200/80 bg-white/85 backdrop-blur-md dark:border-zinc-800/80 dark:bg-zinc-950/85">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
          {/* 风格组 */}
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              改写风格
            </span>
            <div className="flex flex-wrap gap-1.5">
              {styles.length === 0 && (
                <span className="text-xs text-zinc-400">
                  {stylesError ? "风格列表加载失败" : "加载中…"}
                </span>
              )}
              {styles.map((s) => {
                const on = selectedStyles.includes(s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    title={s.description}
                    aria-pressed={on}
                    onClick={() => toggleStyle(s.id)}
                    className={`rounded-full border px-2.5 py-1 text-xs transition-all ${
                      on
                        ? "border-zinc-900 bg-zinc-900 font-medium text-white shadow-sm dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                        : "border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
                    }`}
                  >
                    {s.name}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 右侧操作组 */}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span
              title="评分纯本地完成；原文默认不写入数据库"
              className="hidden items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50/60 px-2.5 py-1 text-[11px] text-emerald-700 sm:inline-flex dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-400"
            >
              <svg viewBox="0 0 16 16" className="h-3 w-3" fill="currentColor" aria-hidden>
                <path d="M8 1a3.5 3.5 0 0 0-3.5 3.5V7H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1h-.5V4.5A3.5 3.5 0 0 0 8 1Zm2 6H6V4.5a2 2 0 1 1 4 0V7Z" />
              </svg>
              原文不保存
            </span>
            <a
              href="/settings"
              className="rounded-full border border-zinc-200 bg-white px-2.5 py-1 text-xs text-zinc-600 transition-colors hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400 dark:hover:border-zinc-700 dark:hover:bg-zinc-800"
            >
              模型设置
            </a>
            <select
              value={selectedConfigId ?? ""}
              onChange={(e) => {
                const id = e.target.value;
                setSelectedConfigId(id || null);
                const cfg = providerConfigs.find((c) => c.id === id);
                setSelectedModel(cfg?.default_model ?? "");
              }}
              className="max-w-[220px] rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300"
            >
              <option value="">模型：默认供应商</option>
              {providerConfigs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.is_default ? "（默认）" : ""}
                </option>
              ))}
              {providerConfigs.length === 0 && (
                <option value="" disabled>
                  未配置供应商 → 去「模型设置」
                </option>
              )}
            </select>
            <button
              type="button"
              onClick={() => void handleRewrite()}
              disabled={!canRewrite}
              className="rounded-full bg-zinc-900 px-4 py-1.5 text-xs font-medium text-white shadow-sm transition-all hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
            >
              {streaming ? "改写中…" : `一键改写（${selectedStyles.length}）`}
            </button>
          </div>
        </div>
      </div>

      {/* 未配置模型引导（评分不受影响） */}
      {!anyModelAvailable && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 dark:border-amber-900 dark:bg-amber-950">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-center gap-2 text-xs text-amber-800 dark:text-amber-300">
            <span>
              还没配置模型供应商——<strong>评分照常可用（纯本地）</strong>，改写需要先配一个。
            </span>
            <a
              href="/settings"
              className="rounded-full bg-amber-600 px-3 py-1 font-medium text-white transition-colors hover:bg-amber-700 dark:bg-amber-500 dark:text-amber-950 dark:hover:bg-amber-400"
            >
              去配置 →
            </a>
            {modelsError && (
              <span className="text-amber-600/70 dark:text-amber-500/70">
                （加载失败：{modelsError}）
              </span>
            )}
          </div>
        </div>
      )}

      {/* 主区：编辑器 + 评分面板 */}
      <main className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 gap-5 px-4 py-5 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-h-[480px] flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300">
              原文
              {analysis && (
                <span className="ml-2 text-[11px] font-normal text-zinc-400">
                  命中 {analysis.findings.length} 处
                </span>
              )}
            </h2>
          </div>
          <Editor
            value={text}
            findings={analysis?.findings ?? []}
            analyzedText={analyzedText}
            activeKey={activeKey}
            onChange={(v) => {
              if (!v.trim() && text.trim()) resetAnalysis();
              setText(v);
              setActiveKey(null);
            }}
            onFindingClick={handleFindingClick}
            onUseExample={() => setText(EXAMPLE_TEXT)}
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-zinc-500">
            <CharLimit current={text.length} max={maxChars} />
            {analyzing && (
              <span className="flex items-center gap-1.5 text-zinc-400">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />
                评分中…
              </span>
            )}
            {streamError && (
              <span className="text-rose-600 dark:text-rose-400">改写失败：{streamError}</span>
            )}
            {adoptedFrom && undoStack !== null && (
              <span className="flex items-center gap-2">
                <span className="text-emerald-600 dark:text-emerald-400">
                  已采纳「{styleName(adoptedFrom)}」
                </span>
                <button
                  type="button"
                  onClick={handleUndo}
                  className="underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-300"
                >
                  撤销
                </button>
              </span>
            )}
            <span className="ml-auto hidden items-center gap-1 text-zinc-400 sm:flex">
              <kbd className="rounded border border-zinc-300 px-1 font-mono text-[10px] dark:border-zinc-700">
                Ctrl
              </kbd>
              +
              <kbd className="rounded border border-zinc-300 px-1 font-mono text-[10px] dark:border-zinc-700">
                Enter
              </kbd>
              改写
            </span>
          </div>

          {/* 版本 Tabs + Diff 切换 */}
          {versions.length > 0 && (
            <div className="flex flex-col gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800">
              <VersionTabs
                versions={versions}
                activeStyle={activeStyle}
                onSelect={setActiveStyle}
                onAdopt={handleAdopt}
              />
              {activeVersion?.gateReason && (
                <p className="text-xs text-zinc-500">
                  闸门：{activeVersion.gateReason}
                  {activeVersion.attempts > 1 && "（已自动重试 1 次）"}
                </p>
              )}
              {diffVersion && (
                <button
                  type="button"
                  onClick={() => setDiffOpen((v) => !v)}
                  className="self-start text-xs text-zinc-500 underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-300"
                >
                  {diffOpen ? "收起 Diff" : "查看与原稿的 Diff"}
                </button>
              )}
              {diffOpen && diffVersion && (
                <DiffView
                  original={diffBase?.from ?? text}
                  rewritten={diffVersion.text}
                  scoreBefore={diffVersion.scoreBefore}
                  scoreAfter={diffVersion.scoreAfter}
                />
              )}
            </div>
          )}
        </div>

        <aside className="lg:sticky lg:top-[64px] lg:self-start">
          <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
            <ScorePanel
              result={analysis}
              loading={analyzing}
              error={analyzeError}
              activeKey={activeKey}
              onFindingClick={handleFindingClick}
            />
          </div>
        </aside>
      </main>
    </div>
  );
}
