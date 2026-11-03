"""词库 CRUD / 导入导出 / 内置停用 端点测试（M4，临时 SQLite）。"""

from fastapi.testclient import TestClient

from conftest import query_all, run_async
from deaiify.db.models import DisabledTerm, Lexicon


def _create(client: TestClient, **overrides) -> dict:
    body = {
        "name": "公司黑话",
        "description": "内部套话",
        "lang": "zh",
        "terms": [
            {"term": "抓手", "layer": "cliches", "match_mode": "exact"},
            {"term": "赋能.{0,6}生态", "layer": "cliches", "match_mode": "regex"},
        ],
    }
    body.update(overrides)
    resp = client.post("/api/v1/lexicons", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_list(db_client: TestClient) -> None:
    created = _create(db_client)
    assert created["id"]
    assert len(created["terms"]) == 2
    assert created["terms"][0]["match_mode"] == "exact"
    # 正则词条入库时已校验
    assert created["terms"][1]["match_mode"] == "regex"

    resp = db_client.get("/api/v1/lexicons")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_patch_delete(db_client: TestClient) -> None:
    created = _create(db_client)
    lid = created["id"]

    resp = db_client.get(f"/api/v1/lexicons/{lid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "公司黑话"

    resp = db_client.patch(f"/api/v1/lexicons/{lid}", json={"name": "新名字"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名字"

    resp = db_client.delete(f"/api/v1/lexicons/{lid}")
    assert resp.status_code == 204
    assert db_client.get(f"/api/v1/lexicons/{lid}").status_code == 404
    # 级联删词条
    assert run_async(query_all(Lexicon)) == []


def test_not_found_error_shape(db_client: TestClient) -> None:
    resp = db_client.get("/api/v1/lexicons/nope")
    assert resp.status_code == 404
    body = resp.json()["error"]
    assert body["code"] == "not_found"
    assert "request_id" in body


def test_invalid_term_rejected(db_client: TestClient) -> None:
    # 非法正则
    resp = db_client.post(
        "/api/v1/lexicons",
        json={"name": "x", "terms": [{"term": "[unclosed", "match_mode": "regex"}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_term"

    # 未知层
    resp = db_client.post(
        "/api/v1/lexicons",
        json={"name": "x", "terms": [{"term": "词", "layer": "nope"}]},
    )
    assert resp.status_code == 400


def test_add_and_delete_terms(db_client: TestClient) -> None:
    created = _create(db_client)
    lid = created["id"]
    tid = created["terms"][0]["id"]

    resp = db_client.post(f"/api/v1/lexicons/{lid}/terms", json={"terms": [{"term": "对齐"}]})
    assert resp.status_code == 200
    assert len(resp.json()["terms"]) == 3

    resp = db_client.delete(f"/api/v1/lexicons/{lid}/terms/{tid}")
    assert resp.status_code == 204
    assert len(db_client.get(f"/api/v1/lexicons/{lid}").json()["terms"]) == 2


def test_import_csv_and_json(db_client: TestClient) -> None:
    lid = _create(db_client)["id"]

    csv_payload = (
        "term,layer,match_mode,weight,replacement\n"
        "闭环,cliches,exact,1.5,说清楚结果\n"
        "颗粒度,cliches,exact,,\n"
    )
    resp = db_client.post(
        f"/api/v1/lexicons/{lid}/import",
        json={"format": "csv", "content": csv_payload},
    )
    assert resp.status_code == 200, resp.text
    terms = resp.json()["terms"]
    assert len(terms) == 4
    added = {t["term"]: t for t in terms}
    assert added["闭环"]["weight"] == 1.5
    assert added["闭环"]["replacement"] == "说清楚结果"

    # JSON 导入（{terms:[...]} 形状）
    resp = db_client.post(
        f"/api/v1/lexicons/{lid}/import",
        json={
            "format": "json",
            "content": '{"terms": [{"term": "抓本质", "match_mode": "exact"}]}',
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["terms"]) == 5

    # 坏 JSON → 400
    resp = db_client.post(f"/api/v1/lexicons/{lid}/import", json={"format": "json", "content": "{"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_import"


def test_export_csv_and_json(db_client: TestClient) -> None:
    lid = _create(db_client)["id"]

    resp = db_client.get(f"/api/v1/lexicons/{lid}/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment" in resp.headers["content-disposition"]
    data = resp.json()
    assert data["name"] == "公司黑话"
    assert len(data["terms"]) == 2

    resp = db_client.get(f"/api/v1/lexicons/{lid}/export?format=csv")
    assert resp.status_code == 200
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("term,layer,match_mode")
    assert len(lines) == 3  # 表头 + 2 词条


def test_builtin_info_and_disable(db_client: TestClient) -> None:
    resp = db_client.get("/api/v1/lexicons/builtin")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 800
    assert resp.json()["disabled"] == []

    resp = db_client.put(
        "/api/v1/lexicons/builtin/disabled",
        json={"terms": ["综上所述", "综上所述"], "disabled": True},
    )
    assert resp.status_code == 200
    # 幂等：重复停用不产生重复行
    assert resp.json()["disabled"] == ["综上所述"]
    assert len(run_async(query_all(DisabledTerm))) == 1

    # 恢复
    resp = db_client.put(
        "/api/v1/lexicons/builtin/disabled",
        json={"terms": ["综上所述"], "disabled": False},
    )
    assert resp.json()["disabled"] == []


def test_analyze_with_custom_lexicon(db_client: TestClient) -> None:
    """自定义词条参与评分：加词条后分数升高、findings 命中自定义词。"""
    text = "我们要抓住这个机会，抓好落实工作。"
    base = db_client.post("/api/v1/analyze", json={"text": text}).json()

    lid = _create(db_client, terms=[{"term": "抓住", "layer": "cliches"}])["id"]
    custom = db_client.post("/api/v1/analyze", json={"text": text, "lexicon_ids": [lid]}).json()

    assert custom["score"] > base["score"]
    assert any(f["matched"] == "抓住" for f in custom["findings"])


def test_analyze_respects_disabled_builtin(db_client: TestClient) -> None:
    text = "综上所述，这个方案是可行的。总之，我们应当尽快推进。"
    base = db_client.post("/api/v1/analyze", json={"text": text}).json()
    assert any(f["matched"] == "综上所述" for f in base["findings"])

    db_client.put(
        "/api/v1/lexicons/builtin/disabled", json={"terms": ["综上所述"], "disabled": True}
    )
    after = db_client.post("/api/v1/analyze", json={"text": text}).json()
    assert not any(f["matched"] == "综上所述" for f in after["findings"])
    assert after["score"] < base["score"]
