"use client";

/**
 * 评分面板（docs §10.1）：总分环 + 八维条 + findings 列表。
 * 反向维度（vagueness/personal）以 ↻ 标注，分数含义与正向相反（越高越"缺人味"）。
 */

import type { AnalysisResult, Band, Finding, Severity } from "@/lib/types";

const BAND_COLOR: Record<Band, { ring: string; text: string; badge: string }> = {
  natural: {
    ring: "stroke-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  },
  mild: {
    ring: "stroke-lime-500",
    text: "text-lime-600 dark:text-lime-400",
    badge: "bg-lime-100 text-lime-700 dark:bg-lime-950 dark:text-lime-300",
  },
  obvious: {
    ring: "stroke-orange-500",
    text: "text-orange-600 dark:text-orange-400",
    badge: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  },
  heavy: {
    ring: "stroke-rose-500",
    text: "text-rose-600 dark:text-rose-400",
    badge: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  },
};

const SEV_DOT: Record<Severity, string> = {
  high: "bg-rose-500",
  mid: "bg-amber-500",
  low: "bg-sky-500",
};

const SEV_LABEL: Record<Severity, string> = {
  high: "高",
  mid: "中",
  low: "低",
};

const DIM_ORDER = [
  "cliche",
  "uniformity",
  "connectives",
  "nominalization",
  "repetition",
  "template",
  "vagueness",
  "personal",
] as const;

function findingKey(f: Finding): string {
  return `${f.start}:${f.end}`;
}

function ScoreRing({ score, band }: { score: number; band: Band }) {
  const R = 52;
  const C = 2 * Math.PI * R;
  const color = BAND_COLOR[band];
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
        <circle
          cx="64"
          cy="64"
          r={R}
          fill="none"
          strokeWidth="10"
          className="stroke-zinc-200 dark:stroke-zinc-800"
        />
        <circle
          cx="64"
          cy="64"
          r={R}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={C}
          strokeDashoffset={C * (1 - score / 100)}
          className={`${color.ring} transition-[stroke-dashoffset] duration-500`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-semibold tabular-nums ${color.text}`}>
          {score}
        </span>
        <span className="text-[11px] text-zinc-500">AI 味</span>
      </div>
    </div>
  );
}

export interface ScorePanelProps {
  result: AnalysisResult | null;
  loading: boolean;
  error: string | null;
  activeKey: string | null;
  onFindingClick: (f: Finding) => void;
}

export function ScorePanel({
  result,
  loading,
  error,
  activeKey,
  onFindingClick,
}: ScorePanelProps) {
  if (error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
        评分失败：{error}
      </div>
    );
  }
  if (!result) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-300 p-6 text-center text-sm text-zinc-500 dark:border-zinc-700">
        {loading ? "分析中…" : "粘贴文本后自动评分（纯本地，不上传原文）"}
      </div>
    );
  }

  const color = BAND_COLOR[result.band];
  const dims = [...result.dimensions].sort(
    (a, b) => DIM_ORDER.indexOf(a.id as (typeof DIM_ORDER)[number]) -
      DIM_ORDER.indexOf(b.id as (typeof DIM_ORDER)[number]),
  );

  return (
    <div className="flex flex-col gap-5">
      {/* 总分 + 档位 */}
      <div className="flex items-center gap-4">
        <ScoreRing score={result.score} band={result.band} />
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={`self-start rounded-full px-2.5 py-1 text-xs font-medium ${color.badge}`}
            >
              {result.band_label}
            </span>
            {result.text_register !== "unknown" && (
              <span
                title={`已按「${result.text_register_label}」文体调整各维度权重（置信度 ${Math.round(
                  result.text_register_confidence * 100,
                )}%），避免把该文体的规范表达误判为 AI 味`}
                className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300"
              >
                文体：{result.text_register_label}
              </span>
            )}
            {result.stats.confidence === "low" && (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                样本过短，仅供参考
              </span>
            )}
          </div>
          <p className="text-xs leading-5 text-zinc-500 dark:text-zinc-400">
            {result.stats.chars} 字 · {result.stats.sentences} 句 · 句长 CV{" "}
            {result.stats.sent_len_cv}
          </p>
          <p className="text-xs text-zinc-400 dark:text-zinc-500">
            engine {result.engine_version} · {result.lang}
          </p>
        </div>
      </div>

      {/* 八维条 */}
      <div className="flex flex-col gap-2.5">
        {dims.map((d) => (
          <div key={d.id} className="group/dim">
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {d.name}
                {d.inverted && (
                  <span
                    title="反向计分：信号越少分越高"
                    className="ml-1 cursor-help text-zinc-400"
                  >
                    ↻
                  </span>
                )}
              </span>
              <span className="text-xs tabular-nums text-zinc-500">{d.score}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  d.score >= 75
                    ? "bg-rose-500"
                    : d.score >= 50
                      ? "bg-orange-400"
                      : d.score >= 25
                        ? "bg-lime-400"
                        : "bg-emerald-400"
                }`}
                style={{ width: `${d.score}%` }}
              />
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-zinc-400 group-hover/dim:text-zinc-500 dark:text-zinc-500 dark:group-hover/dim:text-zinc-400">
              {d.explanation}
            </p>
          </div>
        ))}
      </div>

      {/* findings 列表 */}
      <div className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          命中位置（{result.findings.length}）
        </h3>
        {result.findings.length === 0 ? (
          <p className="text-sm text-zinc-500">未命中任何 AI 味特征，很自然。</p>
        ) : (
          <ul className="flex max-h-[360px] flex-col gap-1.5 overflow-y-auto pr-1">
            {result.findings.map((f) => {
              const key = findingKey(f);
              const active = key === activeKey;
              return (
                <li key={key}>
                  <button
                    type="button"
                    onClick={() => onFindingClick(f)}
                    className={`w-full rounded-lg border p-2.5 text-left transition-colors ${
                      active
                        ? "border-zinc-400 bg-zinc-100 dark:border-zinc-500 dark:bg-zinc-900"
                        : "border-zinc-200 bg-white hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-zinc-700 dark:hover:bg-zinc-900"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`h-1.5 w-1.5 shrink-0 rounded-full ${SEV_DOT[f.severity]}`}
                      />
                      <span className="text-[11px] text-zinc-500">
                        {SEV_LABEL[f.severity]}
                      </span>
                      <code className="truncate rounded bg-zinc-100 px-1 text-[11px] text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                        {f.matched}
                      </code>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-zinc-600 dark:text-zinc-400">
                      {f.reason}
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-zinc-400 dark:text-zinc-500">
                      → {f.suggestion}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
