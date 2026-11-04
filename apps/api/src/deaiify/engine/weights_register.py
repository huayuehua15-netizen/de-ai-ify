"""按文体的维度权重调整（误判修正，docs §5.4 扩展）。

原则：**维度算法不变，只按文体重排权重**——保证可解释（同一套八维，
不同文体下"什么才叫 AI 味"不同）。实测依据（2026-11-04，21 篇真实文体）：

- 学术：`综上所述/首先/其次/然而/此外` 是规范学术衔接，套话与连接词
  权重应大幅下调；但 AI 味仍会体现在模板骨架与结构重复上，故保留其权重；
- 公文：`一是/二是/三是`、`进一步/扎实推进` 是标准公文语，套话降权；
  反向维度（个性化/空泛度）在公文里天然缺第一人称，**权重压到极低**；
- 法律/产品：同上，反向维度几乎不适用；
- 技术文档：反向维度适度降权（技术文档很少用第一人称）；
- 口语/随笔：反向维度是强信号，**加权**（这类文本缺第一人称才可疑）；
- 新闻：套话降权（新闻有固定表述），其余保持。

调整方式：`weight' = weight × factor`，再整体归一化回 1.0，
保证总分仍在 0-100 且各文体间可比。
"""

# 文体 → {维度 id: 权重倍数}（未列出的维度倍数 = 1.0）
REGISTER_FACTORS: dict[str, dict[str, float]] = {
    "academic": {
        "cliche": 0.35,  # 学术衔接词合法
        "connectives": 0.40,
        "personal": 0.25,  # 论文不用第一人称很正常
        "vagueness": 0.70,  # 学术也常无数字，但比公文更该有具体概念
        "template": 1.30,  # AI 论文最典型的就是模板骨架
        "repetition": 1.25,
    },
    "official": {
        "cliche": 0.30,  # 公文套话是文体规范
        "connectives": 0.45,
        "personal": 0.08,  # 公文天然无第一人称——几乎不该因此扣分
        "vagueness": 0.30,
        "template": 1.10,
    },
    "legal": {
        "cliche": 0.25,
        "connectives": 0.35,
        "personal": 0.05,
        "vagueness": 0.25,
        "uniformity": 0.70,  # 法条句长本就均匀
    },
    "product": {
        "cliche": 0.35,
        "connectives": 0.45,
        "personal": 0.08,
        "vagueness": 0.45,
        "uniformity": 0.75,  # 说明书句式固定
    },
    "technical": {
        "cliche": 0.55,
        "connectives": 0.70,
        "personal": 0.30,  # 技术文档少用第一人称
        "vagueness": 0.60,  # 技术文档常有版本号/参数，但不必然
    },
    "news": {
        "cliche": 0.50,  # 新闻有固定表述（"记者获悉"等）
        "connectives": 0.75,
        "personal": 0.60,
    },
    "casual": {
        "personal": 1.60,  # 口语文本缺人味才最可疑
        "vagueness": 1.20,
        "cliche": 1.10,
    },
}


def adjust_weights(base: dict[str, float], register: str) -> dict[str, float]:
    """按文体调整权重并归一化；unknown/未配置文体原样返回。"""
    factors = REGISTER_FACTORS.get(register)
    if not factors:
        return base

    adjusted = {dim: weight * factors.get(dim, 1.0) for dim, weight in base.items()}
    total = sum(adjusted.values())
    if total <= 0:
        return base
    return {dim: weight / total for dim, weight in adjusted.items()}
