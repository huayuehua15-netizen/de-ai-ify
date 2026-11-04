"use client";

/**
 * 字数限制指示器：实时显示「已用 / 上限」，接近上限时变色预警。
 *
 * 上限来自后端 /health 的 limits.max_text_chars（可由 DEAIIFY_MAX_TEXT_CHARS 配置），
 * 不在前端硬编码，避免用户改了环境变量后提示与实际校验不一致。
 */

export interface CharLimitProps {
  current: number;
  max: number;
}

export function CharLimit({ current, max }: CharLimitProps) {
  const ratio = max > 0 ? current / max : 0;
  const pct = Math.min(100, Math.round(ratio * 100));
  const over = current > max;
  const near = !over && ratio >= 0.8;

  const barColor = over
    ? "bg-rose-500"
    : near
      ? "bg-amber-500"
      : "bg-emerald-500";
  const textColor = over
    ? "text-rose-600 dark:text-rose-400"
    : near
      ? "text-amber-600 dark:text-amber-400"
      : "text-zinc-500";

  return (
    <div className="flex items-center gap-2" title={`单次最多 ${max.toLocaleString()} 字`}>
      {/* 细进度条：不抢视觉焦点，但一眼看出余量 */}
      <div className="h-1 w-16 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <span className={`tabular-nums text-xs ${textColor}`}>
        {current.toLocaleString()} / {max.toLocaleString()} 字
      </span>
      {over && (
        <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[11px] font-medium text-rose-700 dark:bg-rose-950 dark:text-rose-300">
          超出 {Math.max(0, current - max).toLocaleString()} 字
        </span>
      )}
      {near && (
        <span className="text-[11px] text-amber-600 dark:text-amber-400">
          接近上限
        </span>
      )}
    </div>
  );
}
