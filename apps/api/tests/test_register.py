"""文体识别与按文体重权测试（误判修正，engine/register.py + weights_register.py）。

背景（2026-11-04 实测）：`personal`/`vagueness` 是反向维度，对公文/法律/
产品说明这类"天然无第一人称、天然无数字"的正式文体系统性误判——公文
单篇曾达 40 分。修复策略是识别文体后重排维度权重（算法不变）。
"""

import pytest

from deaiify.engine import analyze
from deaiify.engine.register import REGISTER_LABELS, detect_register
from deaiify.engine.weights_register import adjust_weights

ACADEMIC = (
    "综上所述，本研究通过三个实验验证了假设。实验一显示，控制组与实验组在反应时上"
    "存在显著差异（t(48)=3.21，p<0.01）。值得注意的是，这一效应在女性被试中更为明显。"
)
OFFICIAL = (
    "根据《关于加强城乡环境综合治理的实施意见》，各部门要按照职责分工，进一步"
    "压实工作责任。一是健全工作机制，二是强化督导考核，三是加强宣传引导。"
)
LEGAL = (
    "第十二条 当事人订立合同，可以采用书面形式、口头形式或者其他形式。"
    "法律、行政法规规定采用书面形式的，应当采用书面形式。"
)
TECHNICAL = (
    "调用该接口前，请先完成鉴权配置。将 API Key 写入环境变量，然后执行 curl -X POST。"
    "若返回 429，说明触发了限流，建议在客户端加入指数退避重试。"
)
PRODUCT = (
    "使用方法：将本品倒入 500ml 温水，搅拌至完全溶解后饮用。每日一至两次，"
    "建议餐后半小时服用。孕妇及哺乳期妇女请遵医嘱。"
)
NEWS = "本报讯 记者昨日从市卫健委获悉，截至 10 月底，全市已完成加强针接种 42.6 万剂次。"
CASUAL = (
    "去年冬天我回了趟老家。院子里那棵枣树还在，只是比记忆里矮了一截。"
    "我妈说，你走那年它就长这么高了。"
)
AI_SLOP = (
    "在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；其次，它降低了运营成本；"
    "最后，它优化了用户体验。综上所述，人工智能具有重要意义，值得我们深入探讨。"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (ACADEMIC, "academic"),
        (OFFICIAL, "official"),
        (LEGAL, "legal"),
        (TECHNICAL, "technical"),
        (PRODUCT, "product"),
        (NEWS, "news"),
        (CASUAL, "casual"),
    ],
)
def test_register_detection(text: str, expected: str) -> None:
    reg, conf = detect_register(text, "zh")
    assert reg == expected, f"期望 {expected}，实际 {reg}"
    assert 0.0 < conf <= 1.0


def test_register_unknown_for_plain_ai_text() -> None:
    """典型 AI 套话文本没有文体结构标志 → unknown（不调整权重）。"""
    reg, conf = detect_register(AI_SLOP, "zh")
    assert reg == "unknown"
    assert conf == 0.0


def test_register_english_not_detected() -> None:
    reg, conf = detect_register("This is a technical document about API usage.", "en")
    assert reg == "unknown"


def test_adjust_weights_normalizes() -> None:
    base = {"cliche": 0.18, "uniformity": 0.15, "personal": 0.08, "vagueness": 0.10}
    adjusted = adjust_weights(base, "official")
    assert abs(sum(adjusted.values()) - 1.0) < 1e-9
    # 公文的 personal 权重应被显著压低
    assert adjusted["personal"] < base["personal"]


def test_adjust_weights_unknown_passthrough() -> None:
    base = {"cliche": 0.5, "personal": 0.5}
    assert adjust_weights(base, "unknown") == base


def test_official_text_scores_lower_than_without_register() -> None:
    """公文：重权后分数显著低于纯默认权重下的结果（误伤修正的核心断言）。"""
    result = analyze(OFFICIAL)
    assert result.text_register == "official"
    assert result.text_register_label == REGISTER_LABELS["official"]
    # 修复前该文体单篇可达 40 分；修复后应明显回落
    assert result.score < 30


def test_academic_not_penalized_for_proper_connectors() -> None:
    """学术论文的"综上所述/然而"是规范衔接，不应被重罚。"""
    result = analyze(ACADEMIC)
    assert result.text_register == "academic"
    assert result.score < 40, f"学术文本被误判为 {result.score} 分"


def test_casual_still_flagged_when_missing_humanness() -> None:
    """口语文体反过来：缺人味时该更可疑（personal 加权）。

    用口语标志（语气词 + 问句）但通篇无第一人称、句长整齐的文本：
    会被判为 casual，此时 personal 维度权重被放大，分数应高于通用权重。
    """
    flat = "今天天气不错吧？气温也挺适中呢。外出记得带伞啊？以防天气变化嘛。"
    result = analyze(flat)
    assert result.text_register == "casual"
    assert result.score >= 25, f"口语文体缺人味仅得 {result.score} 分，personal 未加权"


def test_ai_slop_still_detected() -> None:
    """误判修正不得削弱 AI 检测能力（AI 样本仍应高分）。"""
    result = analyze(AI_SLOP)
    assert result.score >= 60, f"AI 文本仅得 {result.score} 分，规则被削弱"
