"""测试夹具：M4 词库/历史测试用的临时 SQLite 库。

- 会话级 `isolate_db`（autouse）：给**所有**测试默认套隔离 SQLite——
  rewrite 系测试不挂任何 DB 夹具，M4 历史落库后它们曾把测试数据写进
  真实开发库（data/deaiify.db）；CI api-int 已显式设 DEAIIFY_DATABASE_URL
  （PG），不受影响（setenv 只在变量缺失时生效）。
- `db_client` 夹具：需要干净空库逐例隔离的测试（词库/历史 CRUD）。

注意：不用 pytest 的 tmp_path——受限环境下 tempfile.mkdtemp 产出的目录
连创建者进程都无法访问（实测 PermissionError），故用普通 mkdir 目录。
"""

import asyncio
import os
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deaiify.config import get_settings
from deaiify.db.session import dispose_engine
from deaiify.main import create_app

_TMP_ROOT = Path(__file__).parent / "_tmpdata"


@pytest.fixture(scope="session", autouse=True)
def isolate_db() -> None:
    """会话级 DB 隔离：测试绝不触碰真实配置指向的库。"""
    _TMP_ROOT.mkdir(exist_ok=True)
    os.environ.setdefault("DEAIIFY_DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_ROOT / 'session.db'}")
    get_settings.cache_clear()
    yield
    # 会话结束不删 session.db？删：避免陈旧状态影响下轮
    try:
        (_TMP_ROOT / "session.db").unlink(missing_ok=True)
    except OSError:
        pass


def _fresh_db() -> Path:
    _TMP_ROOT.mkdir(exist_ok=True)
    path = _TMP_ROOT / f"{uuid.uuid4().hex}.db"
    return path


@pytest.fixture()
def db_client(monkeypatch: pytest.MonkeyPatch):
    """挂上临时 SQLite 的 TestClient（lifespan 自动建表）。"""
    db_file = _fresh_db()
    monkeypatch.setenv("DEAIIFY_DATABASE_URL", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.setenv("DEAIIFY_REDIS_URL", "")
    get_settings.cache_clear()
    asyncio.run(dispose_engine())  # 弃掉上一个测试可能缓存的引擎

    app = create_app()
    with TestClient(app) as client:
        yield client

    asyncio.run(dispose_engine())
    monkeypatch.delenv("DEAIIFY_DATABASE_URL", raising=False)
    monkeypatch.delenv("DEAIIFY_REDIS_URL", raising=False)
    get_settings.cache_clear()
    if db_file.exists():
        try:
            db_file.unlink()
        except OSError:
            pass  # 文件句柄未释放不致命


async def query_all(model):
    """直接查某模型全部行（须在 db_client 挂载的引擎上运行）。"""
    from sqlalchemy import select

    from deaiify.db.session import get_session_factory

    async with get_session_factory()() as session:
        result = await session.scalars(select(model))
        return list(result)


def run_async(coro):
    """测试内跑一次 async 断言（如直接查 ORM）。"""
    return asyncio.run(coro)


def test_tmp_root_writable() -> None:
    """自检：沙箱下普通 mkdir 目录可写可删（tempfile 路径不可用的替代方案）。"""
    d = _TMP_ROOT / f"selfcheck-{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "x.txt").write_text("ok", encoding="utf-8")
    assert (d / "x.txt").read_text(encoding="utf-8") == "ok"
    shutil.rmtree(d)
