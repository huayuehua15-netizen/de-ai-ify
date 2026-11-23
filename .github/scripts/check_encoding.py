#!/usr/bin/env python3
"""检查仓库里所有被 git 跟踪的文本文件都是合法 UTF-8。

为什么需要这个脚本
------------------
`.gitignore` 不只是给 git 看的。hatchling（本项目的构建后端）在构建 wheel 时
会读它来做 VCS 排除（`load_vcs_exclusion_patterns`），而且是**严格按 UTF-8 解码**：

    UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb9 in position 883

一旦 .gitignore 混进 GBK 字节，`uv sync` 里的 `build_editable` 就会失败，
而错误信息只写 "Call to `hatchling.build.build_editable` failed (exit status: 1)"，
真正的 traceback 在最里层，极难定位。

更隐蔽的是：本地往往因为 venv 里已有 editable 安装而跳过构建，完全复现不出来。
本仓库为此付出过一次长达数小时的 CI 排查。

触发方式是最常见的那种——Windows PowerShell 的 `Add-Content` 默认按系统
ANSI 代码页（简体中文为 GBK）写入，往一个 UTF-8 文件里追加中文注释就会
产生编码混血文件。

这个脚本把这类问题在 CI 的第一秒就挡住，并直接指出是哪个文件的哪个字节。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 二进制文件不参与检查（按扩展名 + 少量已知文件名）
BINARY_SUFFIXES = {
    ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif",
    ".pdf", ".zip", ".gz", ".tar", ".whl", ".woff", ".woff2", ".ttf", ".otf",
    ".mp3", ".mp4", ".webm", ".so", ".dll", ".exe", ".pyc",
}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def main() -> int:
    bad: list[tuple[str, str]] = []

    for name in tracked_files():
        path = Path(name)
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:  # 文件被删/无权限，交给 git status 去报
            print(f"skip {name}: {exc}", file=sys.stderr)
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            # 指出行号，方便直接跳到出事的那一行
            line = data[: exc.start].count(b"\n") + 1
            bad.append((name, f"第 {line} 行，字节偏移 {exc.start}，0x{data[exc.start]:02x}"))

    if not bad:
        print("✓ 所有被跟踪的文本文件均为合法 UTF-8")
        return 0

    print("✗ 发现非 UTF-8 编码的文件：\n", file=sys.stderr)
    for name, detail in bad:
        print(f"  {name}  —— {detail}", file=sys.stderr)
    print(
        "\n修复：把文件重写为无 BOM 的 UTF-8。\n"
        "  PowerShell 不要用 Add-Content / Out-File（默认走系统 ANSI 代码页，\n"
        "  简体中文即 GBK，会写出编码混血文件），改用：\n"
        "    [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))\n"
        "\n为什么这会让构建失败：hatchling 构建 wheel 时严格按 UTF-8 解析 .gitignore，\n"
        "混入 GBK 字节会抛 UnicodeDecodeError，表现为 `uv sync` 里\n"
        "`Call to hatchling.build.build_editable failed`（详见本脚本顶部注释）。",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
