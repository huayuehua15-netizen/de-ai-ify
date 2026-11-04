"use client";

/**
 * 高亮编辑器（ADR-6）：真实 textarea 承载输入，镜像层在其下方渲染命中底色。
 *
 * 对齐要点（docs §10.3）：
 * - 两层共享完全相同的字体/字号/行高/内边距/换行规则；
 * - textarea 文字保持可见（中文 IME 组词期间也必须看得见），overlay 只画
 *   <mark> 底色，文字本身透明——由 textarea 的不透明文字盖住，不会重影；
 * - textarea 内容宽度 = 总宽 − 滚动条，overlay 动态补上滚动条宽度；
 * - 滚动时同步 overlay.scrollTop；
 * - 文本与分析结果不一致时（防抖间隙）清空 overlay，避免错位高亮。
 */

import { useCallback, useEffect, useLayoutEffect, useRef } from "react";

import type { Finding, Severity } from "@/lib/types";

/** 两层必须逐项一致的排版类名 */
const TYPO =
  "box-border whitespace-pre-wrap break-words p-5 font-sans text-[15px] leading-[1.7] tracking-normal";

const SEV_CLASS: Record<Severity, string> = {
  high: "bg-rose-200/80 dark:bg-rose-500/30",
  mid: "bg-amber-200/80 dark:bg-amber-400/25",
  low: "bg-sky-200/80 dark:bg-sky-400/25",
};

const SEV_ACTIVE: Record<Severity, string> = {
  high: "shadow-[inset_0_0_0_2px] shadow-rose-500",
  mid: "shadow-[inset_0_0_0_2px] shadow-amber-500",
  low: "shadow-[inset_0_0_0_2px] shadow-sky-500",
};

interface Segment {
  finding: Finding | null;
  text: string;
}

/** 把原文按 findings 切成段（findings 已由后端保证不重叠、按序）。 */
function splitSegments(text: string, findings: Finding[]): Segment[] {
  if (findings.length === 0) return [{ finding: null, text }];
  const segs: Segment[] = [];
  let cursor = 0;
  for (const f of findings) {
    if (f.start < cursor || f.end > text.length) continue; // 容错：越界/重叠丢弃
    if (f.start > cursor) segs.push({ finding: null, text: text.slice(cursor, f.start) });
    segs.push({ finding: f, text: text.slice(f.start, f.end) });
    cursor = f.end;
  }
  if (cursor < text.length) segs.push({ finding: null, text: text.slice(cursor) });
  return segs;
}

export interface EditorProps {
  value: string;
  findings: Finding[];
  /** 分析时的原文；value !== analyzedText 时隐藏高亮（防抖间隙） */
  analyzedText: string | null;
  activeKey: string | null;
  onChange: (value: string) => void;
  onFindingClick: (finding: Finding) => void;
  /** 空态时展示「用示例文本试试」按钮；不传则不显示 */
  onUseExample?: () => void;
}

export function Editor({
  value,
  findings,
  analyzedText,
  activeKey,
  onChange,
  onFindingClick,
  onUseExample,
}: EditorProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const inSync = analyzedText !== null && analyzedText === value;
  const segments = inSync ? splitSegments(value, findings) : [];

  /** 内容宽度对齐：给 overlay 补上 textarea 滚动条占掉的宽度。 */
  const syncMetrics = useCallback(() => {
    const ta = textareaRef.current;
    const ov = overlayRef.current;
    if (!ta || !ov) return;
    const scrollbar = ta.offsetWidth - ta.clientWidth;
    ov.style.paddingRight = `${20 + scrollbar}px`; // 基准 p-5 = 20px
  }, []);

  useLayoutEffect(() => {
    syncMetrics();
  }, [syncMetrics, value]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    const ro = new ResizeObserver(() => syncMetrics());
    ro.observe(ta);
    return () => ro.disconnect();
  }, [syncMetrics]);

  /** 点击/选中高亮区域 → 按光标位置反查 finding（等价于"点 mark 选卡片"）。 */
  const handleSelect = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta || !inSync) return;
    const pos = ta.selectionStart;
    const hit = findings.find((f) => pos >= f.start && pos <= f.end);
    if (hit) onFindingClick(hit);
  }, [findings, inSync, onFindingClick]);

  /** 从卡片定位到原文：滚动到高亮处并选中该片段。 */
  useEffect(() => {
    if (!activeKey) return;
    const ta = textareaRef.current;
    const ov = overlayRef.current;
    if (!ta || !ov) return;
    const [startStr, endStr] = activeKey.split(":");
    const start = Number(startStr);
    const end = Number(endStr);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(start, end);
    const mark = ov.querySelector<HTMLElement>(
      `[data-offset="${start}"]`,
    );
    if (mark) {
      const top = mark.offsetTop - ta.clientHeight / 2;
      ta.scrollTop = Math.max(0, top);
      ov.scrollTop = ta.scrollTop;
    }
  }, [activeKey]);

  const handleScroll = useCallback(() => {
    const ta = textareaRef.current;
    const ov = overlayRef.current;
    if (ta && ov) ov.scrollTop = ta.scrollTop;
  }, []);

  return (
    <div
      ref={wrapRef}
      className="group relative h-full overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors focus-within:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-950 dark:shadow-none dark:focus-within:border-zinc-600"
    >
      {/* 镜像层：只画高亮底色，文字透明由下层 textarea 盖住 */}
      <div
        ref={overlayRef}
        aria-hidden
        className={`pointer-events-none absolute inset-0 overflow-hidden text-transparent ${TYPO}`}
        style={{ paddingRight: 20 }}
      >
        {segments.map((seg, i) =>
          seg.finding ? (
            <mark
              key={`${seg.finding.start}-${i}`}
              data-offset={seg.finding.start}
              data-sev={seg.finding.severity}
              className={`rounded-[2px] text-inherit ${
                SEV_CLASS[seg.finding.severity]
              } ${
                activeKey === `${seg.finding.start}:${seg.finding.end}`
                  ? SEV_ACTIVE[seg.finding.severity]
                  : ""
              }`}
            >
              {seg.text}
            </mark>
          ) : (
            <span key={`t-${i}`}>{seg.text}</span>
          ),
        )}
      </div>

      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={handleScroll}
        onSelect={handleSelect}
        placeholder="把 AI 草稿粘贴到这里……评分即时呈现，改写需先配置模型。"
        spellCheck={false}
        className={`absolute inset-0 h-full w-full resize-none border-0 bg-transparent text-zinc-900 outline-none placeholder:text-zinc-400 dark:text-zinc-100 dark:placeholder:text-zinc-600 ${TYPO}`}
      />

      {/* 空态引导：一键填入示例，降低上手门槛（不覆盖已有内容） */}
      {!value && onUseExample && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-center gap-2 pb-6">
          <button
            type="button"
            onClick={onUseExample}
            className="pointer-events-auto rounded-full border border-zinc-300 bg-white/90 px-3 py-1.5 text-xs text-zinc-600 shadow-sm backdrop-blur transition-colors hover:border-zinc-400 hover:text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900/90 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:text-zinc-200"
          >
            用示例文本试试 →
          </button>
        </div>
      )}
    </div>
  );
}
