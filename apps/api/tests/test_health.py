"""健康端点测试：标准栈不可用时降级为 unavailable，可用时必须为 ok。"""

import os

import pytest
from fastapi.testclient import TestClient

from deaiify.main import app


def test_health_shape() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "deaiify"
    assert data["version"]
    assert data["engine_version"]
    assert data["db"]["status"] in {"ok", "unavailable"}
    assert data["redis"]["status"] in {"ok", "unavailable", "skipped"}


@pytest.mark.skipif(
    os.getenv("DEAIIFY_EXPECT_SERVICES") != "1",
    reason="需要标准栈 PG + Redis（docs/DEVELOPMENT.md §3.3；CI api-int 或本机 compose）",
)
def test_health_standard_stack() -> None:
    with TestClient(app) as client:
        data = client.get("/api/v1/health").json()
    assert data["db"]["status"] == "ok"
    assert data["redis"]["status"] == "ok"
