"""CLI 测试（M5）：表格对齐、命令行为、退出码。

重点验证中文对齐（display_width 按全角字符计 2 列），
这是 CLI 输出可读性的关键。
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from deaiify.cli import app
from deaiify.cli_output import display_width, pad, score_bar, table, truncate

runner = CliRunner()

AI_TEXT = (
    "在当今社会，人工智能技术正在快速发展。首先，它提升了工作效率；"
    "其次，它降低了运营成本；最后，它优化了用户体验。综上所述，"
    "人工智能具有重要意义，值得我们深入探讨。"
)
HUMAN_TEXT = "我去年换了三次工作，工资从 18k 涨到 26k。说白了，涨薪的秘诀就是敢开口谈。"


# —— 输出工具单测 ——


def test_display_width_counts_cjk_as_two() -> None:
    assert display_width("abc") == 3
    assert display_width("人工智能") == 8  # 4 个全角字符
    assert display_width("AI 味") == 5  # A,I,空格=3 + 味=2
    assert display_width("") == 0


def test_pad_aligns_by_display_width() -> None:
    # 中文字符串补齐后显示宽度应等于目标宽度
    assert display_width(pad("套话", 10)) == 10
    assert display_width(pad("abc", 10)) == 10
    assert display_width(pad("套话", 10, "right")) == 10


def test_table_rows_have_equal_width() -> None:
    rows = [["套话密度", "100", "高"], ["句长均匀度", "62", "中"]]
    out = table(["维度", "分", "备注"], rows)
    lines = [line for line in out.splitlines() if line and not line.startswith("─")]
    # 去掉 ANSI 颜色码后比较（测试环境通常非 TTY，但保险起见）
    import re

    clean = [re.sub(r"\033\[[0-9;]*m", "", line) for line in lines]
    widths = {display_width(line.rstrip()) for line in clean}
    # 允许最后一行因 rstrip 稍短，但不应超过首行
    assert max(widths) - min(widths) <= 2


def test_score_bar_length() -> None:
    assert len(score_bar(0)) == 20
    assert len(score_bar(100)) == 20
    assert score_bar(0).count("█") == 0
    assert score_bar(100).count("█") == 20


def test_truncate_by_display_width() -> None:
    assert display_width(truncate("人工智能技术正在发展", 10)) <= 10
    assert truncate("短", 10) == "短"
    assert truncate("人工智能技术", 6).endswith("…")


# —— 命令行为 ——


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "deaiify" in result.stdout
    assert "engine" in result.stdout


def test_analyze_missing_file_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(tmp_path / "nope.txt")])
    assert result.exit_code == 2


def test_analyze_json_output(tmp_path: Path) -> None:
    f = tmp_path / "ai.txt"
    f.write_text(AI_TEXT, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(f), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["score"] >= 50
    assert len(data["dimensions"]) == 8
    assert "findings" in data
    assert data["text_register"] in {
        "unknown",
        "academic",
        "official",
        "legal",
        "technical",
        "product",
        "news",
        "casual",
    }


def test_analyze_strict_exit_code(tmp_path: Path) -> None:
    """--strict：有 high severity findings 时退出码 1。"""
    f = tmp_path / "ai.txt"
    f.write_text(AI_TEXT, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(f), "--strict"])
    assert result.exit_code == 1


def test_analyze_strict_clean_text_exits_0(tmp_path: Path) -> None:
    f = tmp_path / "human.txt"
    f.write_text(HUMAN_TEXT, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(f), "--strict"])
    assert result.exit_code == 0


def test_analyze_empty_file_exits_2(tmp_path: Path) -> None:
    f = tmp_path / "empty.txt"
    f.write_text("   \n  ", encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(f)])
    assert result.exit_code == 2


def test_analyze_human_readable_output(tmp_path: Path) -> None:
    f = tmp_path / "ai.txt"
    f.write_text(AI_TEXT, encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(f)])
    assert result.exit_code == 0
    assert "AI 味" in result.stdout
    assert "八维" in result.stdout
    # 八维名称应出现
    assert "套话密度" in result.stdout


def test_lex_list_command() -> None:
    result = runner.invoke(app, ["lex", "list"])
    assert result.exit_code == 0
    assert "内置词条总数" in result.stdout
    assert "cliches" in result.stdout


def test_lex_export_command(tmp_path: Path) -> None:
    out = tmp_path / "lex.json"
    result = runner.invoke(app, ["lex", "export", "--out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "cliches.zh" in data
    assert len(data["cliches.zh"]) > 100


def test_lex_export_unknown_layer_exits_2(tmp_path: Path) -> None:
    out = tmp_path / "lex.json"
    result = runner.invoke(app, ["lex", "export", "--out", str(out), "--layer", "nope"])
    assert result.exit_code == 2


def test_rewrite_without_model_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置模型时应以 2 退出（配置错误）。"""
    from deaiify.config import get_settings

    monkeypatch.setenv("DEAIIFY_DEFAULT_MODEL", "")
    get_settings.cache_clear()
    f = tmp_path / "x.txt"
    f.write_text(AI_TEXT, encoding="utf-8")
    result = runner.invoke(app, ["rewrite", str(f)])
    assert result.exit_code == 2
    get_settings.cache_clear()


def test_batch_not_a_directory_exits_2(tmp_path: Path) -> None:
    target = tmp_path / "afile.txt"
    target.write_text("x", encoding="utf-8")
    result = runner.invoke(app, ["batch", str(target), "--out", str(tmp_path / "o")])
    assert result.exit_code == 2
