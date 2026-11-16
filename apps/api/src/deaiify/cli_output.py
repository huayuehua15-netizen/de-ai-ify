"""CLI 输出格式化：表格对齐、JSON 输出、颜色（不引入 rich，控依赖）。

规格见 docs/DEVELOPMENT.md §11：
- 默认人类可读表格（等宽对齐），`--json` 输出结构化供脚本消费；
- 退出码：0 成功 / 1 analyze --strict 时有未处理 findings / 2 配置错误。
"""

import json
import os
import sys
from typing import Any

# —— 颜色（仅在 TTY 且未禁用时启用）——


def _use_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("DEAIIFY_CLI_COLOR") == "0":
        return False
    return sys.stdout.isatty()


class C:
    """ANSI 颜色；非 TTY 时全部降级为空串。"""

    _on = _use_color()
    RESET = "\033[0m" if _on else ""
    BOLD = "\033[1m" if _on else ""
    DIM = "\033[2m" if _on else ""
    RED = "\033[31m" if _on else ""
    GREEN = "\033[32m" if _on else ""
    YELLOW = "\033[33m" if _on else ""
    BLUE = "\033[34m" if _on else ""
    MAGENTA = "\033[35m" if _on else ""
    CYAN = "\033[36m" if _on else ""


BAND_COLOR = {
    "natural": C.GREEN,
    "mild": C.CYAN,
    "obvious": C.YELLOW,
    "heavy": C.RED,
}

SEVERITY_COLOR = {"low": C.DIM, "mid": C.YELLOW, "high": C.RED}


# —— 等宽对齐（中文字符按 2 列宽计算）——


def display_width(text: str) -> int:
    """终端显示宽度：CJK 全角字符计 2，其余计 1。"""
    width = 0
    for ch in text:
        code = ord(ch)
        # 常见 CJK / 全角区间
        if (
            0x1100 <= code <= 0x115F
            or 0x2E80 <= code <= 0xA4CF
            or 0xAC00 <= code <= 0xD7A3
            or 0xF900 <= code <= 0xFAFF
            or 0xFE30 <= code <= 0xFE6F
            or 0xFF00 <= code <= 0xFF60
            or 0xFFE0 <= code <= 0xFFE6
        ):
            width += 2
        else:
            width += 1
    return width


def pad(text: str, width: int, align: str = "left") -> str:
    """按显示宽度补空格（中文对齐的关键）。"""
    gap = max(0, width - display_width(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str:
    """渲染等宽表格（列宽按显示宽度计算）。"""
    if not rows:
        return C.DIM + "（无数据）" + C.RESET
    aligns = aligns or ["left"] * len(headers)
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(str(cell)))

    def line(cells: list[str], sep: str = "  ") -> str:
        return sep.join(pad(str(c), widths[i], aligns[i]) for i, c in enumerate(cells)).rstrip()

    out = [C.BOLD + line(headers) + C.RESET]
    out.append(C.DIM + "  ".join("─" * w for w in widths) + C.RESET)
    for row in rows:
        out.append(line(row))
    return "\n".join(out)


def emit_json(data: Any) -> None:
    """结构化输出（不转义中文，便于管道消费）。"""
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def score_bar(score: int, width: int = 20) -> str:
    """分数条：0-100 映射到 width 个方块。"""
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def truncate(text: str, max_width: int) -> str:
    """按显示宽度截断并加省略号。"""
    if display_width(text) <= max_width:
        return text
    out = ""
    w = 0
    for ch in text:
        cw = display_width(ch)
        if w + cw > max_width - 1:
            break
        out += ch
        w += cw
    return out + "…"
