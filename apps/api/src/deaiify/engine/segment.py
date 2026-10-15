"""分句、分词与语言判定（规格见 docs/DEVELOPMENT.md §5.2）。

所有切分保留原文字符偏移，供高亮定位使用。
"""

import re
from dataclasses import dataclass

_CJK_RE = re.compile(r"[一-鿿㐀-䶿·]")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*|\d+(?:\.\d+)?")

# 中英文通用句末标点；英文句点单独判定（避免 3.14 / e.g. 误切）
_TERMINATORS = set("。！？!?；;…\n")
_CLOSERS = set("”』」）)]〉》’")


@dataclass(frozen=True)
class Sentence:
    text: str
    start: int
    end: int


def detect_lang(text: str) -> str:
    """CJK 字符占比（非空白字符中）≥15% 判为 zh，否则 en。"""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return "zh"
    cjk = sum(1 for c in chars if _CJK_RE.match(c))
    return "zh" if cjk / len(chars) >= 0.15 else "en"


def _is_terminator(text: str, i: int) -> bool:
    ch = text[i]
    if ch in _TERMINATORS:
        return True
    if ch == ".":
        return i + 1 >= len(text) or text[i + 1].isspace()
    return False


def _push(sentences: list[Sentence], text: str, start: int, end: int) -> None:
    seg = text[start:end]
    if not seg.strip():
        return
    left = len(seg) - len(seg.lstrip())
    right = len(seg.rstrip())
    if right > left:
        sentences.append(Sentence(seg[left:right], start + left, start + right))


def split_sentences(text: str) -> list[Sentence]:
    """按句末标点切句；吞并收尾引号与连续标点；跳过纯空白段。"""
    sentences: list[Sentence] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        if _is_terminator(text, i):
            end = i + 1
            while end < n:
                if text[end] in _CLOSERS:
                    end += 1
                elif _is_terminator(text, end):
                    end += 1
                else:
                    break
            _push(sentences, text, start, end)
            start = end
            i = end
            continue
        i += 1
    _push(sentences, text, start, n)
    return sentences


def count_words(text: str, lang: str) -> int:
    """近似词数：拉丁词元 + 数字，中文按 1.6 字/词折算。

    不走分词以保证 100ms 性能预算（jieba 保留给词库导入与 CLI 场景，见 docs §5.2）。
    """
    latin = len(_WORD_RE.findall(text))
    if lang == "en":
        return latin
    cjk = sum(1 for c in text if _CJK_RE.match(c))
    return latin + (cjk * 5 + 7) // 8  # ≈ cjk / 1.6，整数化


def paragraphs_of(text: str) -> list[tuple[int, int]]:
    """按行分段返回 (start, end) 偏移；跳过过短行。"""
    spans: list[tuple[int, int]] = []
    for m in re.finditer(r"[^\n]+", text):
        if len(m.group(0).strip()) >= 8:
            spans.append((m.start(), m.end()))
    return spans


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, var**0.5
