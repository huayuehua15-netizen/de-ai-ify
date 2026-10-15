"""改写服务：构建 Prompt → 调用 provider → 质量闸门 →（失败自动重试一次）。

质量闸门规格见 docs/DEVELOPMENT.md §6.3：
- 事实锚点（数字/拉丁专名）100% 召回，缺失即 fail；
- 字数比 ∈ [0.6, 1.6]，越界即 fail；
- Δscore ≤ -10 通过（pass），-10 < Δ < 0 弱通过（weak），Δ ≥ 0 失败（fail）；
- fail 时注入失败原因自动重试 1 次，仍失败则标记 fail（客户端默认折叠）。
"""

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from deaiify.config import get_settings
from deaiify.engine import analyze
from deaiify.providers.base import ModelProvider, ModelRequest
from deaiify.services.styles import Style

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "rewrite"
_SYSTEM_TMPL = (_PROMPT_DIR / "system.txt").read_text(encoding="utf-8")
_USER_TMPL = (_PROMPT_DIR / "user.txt").read_text(encoding="utf-8")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
# 句首常见大写词不算事实锚点（与 vagueness 检测器保持同一词表口径）
_EN_STOP = {
    "the",
    "this",
    "that",
    "with",
    "for",
    "and",
    "but",
    "not",
    "all",
    "can",
    "will",
    "one",
    "two",
    "how",
    "why",
    "when",
    "what",
    "where",
    "who",
    "are",
    "its",
    "it's",
    "from",
    "into",
    "than",
    "then",
    "these",
    "those",
    "have",
    "has",
    "had",
    "was",
    "were",
    "been",
    "being",
    "may",
    "might",
    "must",
    "should",
    "would",
    "could",
    "also",
    "after",
    "before",
    "during",
}

_MAX_FORBIDDEN = 100  # 注入 prompt 的禁词上限（docs §6.2）

GateStatus = str  # pass | weak | fail | off


@dataclass
class GateVerdict:
    status: GateStatus
    after: int
    delta: int
    reason: str | None = None


@dataclass
class RewriteOutcome:
    style: str
    text: str
    score_before: int
    score_after: int
    delta: int
    gate: GateStatus
    model: str
    usage: dict[str, int] | None
    attempts: int
    gate_reason: str | None = None


def forbidden_terms(lang: str, extra: list[str] | None = None) -> list[str]:
    """禁词清单：内置套话/空泛词 + 用户禁用词，按上限截断（docs §6.2）。"""
    from deaiify.engine.lexicon import build_lexicon

    ls = build_lexicon(lang)
    terms = [t.text for t in ls.hit_terms("cliches")]
    terms += [t.text for t in ls.hit_terms("vague")]
    terms += extra or []
    seen: set[str] = set()
    unique = [t for t in terms if not (t in seen or seen.add(t))]
    return unique[:_MAX_FORBIDDEN]


def build_messages(
    text: str,
    style: Style,
    lang: str,
    *,
    extra_feedback: str = "",
) -> list[dict[str, str]]:
    forbidden = "\n".join(f"- {t}" for t in forbidden_terms(lang))
    system = _SYSTEM_TMPL.format(
        lang_label="中文" if lang == "zh" else "英文",
        forbidden=forbidden,
        style_prompt=style.style_prompt,
    )
    lang_constraint = (
        "语言要求：用自然的简体中文写作，保留原文的中文标点习惯。"
        if lang == "zh"
        else "Language: write in natural English."
    )
    user = _USER_TMPL.format(
        style_constraints=lang_constraint,
        extra_feedback=(extra_feedback + "\n") if extra_feedback else "",
        text=text,
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def extract_anchors(text: str) -> set[str]:
    """事实锚点：数字（含小数）+ 拉丁专名（剔除句首常见词）。"""
    numbers = set(_NUM_RE.findall(text))
    proper = {w for w in _PROPER_RE.findall(text) if w.lower() not in _EN_STOP}
    return numbers | proper


def evaluate_gate(original: str, rewritten: str, score_before: int) -> GateVerdict:
    after = analyze(rewritten).score
    delta = after - score_before

    missing = extract_anchors(original) - extract_anchors(rewritten)
    if missing:
        shown = "、".join(sorted(missing)[:5])
        return GateVerdict("fail", after, delta, f"丢失事实锚点：{shown}")

    len_ratio = len(rewritten) / max(len(original), 1)
    if len_ratio < 0.6 or len_ratio > 1.6:
        return GateVerdict("fail", after, delta, f"字数比 {len_ratio:.2f} 超出 [0.6, 1.6]")

    if delta >= 0:
        return GateVerdict("fail", after, delta, f"评分未下降（{score_before} → {after}）")
    if delta > -10:
        return GateVerdict("weak", after, delta, f"提升有限（{score_before} → {after}）")
    return GateVerdict("pass", after, delta, None)


def _model_request(
    text: str,
    style: Style,
    lang: str,
    model: str,
    *,
    extra_feedback: str = "",
) -> ModelRequest:
    settings = get_settings()
    return ModelRequest(
        messages=build_messages(text, style, lang, extra_feedback=extra_feedback),
        model=model,
        timeout=settings.rewrite_timeout_s,
    )


async def rewrite_one(
    text: str,
    style: Style,
    lang: str,
    provider: ModelProvider,
    model: str,
    *,
    score_before: int,
    use_gate: bool,
) -> RewriteOutcome:
    """非流式改写（并行风格请求由路由层 gather）。"""
    req = _model_request(text, style, lang, model)
    rewritten, usage = await provider.complete(req)

    gate: GateStatus = "off"
    reason: str | None = None
    attempts = 1
    verdict: GateVerdict | None = None
    if use_gate:
        verdict = evaluate_gate(text, rewritten, score_before)
        if verdict.status == "fail":
            # 自动重试一次，注入失败原因（docs §6.3）
            attempts = 2
            retry_hint = (
                f"你上一次的改写未通过校验，原因：{verdict.reason}。请修正该问题后重新输出全文。"
            )
            req2 = _model_request(text, style, lang, model, extra_feedback=retry_hint)
            rewritten, usage = await provider.complete(req2)
            verdict = evaluate_gate(text, rewritten, score_before)
        gate = verdict.status
        reason = verdict.reason

    after = verdict.after if verdict is not None else score_before
    delta = verdict.delta if verdict is not None else 0
    return RewriteOutcome(
        style=style.id,
        text=rewritten,
        score_before=score_before,
        score_after=after,
        delta=delta,
        gate=gate,
        model=model,
        usage=usage.as_dict() or None,
        attempts=attempts,
        gate_reason=reason,
    )


@dataclass
class StreamEvent:
    kind: str  # delta | retry | version | score
    data: dict


async def stream_rewrite(
    text: str,
    style: Style,
    lang: str,
    provider: ModelProvider,
    model: str,
    *,
    score_before: int,
    use_gate: bool,
) -> AsyncIterator[StreamEvent]:
    """流式改写：delta 实时下发；闸门失败自动重试 1 次（先发 retry 让客户端重置缓冲）。"""
    feedback = ""
    attempts = 1
    for attempt in (1, 2):
        req = _model_request(text, style, lang, model, extra_feedback=feedback)
        parts: list[str] = []
        async for chunk in provider.stream(req):
            parts.append(chunk)
            yield StreamEvent("delta", {"style": style.id, "text": chunk})
        rewritten = "".join(parts)

        if not use_gate:
            yield StreamEvent(
                "version",
                {
                    "style": style.id,
                    "text": rewritten,
                    "gate": "off",
                    "model": model,
                    "attempts": attempt,
                },
            )
            yield StreamEvent(
                "score",
                {
                    "style": style.id,
                    "before": score_before,
                    "after": score_before,
                    "delta": 0,
                },
            )
            return

        verdict = evaluate_gate(text, rewritten, score_before)
        if verdict.status == "fail" and attempt == 1:
            attempts = 2
            yield StreamEvent(
                "retry",
                {
                    "style": style.id,
                    "attempt": 2,
                    "reason": verdict.reason,
                },
            )
            feedback = (
                f"你上一次的改写未通过校验，原因：{verdict.reason}。请修正该问题后重新输出全文。"
            )
            continue

        yield StreamEvent(
            "version",
            {
                "style": style.id,
                "text": rewritten,
                "gate": verdict.status,
                "model": model,
                "attempts": attempt,
                "gate_reason": verdict.reason,
            },
        )
        yield StreamEvent(
            "score",
            {
                "style": style.id,
                "before": score_before,
                "after": verdict.after,
                "delta": verdict.delta,
            },
        )
        return
    _ = attempts  # 防御：循环必然 return
