import { HealthBadge } from "@/components/health-badge";

const FEATURES = [
  {
    title: "AI 味评分",
    desc: "八维度可解释评分：套话、句长均匀度、连接词、名词化、结构重复、模板句式、空泛度、个性化信号。",
  },
  {
    title: "特征高亮",
    desc: "逐处标注命中位置、原因与修改建议，不是黑箱分数。",
  },
  {
    title: "多风格改写",
    desc: "口语 / 简洁 / 学术 / 商务等多版本并行输出，改写后自动重评分展示 Δ。",
  },
  {
    title: "Diff 对比",
    desc: "词级对比原稿与改写稿，采纳前先看清每一处改动。",
  },
  {
    title: "自定义词库",
    desc: "内置词库可停用，支持增删改与 CSV / JSON 导入导出。",
  },
  {
    title: "多模型接入",
    desc: "OpenAI / Anthropic / Ollama / 任意 OpenAI 兼容端点，统一适配层。",
  },
  {
    title: "隐私模式",
    desc: "评分纯本地完成，默认不保存原文，可一键清除历史。",
  },
  {
    title: "多入口",
    desc: "Web、REST API、CLI、Docker 自托管，同一引擎行为一致。",
  },
] as const;

export default function Home() {
  return (
    <div className="flex flex-1 flex-col bg-background font-sans">
      <header className="border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <span className="text-lg font-semibold tracking-tight">
              de-ai-ify
            </span>
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 dark:bg-zinc-900 dark:text-zinc-400">
              M0 骨架 · 开发中
            </span>
          </div>
          <HealthBadge />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6">
        <section className="flex flex-col items-start gap-4 py-16">
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            把 AI 草稿，
            <span className="text-zinc-500 dark:text-zinc-400">
              改成人写的。
            </span>
          </h1>
          <p className="max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-400">
            检测并去除 AI
            文本里的套话、空泛表达、结构重复与均匀句长——先评分解释，再一键改写，改完再验证。
            评分纯本地完成，原文默认不保存，可完全自托管。
          </p>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <span className="cursor-not-allowed rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background opacity-50">
              打开编辑器（M3 开放）
            </span>
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full border border-zinc-300 px-5 py-2.5 text-sm font-medium transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              GitHub
            </a>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 pb-16 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <h3 className="mb-1.5 text-sm font-semibold">{f.title}</h3>
              <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                {f.desc}
              </p>
            </div>
          ))}
        </section>
      </main>

      <footer className="border-t border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2 px-6 py-4 text-sm text-zinc-500 dark:text-zinc-400">
          <span>MIT License · 隐私模式：默认不保存原文</span>
          <span>
            后端 API：<code className="font-mono">http://127.0.0.1:8000/docs</code>
          </span>
        </div>
      </footer>
    </div>
  );
}
