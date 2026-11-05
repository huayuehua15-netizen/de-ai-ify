"use client";

/**
 * 词库管理页（docs §10.1 的 /lexicon，M4）。
 *
 * 两块内容：
 *   ① 自定义词库：CRUD、导入导出、词条增删
 *   ② 内置词库：显示总数、停用/恢复条目（停用后该词不再参与评分）
 *
 * 词条归属 layer 决定喂给引擎哪个检测器——UI 里用中文名而非 id，
 * 避免用户面对 cliches/connectives 这类内部标识。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import Link from "next/link";

import {
  addLexiconTerms,
  createLexicon,
  deleteLexicon,
  deleteLexiconTerm,
  exportLexicon,
  fetchBuiltinInfo,
  fetchLexicons,
  importLexicon,
  setBuiltinDisabled,
} from "@/lib/api";
import type { BuiltinInfo, Lexicon, LexiconTerm, MatchMode } from "@/lib/types";

/** 引擎层 id → 用户可读名（顺序与检测器矩阵一致） */
const LAYER_LABEL: Record<string, string> = {
  cliches: "套话短语",
  connectives: "连接词",
  templates: "模板句式（正则）",
  vague: "空泛表达",
  personal: "口语/个性化",
};

const MODE_LABEL: Record<MatchMode, string> = {
  exact: "精确",
  contains: "包含",
  regex: "正则",
};

const INPUT =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:focus:border-zinc-400";
const BTN_PRIMARY =
  "rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300";
const BTN_GHOST =
  "rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900";

export function LexiconPage() {
  const [lexicons, setLexicons] = useState<Lexicon[]>([]);
  const [builtin, setBuiltin] = useState<BuiltinInfo | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [lex, info] = await Promise.all([fetchLexicons(), fetchBuiltinInfo()]);
      setLexicons(lex);
      setBuiltin(info);
      setError(null);
      // 选中项失效时回退到第一项
      setSelectedId((prev) =>
        prev && lex.some((l) => l.id === prev) ? prev : (lex[0]?.id ?? null),
      );
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

  const selected = lexicons.find((l) => l.id === selectedId) ?? null;

  const handleCreate = async (name: string, lang: string) => {
    setBusy(true);
    try {
      const lex = await createLexicon({ name, lang });
      await reload();
      setSelectedId(lex.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (lex: Lexicon) => {
    if (!confirm(`删除词库「${lex.name}」及其 ${lex.terms.length} 条词条？此操作不可撤销。`)) {
      return;
    }
    setBusy(true);
    try {
      await deleteLexicon(lex.id);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">词库管理</h1>
          <p className="mt-1 text-sm text-zinc-500">
            自定义词库参与评分；内置词库可停用条目。改动即时生效，无需重启。
          </p>
        </div>
        <Link href="/" className={BTN_GHOST}>
          ← 回到编辑器
        </Link>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          {error}
        </div>
      )}

      {loading ? (
        <p className="py-8 text-center text-sm text-zinc-400">加载中…</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_1fr]">
          {/* 左：词库列表 */}
          <aside className="flex flex-col gap-3">
            <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
              <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                自定义词库（{lexicons.length}）
              </h2>
              {lexicons.length === 0 ? (
                <p className="px-1 py-3 text-sm text-zinc-400">
                  还没有自定义词库。在下方新建一个。
                </p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {lexicons.map((lex) => (
                    <li key={lex.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(lex.id)}
                        className={`flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors ${
                          lex.id === selectedId
                            ? "bg-zinc-100 dark:bg-zinc-900"
                            : "hover:bg-zinc-50 dark:hover:bg-zinc-900/60"
                        }`}
                      >
                        <span className="flex-1 truncate text-sm text-zinc-800 dark:text-zinc-200">
                          {lex.name}
                        </span>
                        <span className="text-[11px] tabular-nums text-zinc-400">
                          {lex.terms.length}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <CreateLexiconForm busy={busy} onCreate={handleCreate} />
            </div>

            {builtin && (
              <BuiltinPanel
                info={builtin}
                busy={busy}
                onChange={async (terms, disabled) => {
                  setBusy(true);
                  try {
                    const res = await setBuiltinDisabled(terms, disabled);
                    setBuiltin({ ...builtin, disabled: res.disabled });
                  } catch (err) {
                    setError(err instanceof Error ? err.message : String(err));
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            )}
          </aside>

          {/* 右：选中词库详情 */}
          <section className="min-w-0">
            {selected ? (
              <LexiconDetail
                key={selected.id}
                lex={selected}
                busy={busy}
                onChanged={reload}
                onDelete={handleDelete}
                onError={setError}
              />
            ) : (
              <div className="rounded-xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
                左侧选择一个词库，或新建一个
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

/* ============================================================ */

function CreateLexiconForm({
  busy,
  onCreate,
}: {
  busy: boolean;
  onCreate: (name: string, lang: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [lang, setLang] = useState("zh");
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-2 w-full rounded-lg border border-dashed border-zinc-300 py-2 text-xs text-zinc-500 transition-colors hover:border-zinc-400 hover:text-zinc-700 dark:border-zinc-700 dark:hover:border-zinc-600 dark:hover:text-zinc-300"
      >
        + 新建词库
      </button>
    );
  }

  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="词库名称，如「公司黑话」"
        className={INPUT}
        autoFocus
      />
      <select value={lang} onChange={(e) => setLang(e.target.value)} className={INPUT}>
        <option value="zh">中文</option>
        <option value="en">英文</option>
      </select>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!name.trim() || busy}
          onClick={async () => {
            await onCreate(name.trim(), lang);
            setName("");
            setOpen(false);
          }}
          className={`${BTN_PRIMARY} flex-1`}
        >
          创建
        </button>
        <button type="button" onClick={() => setOpen(false)} className={BTN_GHOST}>
          取消
        </button>
      </div>
    </div>
  );
}

/* ============================================================ */

function BuiltinPanel({
  info,
  busy,
  onChange,
}: {
  info: BuiltinInfo;
  busy: boolean;
  onChange: (terms: string[], disabled: boolean) => Promise<void>;
}) {
  const [input, setInput] = useState("");

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        内置词库
      </h2>
      <p className="mb-2 px-1 text-[11px] leading-4 text-zinc-400">
        共 {info.total} 条。停用后该词不再扣分（对所有人生效）。
      </p>
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入要停用的词"
          className={`${INPUT} text-xs`}
        />
        <button
          type="button"
          disabled={!input.trim() || busy}
          onClick={async () => {
            await onChange([input.trim()], true);
            setInput("");
          }}
          className="shrink-0 rounded-lg border border-zinc-300 px-2 text-xs text-zinc-600 transition-colors hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900"
        >
          停用
        </button>
      </div>
      {info.disabled.length > 0 && (
        <div className="mt-2 flex flex-col gap-1">
          <span className="px-1 text-[11px] text-zinc-500">
            已停用 {info.disabled.length} 条：
          </span>
          <div className="flex max-h-32 flex-wrap gap-1 overflow-y-auto">
            {info.disabled.map((t) => (
              <button
                key={t}
                type="button"
                title="点击恢复"
                disabled={busy}
                onClick={() => void onChange([t], false)}
                className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600 transition-colors hover:bg-rose-100 hover:text-rose-700 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:bg-rose-950 dark:hover:text-rose-300"
              >
                {t} ✕
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================ */

function LexiconDetail({
  lex,
  busy,
  onChanged,
  onDelete,
  onError,
}: {
  lex: Lexicon;
  busy: boolean;
  onChanged: () => Promise<void>;
  onDelete: (lex: Lexicon) => Promise<void>;
  onError: (msg: string) => void;
}) {
  const [term, setTerm] = useState("");
  const [layer, setLayer] = useState("cliches");
  const [mode, setMode] = useState<MatchMode>("exact");
  const [adding, setAdding] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importFormat, setImportFormat] = useState<"csv" | "json">("csv");
  const fileRef = useRef<HTMLInputElement>(null);

  const handleAdd = async () => {
    if (!term.trim()) return;
    setAdding(true);
    try {
      await addLexiconTerms(lex.id, [{ term: term.trim(), layer, match_mode: mode }]);
      setTerm("");
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setAdding(false);
    }
  };

  const handleExport = async (fmt: "csv" | "json") => {
    try {
      const text = await exportLexicon(lex.id, fmt);
      const blob = new Blob([text], {
        type: fmt === "csv" ? "text/csv;charset=utf-8" : "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `lexicon-${lex.name}.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{lex.name}</h2>
          <p className="text-xs text-zinc-500">
            {lex.lang === "zh" ? "中文" : "英文"} · {lex.terms.length} 条词条
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void handleExport("csv")} className={BTN_GHOST}>
            导出 CSV
          </button>
          <button type="button" onClick={() => void handleExport("json")} className={BTN_GHOST}>
            导出 JSON
          </button>
          <button
            type="button"
            onClick={() => setImportOpen((v) => !v)}
            className={BTN_GHOST}
          >
            导入
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onDelete(lex)}
            className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-50 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-950"
          >
            删除词库
          </button>
        </div>
      </div>

      {/* 导入区 */}
      {importOpen && (
        <div className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/50">
          <div className="flex items-center gap-2">
            <select
              value={importFormat}
              onChange={(e) => setImportFormat(e.target.value as "csv" | "json")}
              className={`${INPUT} w-auto text-xs`}
            >
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
            <input
              ref={fileRef}
              type="file"
              accept={importFormat === "csv" ? ".csv,text/csv" : ".json,application/json"}
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                setImportText(await f.text());
              }}
              className="flex-1 text-xs text-zinc-500 file:mr-2 file:rounded file:border-0 file:bg-zinc-200 file:px-2 file:py-1 file:text-xs dark:file:bg-zinc-800"
            />
          </div>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={4}
            placeholder={
              importFormat === "csv"
                ? "term,layer,match_mode,weight,replacement\n抓手,cliches,exact,1.0,\n闭环,cliches,exact,,说清楚结果"
                : '{"terms": [{"term": "抓手", "layer": "cliches"}]}'
            }
            className={`${INPUT} font-mono text-xs`}
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!importText.trim() || busy}
              onClick={async () => {
                try {
                  await importLexicon(lex.id, importFormat, importText);
                  setImportText("");
                  setImportOpen(false);
                  await onChanged();
                } catch (err) {
                  onError(err instanceof Error ? err.message : String(err));
                }
              }}
              className={BTN_PRIMARY}
            >
              确认导入
            </button>
            <button type="button" onClick={() => setImportOpen(false)} className={BTN_GHOST}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* 新增词条 */}
      <div className="flex flex-wrap items-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <label className="flex min-w-[160px] flex-1 flex-col gap-1">
          <span className="text-[11px] text-zinc-500">词条</span>
          <input
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleAdd();
            }}
            placeholder="如：抓手 / 赋能.{0,6}生态"
            className={`${INPUT} text-xs`}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-zinc-500">检测层</span>
          <select
            value={layer}
            onChange={(e) => setLayer(e.target.value)}
            className={`${INPUT} w-auto text-xs`}
          >
            {Object.entries(LAYER_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-zinc-500">匹配</span>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as MatchMode)}
            className={`${INPUT} w-auto text-xs`}
          >
            {Object.entries(MODE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!term.trim() || adding}
          onClick={() => void handleAdd()}
          className={BTN_PRIMARY}
        >
          {adding ? "添加中…" : "添加"}
        </button>
      </div>

      {/* 词条列表 */}
      {lex.terms.length === 0 ? (
        <p className="py-6 text-center text-sm text-zinc-400">
          还没有词条。用上方表单添加，或导入 CSV/JSON。
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-zinc-50 text-zinc-500 dark:bg-zinc-900">
              <tr>
                <th className="px-3 py-2 font-medium">词条</th>
                <th className="px-3 py-2 font-medium">检测层</th>
                <th className="px-3 py-2 font-medium">匹配</th>
                <th className="px-3 py-2 font-medium">权重</th>
                <th className="px-3 py-2 font-medium">建议</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {lex.terms.map((t) => (
                <TermRow
                  key={t.id}
                  term={t}
                  lexiconId={lex.id}
                  onDeleted={onChanged}
                  onError={onError}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TermRow({
  term,
  lexiconId,
  onDeleted,
  onError,
}: {
  term: LexiconTerm;
  lexiconId: string;
  onDeleted: () => Promise<void>;
  onError: (msg: string) => void;
}) {
  return (
    <tr className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50">
      <td className="px-3 py-2 font-mono text-zinc-800 dark:text-zinc-200">{term.term}</td>
      <td className="px-3 py-2 text-zinc-500">{LAYER_LABEL[term.layer] ?? term.layer}</td>
      <td className="px-3 py-2 text-zinc-500">{MODE_LABEL[term.match_mode]}</td>
      <td className="px-3 py-2 tabular-nums text-zinc-500">{term.weight}</td>
      <td className="max-w-[180px] truncate px-3 py-2 text-zinc-400">
        {term.replacement || "—"}
      </td>
      <td className="px-3 py-2 text-right">
        <button
          type="button"
          onClick={async () => {
            try {
              await deleteLexiconTerm(lexiconId, term.id);
              await onDeleted();
            } catch (err) {
              onError(err instanceof Error ? err.message : String(err));
            }
          }}
          className="text-zinc-400 transition-colors hover:text-rose-600 dark:hover:text-rose-400"
          title="删除该词条"
        >
          删除
        </button>
      </td>
    </tr>
  );
}
