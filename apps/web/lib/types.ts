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
  time: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id: string };
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
