"""文体识别（register）——解决反向维度的系统性误判。

问题（2026-11-04 实测）：`personal`（第一人称/口语/问句）与 `vagueness`
（数字/专名密度）是反向维度，默认假设"人写文本都有这些信号"。
但公文、法律、产品说明、技术文档**天然不用第一人称、天然没有数字**，
于是恒定拿 100 分——这是最大的误伤来源（实测公文单篇 40 分、法律 30 分）。

解法：先识别文体，再按文体调整维度权重（而不是改维度算法本身，
保证「同一维度、同一算法，不同文体不同解读」的可解释性）。
识别基于各文体的**结构性标志词**，而非单个套话词——单个词不足以判定文体。

识别失败时返回 unknown，权重不做任何调整（保持原行为）。
"""

import re

# 文体 id → 中文名（对外展示，随响应返回，便于用户理解"为什么这个文体扣分不同"）
REGISTER_LABELS: dict[str, str] = {
    "unknown": "通用",
    "academic": "学术论文",
    "official": "公文",
    "legal": "法律条文",
    "technical": "技术文档",
    "product": "产品说明",
    "news": "新闻稿",
    "casual": "口语/随笔",
}

# 各文体的结构标志（命中越多越可信；每类给一组高辨识度正则）
_SIGNALS: dict[str, list[re.Pattern[str]]] = {
    "academic": [
        re.compile(r"本文|本研究|该项?研究|实验(?:组|一|二|结果)|样本"),
        re.compile(r"显著(?:差异|相关|性)|p\s*[<＜]\s*0?\.|信度|效度|变量"),
        re.compile(r"参考文献|文献综述|假设|结论与展望|数据分析|访谈"),
        re.compile(r"采用[^。]{0,12}方法|研究(?:表明|发现|显示)|结果表明"),
    ],
    "official": [
        re.compile(r"一、|二、|三、|四、"),
        re.compile(r"各部门|有关单位|贯彻落实|工作责任|督导|考核|职责分工"),
        re.compile(r"现就[^。]{0,20}通知如下|特此通知|现将[^。]{0,20}印发"),
        re.compile(r"压实|扎实推进|统筹推进|政治站位|形成合力|落地见效"),
    ],
    "legal": [
        re.compile(r"第[一二三四五六七八九十百零]+条"),
        re.compile(r"当事人|用人单位|劳动者|应当|不得|依照|本法|依法承担"),
        re.compile(r"合同|权利|义务|责任|裁定|判决|条例|办法"),
    ],
    "technical": [
        re.compile(r"API|SDK|QPS|HTTP|JSON|Token|接口|端点|参数|返回"),
        re.compile(r"配置|环境变量|调用|部署|编译|依赖|版本|日志"),
        re.compile(r"延迟|吞吐|内存|并发|超时|重试|鉴权|限流"),
        re.compile(r"`[^`]+`"),  # 代码片段
    ],
    "product": [
        re.compile(r"使用方法|用法用量|注意事项|请勿|本品|产品|规格"),
        re.compile(r"每日[一二三]?[至到]?[一二三]?次|温水|服用|清洁|保养"),
        re.compile(r"禁忌|孕妇|儿童|存放|保质期|贮存"),
    ],
    "news": [
        re.compile(r"本报讯|记者|通讯员|获悉|采访"),
        re.compile(r"昨日|日前|当日|开幕式|闭幕|大会|会议召开"),
        re.compile(r"相关负责人|发言人|负责人表示|通报"),
    ],
    "casual": [
        re.compile(r"我(?:们)?|你|咱|俺"),
        # 语气词拆成多条独立标志：中文口语标志密度低，合并一条会漏判
        re.compile(r"[吧呢啊呀嘛]"),
        re.compile(r"[哈喽呗]|咋|啥|甭"),
        re.compile(r"说白了|其实|反正|干脆|话说回来|你猜|讲真"),
        re.compile(r"[？?]"),  # 口语文本常带问句
        # 叙事/抒情标志：散文随笔类没有语气词但有场景化叙述
        re.compile(r"那年|那天|那时候|后来|当时|记得|突然|终于"),
    ],
}

# 判定阈值：命中数达到该值即认为属于该文体（academic 需要 2 个结构标志更稳）
_MIN_HITS: dict[str, int] = {
    "academic": 2,
    "official": 2,
    "legal": 2,
    "technical": 2,
    "product": 2,
    "news": 2,
    "casual": 2,  # 口语文本短，2 个标志即可（"我"+语气词）
}

# 优先级：同一文本可能同时命中多个（公文里也有法律引用），按此顺序取第一个达标者
_PRIORITY = ("legal", "official", "product", "technical", "academic", "news", "casual")


def _count_hits(text: str, patterns: list[re.Pattern[str]]) -> int:
    """统计命中的**不同**标志数（同一标志重复出现只算一次，避免刷分）。"""
    return sum(1 for pat in patterns if pat.search(text))


def detect_register(text: str, lang: str = "zh") -> tuple[str, float]:
    """返回 (文体 id, 置信度 0-1)。英文文本暂不做文体细分（返回 unknown）。

    置信度 = 命中标志数 / 该类标志总数，用于前端展示与后续调权档位。
    """
    if lang != "zh":
        return "unknown", 0.0

    best: tuple[str, float] | None = None
    for reg in _PRIORITY:
        hits = _count_hits(text, _SIGNALS[reg])
        if hits >= _MIN_HITS[reg]:
            conf = min(1.0, hits / max(len(_SIGNALS[reg]), 1) * 1.5)
            best = (reg, round(conf, 2))
            break
    return best if best else ("unknown", 0.0)
