"""维度 4：名词化倾向（nominalization）——动词动作被名词化绕弯。"""

import re

from deaiify.engine.detectors.base import Context, DetectorResult, clamp, finding

# 「进行/开展……+ 名词」骨架：动作本可直接用动词说
_ZH_PAT = re.compile(
    r"(?:进行|开展|实施|实现|作出|给予|予以|加以)(?:了|着|过)?"
    r"[一-鿿]{0,8}?"
    r"(?:工作|研究|分析|调查|讨论|设计|优化|改进|建设|管理|控制|处理|评价|"
    r"评估|测试|验证|检查|统计|比较|选择|应用|使用|开发|推广|培训|宣传|组织|"
    r"协调|沟通|思考|观察|解读|学习|教育|动员|部署|探索|实践|创新|调研|梳理|"
    r"复盘|迭代|沉淀|转型|升级|改革|开拓|整治|行动|活动|攻关|摸底|冲刺|"
    r"智能化|数字化|自动化|标准化|规范化|精细化)"
)

# 英文 -tion/-ment/-ness/-ity 等后缀（常见无害词剔除）
_EN_PAT = re.compile(r"\b[a-zA-Z]{4,}(?:tion|ments|ment|ness|ity|ence|ance)\b")
_EN_STOP = {
    "information",
    "education",
    "situation",
    "attention",
    "question",
    "function",
    "section",
    "collection",
    "election",
    "reaction",
    "version",
    "region",
    "reason",
    "season",
    "person",
    "system",
    "market",
    "report",
}

_BASELINE = 0.03  # 每句 0.03 以下不计（corpus 校准）
_SATURATION = 0.25  # 每句 0.25 判高


def detect(ctx: Context) -> DetectorResult:
    findings = []
    if ctx.lang == "zh":
        hits = list(_ZH_PAT.finditer(ctx.text))
        spans = [(m.start(), m.end(), m.group(0)) for m in hits]
    else:
        spans = []
        for m in _EN_PAT.finditer(ctx.text):
            if m.group(0).lower() not in _EN_STOP:
                spans.append((m.start(), m.end(), m.group(0)))

    ratio = len(spans) / max(ctx.n_sentences, 1)
    score = clamp((ratio - _BASELINE) / (_SATURATION - _BASELINE) * 100)

    for start, end, matched in spans:
        if ctx.lang == "zh":
            reason = f"名词化表达“{matched}”，绕了一圈才说清动作"
            suggestion = f"改成动词直接说，如“{matched[:2]}…”压缩成一个动词短句"
        else:
            reason = f"Nominalization “{matched}” — nominal form hides the action"
            suggestion = "Use the verb form directly and keep the sentence concrete"
        findings.append(
            finding(
                ctx,
                "nominalization",
                start,
                end,
                reason=reason,
                suggestion=suggestion,
                severity="mid",
            )
        )
    return DetectorResult(
        score=score,
        findings=findings,
        explanation=f"名词化表达 {len(spans)} 处（每句 {ratio:.2f}）",
    )
