"use client";

/**
 * 模型设置页（docs §10.1 的 /settings，M4 扩展）。
 *
 * 交互参照主流 AI 客户端：左侧供应商列表 + 右侧「添加供应商」预设网格。
 * 关键点：
 * - key 由后端加密存储，前端只拿 has_key/key_mask，永不回显明文；
 * - 保存前可「测试连通性」（列模型，不消耗 token）；
 * - 默认供应商全局唯一，改写时自动使用。
 */

import { useCallback, useEffect, useState } from "react";

import {
  createProviderConfig,
  deleteProviderConfig,
  fetchPresets,
  fetchProviderConfigs,
  setDefaultProvider,
  testProviderConfig,
  testProviderDraft,
  updateProviderConfig,
} from "@/lib/api";
import type { ConnectivityResult, ProviderConfig, ProviderPreset } from "@/lib/types";

type View = { mode: "list" } | { mode: "add" } | { mode: "edit"; cfg: ProviderConfig };

const KIND_LABEL: Record<string, string> = {
  openai: "OpenAI 兼容",
  anthropic: "Anthropic",
  ollama: "Ollama 本地",
};

export function SettingsPage() {
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [view, setView] = useState<View>({ mode: "list" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const [cfg, pre] = await Promise.all([fetchProviderConfigs(), fetchPresets()]);
      setConfigs(cfg);
      setPresets(pre);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 用微任务启动，避免在 effect 同步阶段 setState（react-hooks/set-state-in-effect）
    const handle = setTimeout(() => void reload(), 0);
    return () => clearTimeout(handle);
  }, [reload]);

  const handleDelete = async (cfg: ProviderConfig) => {
    setBusy(true);
    try {
      await deleteProviderConfig(cfg.id);
      await reload();
      setView({ mode: "list" });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSetDefault = async (cfg: ProviderConfig) => {
    setBusy(true);
    try {
      await setDefaultProvider(cfg.id);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">模型设置</h1>
          <p className="mt-1 text-sm text-zinc-500">
            管理模型供应商，配置后可在改写时选择使用。密钥加密存储，不回显明文。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void reload()}
            disabled={busy}
            className="rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={() => setView({ mode: "add" })}
            className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            + 添加供应商
          </button>
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300">
          {error}
        </div>
      )}

      {view.mode === "list" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_1fr]">
          {/* 左：已配置列表 */}
          <aside className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              已配置（{configs.length}）
            </h2>
            {loading ? (
              <p className="px-1 py-4 text-sm text-zinc-400">加载中…</p>
            ) : configs.length === 0 ? (
              <p className="px-1 py-4 text-sm text-zinc-400">
                还没有配置供应商。评分不需要模型；改写需要至少一个。
              </p>
            ) : (
              <ul className="flex flex-col gap-1">
                {configs.map((cfg) => (
                  <li key={cfg.id}>
                    <button
                      type="button"
                      onClick={() => setView({ mode: "edit", cfg })}
                      className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-900"
                    >
                      <span
                        className={`h-2 w-2 shrink-0 rounded-full ${
                          cfg.has_key || cfg.kind === "ollama"
                            ? "bg-emerald-500"
                            : "bg-amber-500"
                        }`}
                      />
                      <span className="flex-1 truncate text-sm text-zinc-800 dark:text-zinc-200">
                        {cfg.name}
                      </span>
                      {cfg.is_default && (
                        <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                          默认
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          {/* 右：说明区 */}
          <section className="flex flex-col gap-3 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
            {configs.length === 0 ? (
              <EmptyHint />
            ) : (
              <DefaultSummary configs={configs} busy={busy} onSetDefault={handleSetDefault} />
            )}
          </section>
        </div>
      ) : view.mode === "add" ? (
        <AddProviderPanel
          presets={presets}
          onCancel={() => setView({ mode: "list" })}
          onSaved={async () => {
            await reload();
            setView({ mode: "list" });
          }}
          onError={setError}
        />
      ) : (
        <EditProviderPanel
          cfg={view.cfg}
          busy={busy}
          onCancel={() => setView({ mode: "list" })}
          onSaved={async () => {
            await reload();
            setView({ mode: "list" });
          }}
          onDelete={handleDelete}
          onSetDefault={handleSetDefault}
          onError={setError}
        />
      )}
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
        还没有供应商
      </h3>
      <p className="text-sm leading-6 text-zinc-500">
        点右上角「+ 添加供应商」，从预设里选一个（DeepSeek / 智谱 / Kimi / MiniMax /
        阿里百炼 / Ollama 本地 / 任意 OpenAI 兼容端点），填 key 后即可改写。
      </p>
      <p className="text-sm leading-6 text-zinc-500">
        没有模型也能用：<strong className="text-zinc-700 dark:text-zinc-300">AI 味评分是纯本地的</strong>
        ，不需要任何 key。
      </p>
    </div>
  );
}

function DefaultSummary({
  configs,
  busy,
  onSetDefault,
}: {
  configs: ProviderConfig[];
  busy: boolean;
  onSetDefault: (cfg: ProviderConfig) => void;
}) {
  const current = configs.find((c) => c.is_default) ?? configs[0];
  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">当前默认</h3>
      {current && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-zinc-500">名称</dt>
          <dd className="text-zinc-800 dark:text-zinc-200">{current.name}</dd>
          <dt className="text-zinc-500">类型</dt>
          <dd>{KIND_LABEL[current.kind] ?? current.kind}</dd>
          <dt className="text-zinc-500">端点</dt>
          <dd className="break-all font-mono text-xs text-zinc-600 dark:text-zinc-400">
            {current.base_url || "（SDK 默认）"}
          </dd>
          <dt className="text-zinc-500">模型</dt>
          <dd className="font-mono text-xs">{current.default_model || "（未设置）"}</dd>
          <dt className="text-zinc-500">密钥</dt>
          <dd className="font-mono text-xs">
            {current.has_key ? current.key_mask : current.kind === "ollama" ? "不需要" : "未配置"}
          </dd>
        </dl>
      )}
      {configs.length > 1 && (
        <div className="flex flex-col gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800">
          <p className="text-xs text-zinc-500">切换默认供应商：</p>
          <div className="flex flex-wrap gap-2">
            {configs
              .filter((c) => !c.is_default)
              .map((c) => (
                <button
                  key={c.id}
                  type="button"
                  disabled={busy}
                  onClick={() => onSetDefault(c)}
                  className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
                >
                  设为默认：{c.name}
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AddProviderPanel({
  presets,
  onCancel,
  onSaved,
  onError,
}: {
  presets: ProviderPreset[];
  onCancel: () => void;
  onSaved: () => Promise<void>;
  onError: (msg: string) => void;
}) {
  const [picked, setPicked] = useState<ProviderPreset | null>(null);

  if (!picked) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
          >
            ← 返回
          </button>
          <h2 className="text-lg font-semibold">添加供应商</h2>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPicked(p)}
              className="group flex items-start gap-3 rounded-xl border border-zinc-200 p-4 text-left transition-all hover:border-zinc-400 hover:shadow-sm dark:border-zinc-800 dark:hover:border-zinc-600"
            >
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-sm font-semibold text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                {p.name.slice(0, 1)}
              </span>
              <span className="flex flex-1 flex-col gap-0.5">
                <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">
                  {p.name}
                </span>
                <span className="text-xs text-zinc-500">{p.note}</span>
                {p.models.length > 0 && (
                  <span className="mt-1 font-mono text-[11px] text-zinc-400">
                    {p.models.slice(0, 2).join(" · ")}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <ProviderForm
      preset={picked}
      onCancel={() => setPicked(null)}
      onSaved={onSaved}
      onError={onError}
    />
  );
}

function EditProviderPanel({
  cfg,
  busy,
  onCancel,
  onSaved,
  onDelete,
  onSetDefault,
  onError,
}: {
  cfg: ProviderConfig;
  busy: boolean;
  onCancel: () => void;
  onSaved: () => Promise<void>;
  onDelete: (cfg: ProviderConfig) => Promise<void>;
  onSetDefault: (cfg: ProviderConfig) => Promise<void>;
  onError: (msg: string) => void;
}) {
  return (
    <ProviderForm
      preset={null}
      existing={cfg}
      busy={busy}
      onCancel={onCancel}
      onSaved={onSaved}
      onDelete={onDelete}
      onSetDefault={onSetDefault}
      onError={onError}
    />
  );
}

function ProviderForm({
  preset,
  existing,
  busy = false,
  onCancel,
  onSaved,
  onDelete,
  onSetDefault,
  onError,
}: {
  preset: ProviderPreset | null;
  existing?: ProviderConfig;
  busy?: boolean;
  onCancel: () => void;
  onSaved: () => Promise<void>;
  onDelete?: (cfg: ProviderConfig) => Promise<void>;
  onSetDefault?: (cfg: ProviderConfig) => Promise<void>;
  onError: (msg: string) => void;
}) {
  const isEdit = Boolean(existing);
  const [name, setName] = useState(existing?.name ?? preset?.name ?? "");
  const [kind, setKind] = useState<string>(existing?.kind ?? preset?.kind ?? "openai");
  const [baseUrl, setBaseUrl] = useState(existing?.base_url ?? preset?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(
    existing?.default_model ?? (preset?.models[0] ?? ""),
  );
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<ConnectivityResult | null>(null);

  const needsKey = kind !== "ollama";
  const canSave = name.trim().length > 0 && (!needsKey || isEdit || apiKey.trim().length > 0);

  const handleTest = async () => {
    setTesting(true);
    setResult(null);
    try {
      const key = apiKey.trim() || null;
      const res = isEdit && existing
        ? await testProviderConfig(existing.id)
        : await testProviderDraft({ kind, base_url: baseUrl, api_key: key });
      setResult(res);
      if (res.ok && res.models.length > 0 && !model) setModel(res.models[0]);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (isEdit && existing) {
        const patch: Record<string, unknown> = {
          name,
          kind,
          base_url: baseUrl,
          default_model: model,
        };
        if (apiKey.trim()) patch.api_key = apiKey.trim();
        await updateProviderConfig(existing.id, patch);
      } else {
        await createProviderConfig({
          name,
          kind,
          base_url: baseUrl || null,
          api_key: apiKey.trim() || null,
          default_model: model || null,
        });
      }
      await onSaved();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
        >
          ← 返回
        </button>
        <h2 className="text-lg font-semibold">{isEdit ? "编辑供应商" : `配置：${name}`}</h2>
      </div>

      {preset?.note && <p className="text-xs text-zinc-500">{preset.note}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="显示名称">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={INPUT}
            placeholder="例如：我的 DeepSeek"
          />
        </Field>
        <Field label="接口类型">
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className={INPUT}
          >
            <option value="openai">OpenAI 兼容（含智谱/Kimi/DeepSeek 等）</option>
            <option value="anthropic">Anthropic Claude</option>
            <option value="ollama">Ollama 本地</option>
          </select>
        </Field>
        <Field label="API 端点" hint="OpenAI 兼容地址，通常以 /v1 结尾">
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className={`${INPUT} font-mono text-xs`}
            placeholder={kind === "ollama" ? "http://127.0.0.1:11434" : "https://…/v1"}
          />
        </Field>
        <Field
          label="API Key"
          hint={
            isEdit && existing?.has_key
              ? `已配置（${existing.key_mask}）；留空则不修改`
              : needsKey
                ? "加密存储，不会明文回显"
                : "Ollama 本地无需密钥"
          }
        >
          <input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            type="password"
            autoComplete="off"
            disabled={!needsKey}
            className={`${INPUT} font-mono text-xs disabled:opacity-40`}
            placeholder={isEdit && existing?.has_key ? "（保持不变）" : "sk-…"}
          />
        </Field>
        <Field label="默认模型">
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className={`${INPUT} font-mono text-xs`}
            placeholder="deepseek-chat"
            list="model-suggestions"
          />
          {(preset?.models.length ?? 0) > 0 && (
            <datalist id="model-suggestions">
              {preset?.models.map((m) => <option key={m} value={m} />)}
            </datalist>
          )}
        </Field>
      </div>

      {/* 测试结果 */}
      {result && (
        <div
          className={`rounded-lg border px-3 py-2 text-xs ${
            result.ok
              ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
              : "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300"
          }`}
        >
          {result.ok ? (
            <>
              连接成功，可用模型 {result.models.length} 个
              {result.models.length > 0 && (
                <span className="ml-1 font-mono">
                  （{result.models.slice(0, 4).join(", ")}
                  {result.models.length > 4 ? "…" : ""}）
                </span>
              )}
            </>
          ) : (
            <>连接失败：{result.error}</>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <button
          type="button"
          onClick={() => void handleTest()}
          disabled={testing || (!needsKey && !baseUrl)}
          className="rounded-lg border border-zinc-300 px-3 py-2 text-sm transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
        >
          {testing ? "测试中…" : "测试连通性"}
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={!canSave || saving}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          {saving ? "保存中…" : isEdit ? "保存修改" : "保存"}
        </button>

        {isEdit && existing && (
          <>
            {!existing.is_default && onSetDefault && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onSetDefault(existing)}
                className="ml-auto rounded-lg border border-zinc-300 px-3 py-2 text-sm transition-colors hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
              >
                设为默认
              </button>
            )}
            {onDelete && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDelete(existing)}
                className={`${existing.is_default ? "ml-auto" : ""} rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-600 transition-colors hover:bg-rose-50 disabled:opacity-50 dark:border-rose-800 dark:text-rose-400 dark:hover:bg-rose-950`}
              >
                删除
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const INPUT =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:focus:border-zinc-400";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">{label}</span>
      {children}
      {hint && <span className="text-[11px] text-zinc-400">{hint}</span>}
    </label>
  );
}
