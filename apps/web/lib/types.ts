/**
 * API 契约类型（与 apps/api/src/deaiify/api/schemas.py、engine/models.py 对齐）。
 * 后端 OpenAPI 文档：http://127.0.0.1:8000/docs
 */

export type Band = "natural" | "mild" | "obvious" | "heavy";
export type Severity = "low" | "mid" | "high";
export type GateStatus = "pass" | "weak" | "fail" | "off";
export type Confidence = "low" | "medium" | "high";

export interface Finding {
  dimension: string;
  start: number;
  end: number;
  matched: string;
  reason: string;
  suggestion: string;
  severity: Severity;
}

export interface DimensionScore {
  id: string;
  name: string;
  score: number;
  inverted: boolean;
  explanation: string;
}

export interface TextStats {
  chars: number;
  sentences: number;
  words: number;
  paragraphs: number;
  sent_len_mean: number;
  sent_len_std: number;
  sent_len_cv: number;
  confidence: Confidence;
  lang: string;
}

export interface AnalysisResult {
  score: number;
  band: Band;
  band_label: string;
  dimensions: DimensionScore[];
  findings: Finding[];
  stats: TextStats;
  lang: string;
  engine_version: string;
  /** 识别出的文体（按文体重排维度权重，见后端 engine/register.py） */
  text_register: string;
  text_register_label: string;
  text_register_confidence: number;
}

/* —— 供应商配置（模型设置页）—— */

export interface ProviderPreset {
  id: string;
  name: string;
  kind: "openai" | "anthropic" | "ollama";
  base_url: string;
  needs_key: boolean;
  docs_url: string;
  models: string[];
  note: string;
}

export interface ProviderConfig {
  id: string;
  name: string;
  kind: "openai" | "anthropic" | "ollama";
  base_url: string;
  default_model: string;
  has_key: boolean;
  key_mask: string;
  is_default: boolean;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConnectivityResult {
  ok: boolean;
  models: string[];
  error: string | null;
}

export interface StyleOut {
  id: string;
  name: string;
  description: string;
}

export interface ModelOut {
  id: string;
  provider: string;
  owned_by?: string | null;
}

export interface ProviderOut {
  provider: string;
  available: boolean;
  reason?: string | null;
  models: ModelOut[];
}

export interface ProvidersHealth {
  ready: boolean;
  source: "ui" | "env" | "none";
  count: number;
  default: string | null;
  env_fallback: boolean;
}

export interface HealthData {
  service: string;
  version: string;
  engine_version: string;
  env: string;
  python: string;
  db: { status: string; dialect?: string; detail?: string };
  redis: { status: string; detail?: string };
  providers: ProvidersHealth;
  limits: { max_text_chars: number; batch_concurrency: number };
  time: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string };
}

/* —— 词库（M4）—— */

export type MatchMode = "exact" | "regex" | "contains";

export interface LexiconTerm {
  id: string;
  term: string;
  layer: string;
  match_mode: MatchMode;
  weight: number;
  replacement: string | null;
  enabled: boolean;
}

export interface Lexicon {
  id: string;
  name: string;
  description: string | null;
  lang: string;
  terms: LexiconTerm[];
  created_at: string | null;
  updated_at: string | null;
}

export interface BuiltinInfo {
  total: number;
  disabled: string[];
}

/* —— 改写历史（M4）—— */

export interface HistoryItem {
  id: string;
  style: string;
  model: string;
  lang: string;
  score_before: number;
  score_after: number;
  delta: number;
  text_len: number;
  text_hash: string;
  /** 仅 optin 模式可能非空；never 模式恒为 null（隐私承诺） */
  stored_text: string | null;
  created_at: string | null;
  expires_at: string | null;
}

export interface ClearResult {
  deleted: number;
  store_mode: string;
}

/* —— 批量任务（M4，docs §6.5）—— */

export type BatchItemStatus = "pending" | "running" | "ok" | "failed";
export type BatchJobStatus = "queued" | "running" | "done" | "failed";

export interface BatchItemOut {
  index: number;
  title: string | null;
  status: BatchItemStatus;
  /** 改写结果；仅成功且正文仍在服务进程内时非空（重启后只留摘要） */
  text: string | null;
  score_before: number | null;
  score_after: number | null;
  delta: number | null;
  gate: GateStatus | null;
  gate_reason: string | null;
  attempts: number;
  error: string | null;
}

export interface BatchJobOut {
  job_id: string;
  status: BatchJobStatus;
  total: number;
  /** 成功条数 */
  done: number;
  failed: number;
  /** 尚未出结果（排队 + 运行中） */
  pending: number;
  /** 0–1，按已出结果的条数算 */
  progress: number;
  style: string;
  model: string;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
  items: BatchItemOut[];
}

/* —— SSE 事件载荷（docs §7.3）—— */

export interface SseStart {
  styles: string[];
  before: number;
  model: string;
}

export interface SseDelta {
  style: string;
  text: string;
}

export interface SseRetry {
  style: string;
  attempt: number;
  reason?: string | null;
}

export interface SseVersion {
  style: string;
  text: string;
  gate: GateStatus;
  model: string;
  attempts: number;
  gate_reason?: string | null;
}

export interface SseScore {
  style: string;
  before: number;
  after: number;
  delta: number;
}

export interface SseError {
  code: string;
  message: string;
  style?: string;
}

export interface SseDone {
  versions: number;
  elapsed_ms: number;
}

/** 单个风格的改写结果（含流式过程中的临时态） */
export interface RewriteVersion {
  style: string;
  text: string;
  gate: GateStatus;
  model: string;
  attempts: number;
  gateReason: string | null;
  scoreBefore: number | null;
  scoreAfter: number | null;
  delta: number | null;
  error: string | null;
  streaming: boolean;
}
