"""
Flask Web 后端 — 宝可梦队伍策略师 SSE 接口
===========================================
- POST /api/chat  SSE 流式对话
- GET  /         前端页面
- GET  /charts/<path>  图表静态文件
"""

import json
import os

from flask import Flask, Response, render_template, request, stream_with_context
from log import logging
from agent import (
    PokemonStrategist,
    OpenRouterClient,
    WORKDIR,
)
from tools import NATIVE_TOOLS


app = Flask(
    __name__,
    template_folder=os.path.join(WORKDIR, "templates"),
    static_folder=os.path.join(WORKDIR, "static"),
)

# ── Agent 全局初始化 ─────────────────────────────────────────────

_api_key = os.environ.get("OPENROUTER_API_KEY", "")
_model = os.environ.get("MODEL_ID")

if _api_key:
    _client = OpenRouterClient(api_key=_api_key, model=_model)
    _agent = PokemonStrategist(_client, NATIVE_TOOLS)
    logging.info("Agent 初始化完成, 模型=%s, 工具=%d 个", _model, len(NATIVE_TOOLS))
else:
    _client = None
    _agent = None
    logging.warning("OPENROUTER_API_KEY 未设置，Agent 不可用")


# ── SSE 工具函数 ─────────────────────────────────────────────────


def sse_event(event_type: str, data: dict) -> str:
    """格式化 SSE 事件。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_comment(msg: str) -> str:
    return f": {msg}\n"


# ── 路由 ─────────────────────────────────────────────────────────


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/charts/<path:filename>")
def serve_chart(filename: str):
    from flask import send_from_directory
    charts_dir = os.path.join(WORKDIR, "charts")
    return send_from_directory(charts_dir, filename)


@app.route("/api/config", methods=["GET"])
def get_config():
    """前端获取配置（模型名等）。"""
    return {"model": _model if _client else "N/A", "ready": _agent is not None}


@app.route("/api/chat", methods=["POST"])
def chat():
    """SSE 流式对话接口。"""
    if not _agent or not _client:
        return {"error": "Agent 未初始化，请设置 OPENROUTER_API_KEY"}, 503

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return {"error": "消息不能为空"}, 400

    def generate():
        yield sse_comment("connection established")
        try:
            for event in _agent.run_stream(message):
                etype = event["type"]
                if etype == "thinking":
                    yield sse_event("thinking", {"content": event["content"]})
                elif etype == "tool_call":
                    yield sse_event("tool_call", {
                        "name": event["name"],
                        "arguments": event["arguments"],
                        "round": event.get("round", 1),
                        "idx": event.get("idx", 0),
                    })
                elif etype == "tool_result":
                    yield sse_event("tool_result", {
                        "name": event["name"],
                        "duration": event.get("duration", 0),
                        "summary": event.get("summary", ""),
                    })
                elif etype == "pokemon":
                    yield sse_event("pokemon", {"data": event["data"]})
                elif etype == "chart":
                    # 将绝对路径转为相对URL
                    chart_abs = event["path"]
                    try:
                        rel = os.path.relpath(chart_abs, WORKDIR)
                    except ValueError:
                        rel = chart_abs
                    yield sse_event("chart", {"path": rel.replace(os.sep, "/")})
                elif etype == "final":
                    # final 事件中的 chart 路径也需转为相对 URL
                    final_data = event.get("data", {"pokemon": [], "charts": []})
                    rel_charts = []
                    for cp in final_data.get("charts", []):
                        try:
                            rel_charts.append(os.path.relpath(cp, WORKDIR).replace(os.sep, "/"))
                        except ValueError:
                            rel_charts.append(cp)
                    final_data["charts"] = rel_charts
                    yield sse_event("final", {
                        "answer": event["answer"],
                        "data": final_data,
                    })
                    break
        except Exception as e:
            logging.exception("Agent 运行出错")
            yield sse_event("error", {"message": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 入口 ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    logging.info("启动 Flask 服务, port=%d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
