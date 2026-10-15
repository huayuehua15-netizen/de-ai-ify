"""内置风格预设矩阵（docs/DEVELOPMENT.md §6.1）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    description: str
    style_prompt: str


STYLES: dict[str, Style] = {
    s.id: s
    for s in [
        Style(
            id="natural",
            name="自然口语",
            description="去 AI 味、像有经验的朋友在写（默认）",
            style_prompt=(
                "像一个有经验的人在分享：长短句交替、允许自然的语气词（其实、话说回来、说白了），"
                "删掉一切客套与总结腔，多给具体做法和真实判断，读起来轻松但不油滑"
            ),
        ),
        Style(
            id="concise",
            name="简洁直接",
            description="砍掉 20–40% 字数，一句一个信息",
            style_prompt=(
                "极简：删除修饰语与重复表达，一句只说一件事，"
                "禁用名词化绕弯（把“进行了分析”写成“分析了”），结论先行"
            ),
        ),
        Style(
            id="academic",
            name="学术克制",
            description="保留专业性，去掉空话与排比",
            style_prompt=(
                "学术而克制：保留术语、限定语与引用位，判断有据、留有余地；"
                "删除排比、拔高与空泛形容词，不用“众所周知/毋庸置疑”这类断言套话"
            ),
        ),
        Style(
            id="business",
            name="商务简报",
            description="结论先行，量化表达优先",
            style_prompt=(
                "商务简报：每段首句直接给结论，再给依据；用数字和可执行项说话，"
                "删掉背景铺垫与升华号召，语气专业、可直接转发给同事"
            ),
        ),
        Style(
            id="social",
            name="社交媒体",
            description="短平快，钩子开头",
            style_prompt=(
                "社交媒体：开头一句抓人的钩子，句子尽量短，口语化、有观点、有细节，"
                "删掉所有书面客套，结尾可以抛问题引发互动"
            ),
        ),
    ]
}

DEFAULT_STYLE = "natural"


def get_style(style_id: str) -> Style | None:
    return STYLES.get(style_id)
