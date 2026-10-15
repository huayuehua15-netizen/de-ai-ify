"""de-ai-ify CLI 入口（命令规划见 docs/DEVELOPMENT.md §11）。"""

import asyncio

import typer

from deaiify import __version__
from deaiify.api.routers.health import check_db, check_redis
from deaiify.config import get_settings
from deaiify.engine.version import ENGINE_VERSION

app = typer.Typer(
    help="de-ai-ify CLI：评分 / 改写 / 词库 / 批量 / 服务（docs/DEVELOPMENT.md §11）",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """显示应用与评分引擎版本。"""
    typer.echo(f"deaiify {__version__} (engine {ENGINE_VERSION})")


@app.command()
def doctor() -> None:
    """环境自检：配置摘要与存储连通性（终端侧见 pnpm check:env）。"""
    settings = get_settings()
    typer.echo(f"deaiify {__version__} (engine {ENGINE_VERSION})")
    typer.echo(f"env={settings.env} store={settings.store}")

    db = asyncio.run(check_db())
    redis = asyncio.run(check_redis())
    typer.echo(f"db={db['status']} ({db.get('dialect') or db.get('detail', '-')})")
    typer.echo(f"redis={redis['status']} ({redis.get('detail', '-')})")

    if db["status"] != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
