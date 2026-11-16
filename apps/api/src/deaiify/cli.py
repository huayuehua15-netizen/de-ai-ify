"""de-ai-ify CLI（命令规格见 docs/DEVELOPMENT.md §11）。

命令：
    deaiify analyze <file>          评分（--json / --strict）
    deaiify rewrite <file>          改写（--style / --versions / --stream / --out）
    deaiify batch <dir>             批量改写（--out / --concurrency）
    deaiify lex list/add/import/export/disable   词库管理
    deaiify models                  列出各 provider 可达模型
    deaiify serve                   起 API 服务
    deaiify doctor                  环境自检
    deaiify version                 版本

退出码：0 成功 / 1 analyze --strict 且有未处理 findings / 2 配置错误
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from deaiify import __version__
from deaiify.cli_output import (
    BAND_COLOR,
    SEVERITY_COLOR,
    C,
    emit_json,
    score_bar,
    table,
    truncate,
)
from deaiify.config import get_settings
from deaiify.engine import analyze as engine_analyze
from deaiify.engine.version import ENGINE_VERSION

app = typer.Typer(
    help="de-ai-ify CLI：评分 / 改写 / 词库 / 批量 / 服务（docs/DEVELOPMENT.md §11）",
    no_args_is_help=True,
)
lex_app = typer.Typer(help="词库管理（列出 / 添加 / 导入 / 导出 / 停用）", no_args_is_help=True)
app.add_typer(lex_app, name="lex")

# 配置错误统一用 2
EXIT_CONFIG = 2


def _read_text(path: Path) -> str:
    """读文本文件；不存在或不可读时以配置错误退出。"""
    if not path.exists():
        typer.secho(f"文件不存在：{path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        typer.secho(f"文件不是 UTF-8 编码：{path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG) from None


# ============================================================
# version / doctor
# ============================================================


@app.command()
def version() -> None:
    """显示应用与评分引擎版本。"""
    typer.echo(f"deaiify {__version__} (engine {ENGINE_VERSION})")


@app.command()
def doctor() -> None:
    """环境自检：配置摘要与存储连通性（终端侧见 pnpm check:env）。"""
    from deaiify.api.routers.health import check_db, check_redis

    settings = get_settings()
    typer.echo(f"deaiify {__version__} (engine {ENGINE_VERSION})")
    typer.echo(f"env={settings.env} store={settings.store}")

    db = asyncio.run(check_db())
    redis = asyncio.run(check_redis())
    typer.echo(f"db={db['status']} ({db.get('dialect') or db.get('detail', '-')})")
    typer.echo(f"redis={redis['status']} ({redis.get('detail', '-')})")

    if db["status"] != "ok":
        raise typer.Exit(code=1)


# ============================================================
# analyze
# ============================================================


@app.command()
def analyze(
    path: Annotated[Path, typer.Argument(help="待评分文本文件（UTF-8）")],
    json_out: Annotated[bool, typer.Option("--json", help="输出 JSON（供脚本消费）")] = False,
    strict: Annotated[
        bool, typer.Option("--strict", help="有任何 high severity 命中即以 1 退出")
    ] = False,
    lang: Annotated[str, typer.Option(help="auto / zh / en")] = "auto",
    top: Annotated[int, typer.Option(help="最多显示多少条 findings")] = 20,
) -> None:
    """对文本做 AI 味评分与高亮。"""
    text = _read_text(path)
    if not text.strip():
        typer.secho("文件为空", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG)

    result = engine_analyze(text, lang=lang)

    if json_out:
        emit_json(json.loads(result.model_dump_json()))
        if strict and any(f.severity == "high" for f in result.findings):
            raise typer.Exit(1)
        return

    color = BAND_COLOR.get(result.band, "")
    typer.echo()
    typer.echo(
        f"  {C.BOLD}AI 味{C.RESET}  {color}{C.BOLD}{result.score}{C.RESET}"
        f"  {score_bar(result.score)}  {color}{result.band_label}{C.RESET}"
    )
    if result.text_register != "unknown":
        typer.echo(
            f"  {C.DIM}文体 {result.text_register_label}"
            f"（置信度 {result.text_register_confidence:.0%}，已按文体重排权重）{C.RESET}"
        )
    st = result.stats
    typer.echo(
        f"  {C.DIM}{st.chars} 字 · {st.sentences} 句 · 句长 {st.sent_len_mean}"
        f" ± {st.sent_len_std}（CV {st.sent_len_cv}） · 置信度 {st.confidence}{C.RESET}"
    )

    typer.echo()
    typer.echo(f"  {C.BOLD}八维{C.RESET}")
    rows = [
        [d.name + (" ↻" if d.inverted else ""), str(d.score), score_bar(d.score, 16), d.explanation]
        for d in result.dimensions
    ]
    typer.echo(table(["维度", "分", "分布", "说明"], rows, ["left", "right", "left", "left"]))

    typer.echo()
    shown = min(top, len(result.findings))
    typer.echo(f"  {C.BOLD}命中 {len(result.findings)} 处{C.RESET}（显示前 {shown}）")
    if not result.findings:
        typer.echo(f"  {C.GREEN}未命中任何 AI 味特征，很自然。{C.RESET}")
    else:
        frows = []
        for f in result.findings[:top]:
            sev = SEVERITY_COLOR.get(f.severity, "")
            frows.append(
                [
                    f"{sev}{f.severity}{C.RESET}",
                    f.dimension,
                    truncate(f.matched, 18),
                    truncate(f.reason, 34),
                ]
            )
        typer.echo(table(["严重度", "维度", "命中", "原因"], frows))

    typer.echo()
    high = sum(1 for f in result.findings if f.severity == "high")
    if high:
        typer.secho(f"  {high} 处 high severity", fg=typer.colors.YELLOW)
    typer.echo(f"  {C.DIM}engine {result.engine_version}{C.RESET}")
    typer.echo()

    if strict and high:
        raise typer.Exit(1)


# ============================================================
# rewrite
# ============================================================


@app.command()
def rewrite(
    path: Annotated[Path, typer.Argument(help="待改写文本文件（UTF-8）")],
    style: Annotated[
        str, typer.Option("--style", "-s", help="风格 id：natural/concise/academic/business/social")
    ] = "natural",
    versions: Annotated[
        int, typer.Option("--versions", "-n", help="生成几个版本（同风格重复采样）")
    ] = 1,
    stream: Annotated[bool, typer.Option("--stream", help="流式输出（打字机效果）")] = False,
    out: Annotated[
        Path | None, typer.Option("--out", "-o", help="输出目录；不给则打印到 stdout")
    ] = None,
    model: Annotated[str | None, typer.Option("--model", help="模型名；默认取配置")] = None,
    provider: Annotated[
        str | None, typer.Option("--provider", help="openai/anthropic/ollama")
    ] = None,
    gate: Annotated[bool, typer.Option("--gate/--no-gate", help="是否启用质量闸门")] = True,
) -> None:
    """改写文本并（默认）走质量闸门重评分。"""
    from deaiify.providers.base import ProviderError
    from deaiify.providers.registry import get_provider
    from deaiify.services.rewrite import rewrite_one
    from deaiify.services.styles import get_style

    text = _read_text(path)
    st = get_style(style)
    if st is None:
        typer.secho(
            f"未知风格 {style}（可用：natural/concise/academic/business/social）",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(EXIT_CONFIG)

    settings = get_settings()
    model_name = model or settings.default_model
    if not model_name:
        typer.secho(
            "未指定模型：用 --model 或设置 DEAIIFY_DEFAULT_MODEL",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(EXIT_CONFIG)

    try:
        prov = get_provider(provider)
    except ProviderError as exc:
        typer.secho(f"{exc.code}: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG) from None

    before = engine_analyze(text)

    async def _run_one() -> tuple[str, int, int, str]:
        outcome = await rewrite_one(
            text, st, before.lang, prov, model_name, score_before=before.score, use_gate=gate
        )
        return outcome.text, outcome.score_after, outcome.delta, outcome.gate

    async def _run_stream() -> tuple[str, int, int, str]:
        from deaiify.services.rewrite import stream_rewrite

        parts: list[str] = []
        last_after, last_delta, last_gate = before.score, 0, "off"
        async for ev in stream_rewrite(
            text, st, before.lang, prov, model_name, score_before=before.score, use_gate=gate
        ):
            if ev.kind == "delta":
                chunk = ev.data.get("text", "")
                parts.append(chunk)
                if not out:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
            elif ev.kind == "score":
                last_after = ev.data.get("after", before.score)
                last_delta = ev.data.get("delta", 0)
            elif ev.kind == "version":
                last_gate = ev.data.get("gate", "off")
        return "".join(parts), last_after, last_delta, last_gate

    results: list[tuple[str, int, int, str]] = []
    for i in range(max(1, versions)):
        if out is None and versions > 1:
            typer.echo(f"\n{C.BOLD}--- 版本 {i + 1} ---{C.RESET}")
        res = asyncio.run(_run_stream() if stream else _run_one())
        results.append(res)

    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        stem = path.stem
        for i, (rewritten, after, delta, gate) in enumerate(results, start=1):
            suffix = "" if versions == 1 else f".v{i}"
            target = out / f"{stem}.{st.id}{suffix}.txt"
            target.write_text(rewritten, encoding="utf-8")
            typer.echo(
                f"已写出 {target}  "
                f"{C.DIM}{before.score} → {after}（{delta:+d}）gate={gate}{C.RESET}"
            )
    elif not stream:
        # 非流式且未指定输出目录：把结果打到 stdout
        for i, (rewritten, after, delta, gate) in enumerate(results, start=1):
            if versions > 1:
                typer.echo(f"\n{C.BOLD}--- 版本 {i} ---{C.RESET}")
            typer.echo(rewritten)
            color = C.GREEN if delta < 0 else C.RED
            typer.echo(
                f"\n{C.DIM}AI 味 {before.score} → {color}{after}{C.RESET}{C.DIM}"
                f"（{delta:+d}）· gate={gate}{C.RESET}"
            )


# ============================================================
# batch
# ============================================================


@app.command()
def batch(
    directory: Annotated[Path, typer.Argument(help="输入目录（处理其中 *.txt / *.md）")],
    out: Annotated[Path, typer.Option("--out", "-o", help="输出目录")],
    style: Annotated[str, typer.Option("--style", "-s")] = "natural",
    concurrency: Annotated[int, typer.Option("--concurrency", "-c")] = 3,
    model: Annotated[str | None, typer.Option("--model")] = None,
    provider: Annotated[str | None, typer.Option("--provider")] = None,
) -> None:
    """批量改写目录下的文本文件；单文件失败不阻塞整批。"""
    from deaiify.providers.base import ProviderError
    from deaiify.providers.registry import get_provider
    from deaiify.services.rewrite import rewrite_one
    from deaiify.services.styles import get_style

    if not directory.is_dir():
        typer.secho(f"不是目录：{directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG)

    st = get_style(style)
    if st is None:
        typer.secho(f"未知风格 {style}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG)

    settings = get_settings()
    model_name = model or settings.default_model
    if not model_name:
        typer.secho(
            "未指定模型：用 --model 或设置 DEAIIFY_DEFAULT_MODEL", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(EXIT_CONFIG)

    try:
        prov = get_provider(provider)
    except ProviderError as exc:
        typer.secho(f"{exc.code}: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG) from None

    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in {".txt", ".md"})
    if not files:
        typer.secho(f"{directory} 下没有 .txt / .md 文件", fg=typer.colors.YELLOW)
        raise typer.Exit(EXIT_CONFIG)

    out.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(p: Path) -> tuple[str, str, str]:
        """返回 (文件名, 状态, 说明)。"""
        async with sem:
            try:
                text = p.read_text(encoding="utf-8")
                before = engine_analyze(text)
                oc = await rewrite_one(
                    text,
                    st,
                    before.lang,
                    prov,
                    model_name,
                    score_before=before.score,
                    use_gate=True,
                )
                (out / f"{p.stem}.{st.id}.txt").write_text(oc.text, encoding="utf-8")
                return (p.name, "ok", f"{oc.score_before} → {oc.score_after}（{oc.delta:+d}）")
            except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整批
                return (p.name, "fail", f"{type(exc).__name__}: {exc}")

    async def _all() -> list[tuple[str, str, str]]:
        return list(await asyncio.gather(*(_one(p) for p in files)))

    typer.echo(f"处理 {len(files)} 个文件（并发 {concurrency}，风格 {st.name}）…\n")
    results = asyncio.run(_all())

    rows = []
    for name, status, detail in results:
        mark = f"{C.GREEN}✓{C.RESET}" if status == "ok" else f"{C.RED}✗{C.RESET}"
        rows.append([mark, name, detail])
    typer.echo(table(["", "文件", "结果"], rows))

    ok = sum(1 for _, s, _ in results if s == "ok")
    fail = len(results) - ok
    typer.echo()
    if fail:
        typer.secho(f"完成：{ok} 成功，{fail} 失败", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    typer.secho(f"完成：{ok} 全部成功 → {out}", fg=typer.colors.GREEN)


# ============================================================
# lex
# ============================================================


@lex_app.command("list")
def lex_list() -> None:
    """列出内置词库统计与当前停用项。"""
    from deaiify.engine.lexicon import LAYERS, _read_entries, built_in_count

    typer.echo(f"内置词条总数：{built_in_count()}\n")
    rows = []
    for layer in LAYERS:
        zh = len(_read_entries(layer, "zh"))
        en = len(_read_entries(layer, "en"))
        rows.append([layer, str(zh), str(en), str(zh + en)])
    typer.echo(table(["层", "中文", "英文", "合计"], rows, ["left", "right", "right", "right"]))


@lex_app.command("export")
def lex_export(
    out: Annotated[Path, typer.Option("--out", "-o", help="导出文件路径")],
    layer: Annotated[str | None, typer.Option("--layer", help="只导出某一层")] = None,
    lang: Annotated[str, typer.Option("--lang", help="zh / en")] = "zh",
) -> None:
    """导出内置词库为 JSON。"""
    from deaiify.engine.lexicon import LAYERS, _read_entries

    layers = [layer] if layer else list(LAYERS)
    bad = [x for x in layers if x not in LAYERS]
    if bad:
        typer.secho(
            f"未知层：{', '.join(bad)}（可用：{', '.join(LAYERS)}）", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(EXIT_CONFIG)

    data: dict[str, list[str]] = {}
    for lay in layers:
        data[f"{lay}.{lang}"] = list(_read_entries(lay, lang))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v) for v in data.values())
    typer.secho(f"已导出 {total} 条 → {out}", fg=typer.colors.GREEN)


@lex_app.command("disable")
def lex_disable(
    terms: Annotated[list[str], typer.Argument(help="要停用的词条（可多个）")],
    restore: Annotated[bool, typer.Option("--restore", help="改为恢复停用")] = False,
) -> None:
    """停用/恢复内置词条（写入数据库，Web 与 API 共用）。"""
    from deaiify.db.session import get_session_factory
    from deaiify.services.lexicons import list_disabled, set_disabled

    async def _run() -> list[str]:
        async with get_session_factory()() as session:
            return await set_disabled(session, list(terms), not restore)

    try:
        remaining = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001 - 存储不可用时给配置错误码
        typer.secho(f"存储不可用：{type(exc).__name__}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(EXIT_CONFIG) from None

    action = "恢复" if restore else "停用"
    typer.secho(f"已{action}：{', '.join(terms)}", fg=typer.colors.GREEN)
    typer.echo(f"当前停用清单（{len(remaining)} 条）：{', '.join(remaining) or '（无）'}")

    _ = list_disabled  # 保持导入可见，便于扩展


# ============================================================
# models
# ============================================================


@app.command()
def models() -> None:
    """列出各 provider 的可达模型（不可达则显示原因）。"""
    from deaiify.providers.base import ProviderError
    from deaiify.providers.registry import get_provider, known_providers

    async def _probe(name: str) -> list[list[str]]:
        try:
            prov = get_provider(name)
            infos = await prov.list_models()
            return [["✓", name, m.id] for m in infos] or [
                ["✓", name, f"{C.DIM}（无模型）{C.RESET}"]
            ]
        except ProviderError as exc:
            return [["✗", name, f"{C.DIM}{exc.message}{C.RESET}"]]
        except Exception as exc:  # noqa: BLE001
            return [["✗", name, f"{C.DIM}{type(exc).__name__}{C.RESET}"]]

    async def _all() -> list[list[str]]:
        groups = await asyncio.gather(*(_probe(n) for n in known_providers()))
        return [row for g in groups for row in g]

    rows = asyncio.run(_all())
    typer.echo(table(["", "provider", "模型"], rows))


# ============================================================
# serve
# ============================================================


@app.command()
def serve(
    host: Annotated[str | None, typer.Option("--host", help="监听地址")] = None,
    port: Annotated[int | None, typer.Option("--port", help="端口")] = None,
    reload: Annotated[bool, typer.Option("--reload", help="热重载（开发用）")] = False,
) -> None:
    """启动 API 服务（等价于 uvicorn deaiify.main:app）。"""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "deaiify.main:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
