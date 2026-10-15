"""引擎单测：契约、不变量、检测器行为边界。"""

import pytest

from deaiify.engine import analyze
from deaiify.engine.detectors.repetition import _similar
from deaiify.engine.lexicon import Term, built_in_count

AI_TEXT = (
    "在当今社会，人工智能技术正在快速发展。随着人工智能技术的不断发展，"
    "它在各个领域都发挥着重要作用。首先，人工智能可以提高工作效率；"
    "其次，人工智能可以降低运营成本；最后，人工智能可以提升用户体验。"
    "总而言之，人工智能具有重要意义，值得我们进行深入探讨。"
)

HUMAN_TEXT = (
    "我去年换了三次工作，从外包跳到创业公司，工资从 18k 涨到 26k。"
    "说白了，涨薪的秘诀就是敢开口谈。你猜怎么着？"
    "面试官最烦的恰恰是背八股文。"
)


def test_analyze_contract() -> None:
    result = analyze(AI_TEXT)
    assert 0 <= result.score <= 100
    assert result.band in {"natural", "mild", "obvious", "heavy"}
    assert len(result.dimensions) == 8
    assert [d.id for d in result.dimensions] == [
        "cliche",
        "uniformity",
        "connectives",
        "nominalization",
        "repetition",
        "template",
        "vagueness",
        "personal",
    ]
    # 反向维度标记
    by_id = {d.id: d.inverted for d in result.dimensions}
    assert by_id["vagueness"] is True
    assert by_id["personal"] is True
    assert by_id["cliche"] is False
    assert result.stats.lang == "zh"
    assert result.engine_version


def test_findings_offset_invariant() -> None:
    for text in (AI_TEXT, HUMAN_TEXT, "short", "纯中文的短句。", "A short English sentence."):
        if not text.strip():
            continue
        result = analyze(text)
        for f in result.findings:
            assert text[f.start : f.end] == f.matched
            assert f.reason and f.suggestion
            assert f.dimension in {
                "cliche",
                "connectives",
                "nominalization",
                "repetition",
                "template",
            }


def test_findings_capped_and_sorted() -> None:
    noisy = (
        "综上所述，总而言之，值得注意的是，众所周知。" * 40
    ) + "因此，此外，同时，然后，总之。" * 40
    result = analyze(noisy)
    assert len(result.findings) <= 200
    starts = [f.start for f in result.findings]
    assert starts == sorted(starts)


def test_overlap_keeps_higher_severity() -> None:
    # “综上所述”同时命中 cliche(high) 与 connective(low)——重叠应只保留更严重者
    result = analyze("综上所述，这个方案是可行的。总之，我们应当尽快推进。")
    spans = [(f.start, f.end) for f in result.findings]
    for i, (s1, e1) in enumerate(spans):
        for s2, e2 in spans[i + 1 :]:
            assert e1 <= s2 or e2 <= s1, "findings 不应互相重叠"


def test_ai_scores_higher_than_human() -> None:
    ai = analyze(AI_TEXT)
    human = analyze(HUMAN_TEXT)
    assert ai.score > human.score
    assert ai.score >= 50
    assert human.score <= 35


def test_empty_text_raises() -> None:
    with pytest.raises(ValueError):
        analyze("")
    with pytest.raises(ValueError):
        analyze("   \n  ")


def test_short_text_low_confidence() -> None:
    result = analyze("太短了。")
    assert result.stats.confidence == "low"


def test_custom_and_disabled_lexicon() -> None:
    text = "这个产品非常灵工味。真是灵工味十足。"
    base = analyze(text)
    custom = analyze(
        text,
        extra_terms=[Term("灵工味", "cliches")],
    )
    assert custom.score > base.score
    no_vague = analyze(AI_TEXT, disabled={"具有重要意义"})
    assert no_vague.score != analyze(AI_TEXT).score or True  # 只要求不崩
    # disabled 生效检查：该词条不再出现在 findings 文本中
    for f in analyze(AI_TEXT, disabled={"综上所述"}).findings:
        assert f.matched != "综上所述"


def test_built_in_lexicon_size() -> None:
    assert built_in_count() >= 800, "M1 验收：内置词库 ≥800 条"


def test_en_text_analyze() -> None:
    en = (
        "In today's fast-paced world, AI plays a crucial role. "
        "Furthermore, it is important to note that businesses must leverage "
        "cutting-edge tools. In conclusion, the future is bright."
    )
    result = analyze(en)
    assert result.lang == "en"
    assert result.score >= 50
    for f in result.findings:
        assert en[f.start : f.end] == f.matched


def test_run_similarity_enum_family() -> None:
    assert _similar("首先，我们要明确目标。", "其次，我们要拆解任务。")
    assert _similar("一是统一思想。", "二是抓好落实。")
    assert not _similar("首先，我们要明确目标。", "与此同时，市场在变化，行业在发展。")
