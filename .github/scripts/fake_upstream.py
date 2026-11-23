#!/usr/bin/env python3
"""e2e 用的假上游：一个最小 OpenAI 兼容服务。

**为什么需要它**：改写链路（`/rewrite`、`/rewrite/stream`）必须真的打一次
HTTP 才能验证——prompt 拼装、SSE 帧序、闸门重算、前端打字机。但 CI 里没有
任何模型凭据，也不该有（跑一次要花钱、且结果不稳定）。

所以这里起一个只实现两个端点的假服务：

  GET  /v1/models              → 给 /providers/{id}/test 用
  POST /v1/chat/completions    → 按 stream 字段决定回 JSON 还是 SSE

它**故意返回一段人写风格的中文**（短句、口语连接词、无套话），这样：
  - 闸门算出的 Δscore 会是负的（pass），能验证「闸门放行好改写」；
  - 前端能拿到真实文本，打字机、版本 Tab、采纳按钮都走了真实代码路径。

另外留了两个开关，用来测加载态与错误态（都是测试夹具，不是产品代码）：
请求体里出现 `[[SLOW]]` 时故意拖 2 秒；出现 `[[FAIL]]` 时返回 500。

用法（CI 与本地一致）：
    python .github/scripts/fake_upstream.py --port 9100
    # 然后建供应商指向 http://127.0.0.1:9100/v1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODEL_ID = "fake-deaiify-1"

# 一段人写风格的中文：短句、口语、无「综上所述/首先其次最后」。
REWRITTEN = (
    "人工智能这东西现在确实挺能打。"
    "写稿、算账、跑客服，都能替人省下不少力气。"
    "但它也不是万灵药——说清楚要什么，它才给得出像样的东西。"
)

_FALLBACK_CHARS = "在当社会，人工智能技术正在快速发展，首先提升了效率，其次降低了成本。"


def _completion(content: str) -> dict[str, Any]:
    """OpenAI chat.completion 的最小合法形状（含 usage，闸门要算 token 不关心，但 SDK 会读）。"""
    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 60, "total_tokens": 160},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[fake-upstream] " + (fmt % args) + "\n")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, content: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def chunk(delta: dict[str, Any], finish: str | None = None) -> None:
            payload = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": MODEL_ID,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            line = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

        # 按字符切，模拟真实上游的逐字流
        for ch in content:
            chunk({"content": ch})
        chunk({}, "stop")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._send_json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": MODEL_ID,
                            "object": "model",
                            "created": 0,
                            "owned_by": "fake",
                        }
                    ],
                },
            )
            return
        self._send_json(404, {"error": {"message": "not found", "type": "fake"}})

    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._send_json(404, {"error": {"message": "not found", "type": "fake"}})
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {"error": {"message": "bad json", "type": "fake"}})
            return

        # 把 messages 拼成一个大字符串，用来找开关标记（不关心结构）
        blob = json.dumps(body.get("messages", []), ensure_ascii=False)

        if "[[FAIL]]" in blob:
            self._send_json(
                500,
                {"error": {"message": "fake upstream failure", "type": "server_error"}},
            )
            return
        if "[[SLOW]]" in blob:
            time.sleep(2.0)

        content = REWRITTEN

        if body.get("stream"):
            self._send_sse(content)
        else:
            self._send_json(200, _completion(content))


def main() -> int:
    ap = argparse.ArgumentParser(description="de-ai-ify e2e 假上游")
    ap.add_argument("--port", type=int, default=9100)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"fake upstream on http://{args.host}:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
