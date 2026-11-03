import { HealthBadge } from "@/components/health-badge";
import { Workspace } from "@/components/workspace";

export default function Home() {
  return (
    <div className="flex min-h-dvh flex-col bg-background font-sans">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold tracking-tight">de-ai-ify</span>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
              M3 编辑器 · 开发中
            </span>
          </div>
          <HealthBadge />
        </div>
      </header>

      <Workspace />

      <footer className="border-t border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-zinc-500">
          <span>MIT License · 隐私模式：评分纯本地，默认不保存原文</span>
          <span>
            API 文档：<code className="font-mono">http://127.0.0.1:8000/docs</code>
          </span>
        </div>
      </footer>
    </div>
  );
}
