"""维度 5：结构重复（repetition）——段首模板复读与连续排比。"""

from deaiify.engine.detectors.base import Context, DetectorResult, clamp, finding
from deaiify.engine.models import Finding
from deaiify.engine.segment import paragraphs_of

_OPEN_LEN = 4  # 段首取前 N 字做重合比较
_RUN_MIN = 3  # 连续排比最少句数
_LEN_TOL = 0.15  # 句长接近带 ±15%（枚举族不受限）
_CN_NUM = "一二三四五六七八九十"

# 序列举头归一化：『首先/其次/最后』『第一/第二』『First/Second…』视为同一 key
_ENUM_PREFIXES = (
    "首先",
    "其次",
    "再次",
    "再者",
    "最后",
    "另外",
    "同时",
    "最后一点",
    "第一",
    "第二",
    "第三",
    "第四",
    "第五",
    "其一",
    "其二",
    "其三",
)
_ENUM_EN = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "finally",
    "lastly",
    "one:",
    "two:",
    "three:",
)


def _is_enum(body: str) -> bool:
    if any(body.startswith(p) for p in _ENUM_PREFIXES):
        return True
    lowered = body.lower()
    if any(lowered.startswith(p) for p in _ENUM_EN):
        return True
    return len(body) >= 2 and body[0] in _CN_NUM and body[1] == "是"


def _opening_key(seg: str) -> str:
    """段首归一化：中英枚举段（首先/First…）视为同构，其余取前 N 字。"""
    body = seg.lstrip()
    if _is_enum(body[:6]):
        return "enum"
    return body[:_OPEN_LEN]


def _sentence_key(text: str) -> str:
    body = text.lstrip()
    if not body:
        return ""
    if _is_enum(body[:6]):
        return "enum"
    if ord(body[0]) < 128:
        # 英文：首词做 key（避免仅凭首字母误合并），大小写不敏感
        word: list[str] = []
        for ch in body:
            if ch.isalpha():
                word.append(ch)
            else:
                break
        return "".join(word).lower()[:8]
    return body[0]


def _similar_kv(ka: str, kb: str, la: int, lb: int) -> bool:
    """基于预计算 key/长度的相似判断（热路径：键只算一次）。"""
    if not ka or ka != kb:
        return False
    # 枚举族（首先/其次/最后、First/Second…）本身就是排比信号，不要求句长接近
    if ka == "enum":
        return True
    return abs(la - lb) <= _LEN_TOL * max(la, lb)


def _similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return _similar_kv(_sentence_key(a), _sentence_key(b), len(a), len(b))


def _find_runs(keys: list[str], lens: list[int]) -> list[tuple[int, int]]:
    """单次扫描找出所有连续同构句组，返回 (start, end) 半开区间。"""
    n = len(keys)
    runs: list[tuple[int, int]] = []
    run_start = 0
    for i in range(1, n + 1):
        if i < n and _similar_kv(keys[i - 1], keys[i], lens[i - 1], lens[i]):
            continue
        if i - run_start >= _RUN_MIN:
            runs.append((run_start, i))
        run_start = i
    return runs


def detect(ctx: Context) -> DetectorResult:
    findings: list[Finding] = []
    text = ctx.text

    # A. 段首模板复读：多段以同样的前几字开头
    openings: dict[str, int] = {}
    paras = paragraphs_of(text)
    for start, end in paras:
        key = _opening_key(text[start:end])
        if len(key.strip()) >= 2:
            openings[key] = openings.get(key, 0) + 1
    dup = sum(c - 1 for c in openings.values() if c > 1)
    s1 = dup / max(len(paras), 1) * 100 if paras else 0.0

    # B. 连续排比：≥3 句同构（枚举族不限句长，其余要求长度接近）
    sents = ctx.sentences
    keys = [_sentence_key(s.text) for s in sents]
    lens = [len(s.text) for s in sents]
    runs = _find_runs(keys, lens)
    covered = sum(e - st for st, e in runs)
    g = covered / max(len(sents), 1)
    s2 = clamp(g * 130)

    score = clamp(max(s1 * 0.9, s2))

    # 排比 findings：每组连续句（除首句）标记为与前句雷同
    for run_start, run_end in runs:
        rlen = run_end - run_start
        for idx in range(run_start + 1, run_end):
            s = sents[idx]
            findings.append(
                finding(
                    ctx,
                    "repetition",
                    s.start,
                    s.end,
                    reason=f"与前句结构雷同（连续 {rlen} 句长度接近、开头相同）",
                    suggestion="变换句长和开头：长短句交替，换个人或事作主语",
                    severity="high",
                )
            )

    return DetectorResult(
        score=score,
        findings=findings,
        explanation=(
            f"段首重复 {dup} 处（{len(paras)} 段）；连续同构句覆盖 {covered}/{len(sents)} 句"
        ),
    )
