"""
基于 OpenRouter API 的宝可梦队伍策略师 Agent
- 支持任意 LLM（Claude、GPT、Gemini 等）
- 完整的 Function Calling 循环
- 生产级：日志、重试、超时、错误处理
- 可视化工具调用链路
- 支持流式输出
"""

import json
import os
import re
import textwrap
import time
import requests
from typing import Any, Generator

from handlers.compact_context import compact_history
from handlers.error_recovery import auto_compact
from log import logging
from settings.constant import MAX_RECOVERY_ATTEMPTS, MODEL, CONTEXT_LIMIT, WORKDIR
from tools import NATIVE_HANDLERS, search_pokemon, NATIVE_TOOLS

# ── 上下文管理 ────────────────────────────────────────────────────

def estimate_context_size(messages: list[dict]) -> int:
    """粗略估算 message 列表的 token 数（字符数 ×0.4）。"""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        total += len(content)
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                total += len(tc["function"]["arguments"])
    return int(total * 0.4)


# ── 思考过程可视化 ────────────────────────────────────────────────


class Visualizer:
    """终端可视化 Agent 思考过程（Tool 调用链路）。"""

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    GRAY = "\033[90m"

    @classmethod
    def user_query(cls, query: str):
        """显示用户提问。"""
        cls._print_box("提问", query, cls.CYAN, "💬")

    @classmethod
    def thinking(cls, content: str | None):
        """显示模型的思考过程。"""
        if not content or not content.strip():
            return
        cls._print_box("思考", content.strip(), cls.YELLOW, "🧠")

    @classmethod
    def tool_call(cls, tool_name: str, arguments: dict, round_num: int, idx: int = 0):
        """显示工具调用。"""
        args_str = json.dumps(arguments, ensure_ascii=False, indent=2)
        tag = f"#{round_num}-{idx}"
        header = f" 调用工具: {cls.BOLD}{tool_name}{cls.RESET} {cls.GRAY}({tag}){cls.RESET}"
        body = f"\n{cls.GRAY}参数:{cls.RESET}\n{args_str}"
        cls._print_raw(cls.GREEN, "🔧", header + body)
        print()

    @classmethod
    def tool_result(cls, tool_name: str, result: Any, duration: float):
        """显示工具结果摘要。"""
        summary = cls._summarize(result)
        cls._print_raw(
            cls.BLUE,
            "📦",
            f" {cls.DIM}{tool_name}{cls.RESET} → {summary} "
            f"{cls.GRAY}({duration:.2f}s){cls.RESET}",
        )
        print()

    @classmethod
    def tool_error(cls, tool_name: str, error: str):
        """显示工具调用错误。"""
        cls._print_raw(cls.RED, "❌", f" {tool_name} 执行失败: {error}")
        print()

    @classmethod
    def final_answer(cls, content: str):
        """显示最终回答。"""
        print()
        cls._print_box("最终回答", content, cls.MAGENTA, "🎯", prefix="")

    @classmethod
    def _print_box(cls, label: str, text: str, color: str, emoji: str, prefix: str = ""):
        """打印带边框的信息块。"""
        icon = emoji or "•"
        lines = text.split("\n")

        # 上边框
        print(f"{prefix}{color}┌─ {icon} {label} ", end="")
        print(f"{'─' * max(2, 56 - len(label) - 4)}┐{cls.RESET}")

        # 内容
        for line in lines:
            for wrapped in textwrap.wrap(line, width=60, drop_whitespace=False) or [""]:
                print(f"{prefix}{color}│ {cls.RESET}{wrapped}")

        # 下边框
        print(f"{prefix}{color}└{'─' * 58}┘{cls.RESET}")

    @classmethod
    def _print_raw(cls, color: str, emoji: str, text: str):
        """打印无边框行。"""
        print(f"{color}{emoji}{cls.RESET}{text}")

    @staticmethod
    def _summarize(result: Any) -> str:
        """对工具返回结果生成一行摘要。"""
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return f"string ({len(result)} chars)"

        if isinstance(result, dict):
            if "error" in result:
                return f"⚠️ {result['error']}"
            keys = list(result.keys())
            # Pokemon-specific summaries
            if "name" in result and "types" in result:
                return f"{result['name'].capitalize()} | 属性: {', '.join(result['types'])}"
            if "damage_relations" in result:
                dr = result["damage_relations"]
                return f"{result['name']}: 2倍克 {dr['double_damage_to']}, 怕 {dr['double_damage_from']}"
            if "chain" in result:
                return f"进化链 ID={result['id']}"
            return f"dict ({len(keys)} keys)"

        if isinstance(result, list):
            return f"list ({len(result)} items)"

        if result is None:
            return "None"

        return str(result)[:60]


# ── 异常定义 ──────────────────────────────────────────────────────


class ContextLengthExceededError(RuntimeError):
    """当 API 返回上下文长度超出限制时的自定义异常。"""

    def __init__(self, message: str, max_tokens_hint: int | None = None):
        super().__init__(message)
        self.max_tokens_hint = max_tokens_hint


# ── OpenRouter API 调用 ──────────────────────────────────────────


class OpenRouterClient:
    """OpenRouter API 的轻量封装，支持 tool calling。"""

    def __init__(
        self,
        api_key: str = "",
        model: str = MODEL,
        timeout: int = 60,
        max_retries: int = MAX_RECOVERY_ATTEMPTS,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "缺少 OpenRouter API Key，请设置环境变量 OPENROUTER_API_KEY "
                "或通过参数传入。"
            )
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })

    @staticmethod
    def _check_context_length_error(status: int, body: str) -> ContextLengthExceededError | None:
        """检查响应是否为上下文长度超限错误。"""
        if status not in (400, 413, 429):
            return None

        body_lower = body.lower()
        context_keywords = [
            "context_length_exceeded",
            "context length",
            "maximum context length",
            "max tokens",
            "max_tokens",
            "token limit",
            "too many tokens",
            "prompt too long",
            "request too large",
            "content_length_limit",
        ]
        if not any(kw in body_lower for kw in context_keywords):
            return None

        max_tokens_hint = None
        patterns = [
            r"maximum context length is (\d+)",
            r"max.*?tokens?.*?(\d+)",
            r"(\d+).*?tokens?.*?limit",
            r"limit.*?(\d+).*?tokens?",
        ]
        for pattern in patterns:
            m = re.search(pattern, body_lower)
            if m:
                max_tokens_hint = int(m.group(1))
                break

        return ContextLengthExceededError(
            f"上下文/Token 长度超限 (HTTP {status})", max_tokens_hint
        )

    def _call(self, payload: dict) -> dict:
        """带重试的 API 调用。"""
        url = "https://openrouter.ai/api/v1/chat/completions"
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.ConnectTimeout as e:
                last_error = e
                logging.warning("请求超时 (attempt %d/%d)", attempt, self.max_retries)
                if attempt < self.max_retries:
                    delay = min(1.5 ** attempt, 30)
                    logging.info(
                        "连接超时，%.1fs 后重试 (attempt %d/%d)",
                        delay, attempt + 1, self.max_retries,
                    )
                    time.sleep(delay)
                    continue
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code
                body = e.response.text[:500]

                ctx_err = self._check_context_length_error(status, body)
                if ctx_err:
                    raise ctx_err from e

                if 400 <= status < 500 and status != 429:
                    raise RuntimeError(f"API 返回 {status}: {body}") from e

                logging.warning("HTTP %d (attempt %d/%d)", status, attempt, self.max_retries)
                last_error = e
            except requests.exceptions.JSONDecodeError as e:
                last_error = e
                logging.warning("JSON 解析失败 (attempt %d/%d): %s", attempt, self.max_retries, e)
            except requests.exceptions.RequestException as e:
                last_error = e
                logging.error("请求异常 (attempt %d/%d): %s", attempt, self.max_retries, e)

            if attempt < self.max_retries:
                delay = min(1.5 ** attempt, 30)
                time.sleep(delay)

        raise RuntimeError(f"API 请求失败，已重试 {self.max_retries} 次") from last_error

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 8000,
    ) -> dict:
        """发送聊天请求。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            # NATIVE_TOOLS 已是 [{"type":"function","function":{...}}] 格式
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        return self._call(payload)


# ── Agent 核心 ────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是宝可梦队伍策略师，精通宝可梦对战、属性克制和队伍搭配。

## 核心能力
1. **队伍推荐** — 根据玩家需求（通关、对战、偏爱属性等）推荐最佳队伍
2. **属性分析** — 分析队伍的属性覆盖面和防守弱点，给出改进建议
3. **数据可视化** — 使用图表工具生成种族值雷达图和柱状图
4. **对战建议** — 根据对手宝可梦，推荐最佳上场选择和技能策略
5. **进化展示** — 查询并展示宝可梦的进化链

## 工作流程
- 始终使用工具获取真实数据，不要凭记忆编造
- 推荐队伍时要先搜索宝可梦数据，确认种族值和属性
- 分析属性克制时调用 get_type_matchups 获取准确的克制关系
- 展示进化链时先调用 get_pokemon_species 获取进化链ID，再调用 get_evolution_chain
- 在对话上下文中跟踪用户的队伍成员，方便后续分析和替换

## 输出规范
- 用中文回答
- 宝可梦名称保留英文原名（如 Pikachu）
- 给出建议时附带数据支撑（种族值、属性克制关系等）
- 需要可视化时自动调用图表工具"""


class PokemonStrategist:
    """宝可梦队伍策略师 Agent —— 通过 Function Calling 调用 PokeAPI 回答用户问题。"""

    def __init__(self, client: OpenRouterClient, tools: list[dict]):
        self.client = client
        self.tools = tools

    def run(self, user_message: str, max_rounds: int = 20) -> str:
        """运行 Agent：多轮 Function Calling，返回文本回答（终端用）。"""
        result = self._run_loop(user_message, max_rounds, visualize=True)
        return result["answer"]

    def run_stream(
        self, user_message: str, max_rounds: int = 50,
    ) -> Generator[dict, None, None]:
        """Generator：以事件流形式产出 Agent 思考过程与最终结果。

        每次 yield 的 dict:
          - type=thinking:   { "content": "模型推理文本" }
          - type=tool_call:  { "name": func, "arguments": {}, "round": N, "idx": N }
          - type=tool_result:{ "name": func, "duration": float, "summary": "str" }
          - type=pokemon:    { "data": {pokemon dict} }  — 搜索到的宝可梦数据
          - type=chart:      { "path": "charts/xxx.png" }  — 生成的图表路径
          - type=final:      { "answer": str, "data": {"pokemon":[], "charts":[]} }
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        # 收集的结构化数据
        collected: dict[str, list] = {"pokemon": [], "charts": []}
        context_truncated = False

        for _round in range(1, max_rounds + 1):
            if estimate_context_size(messages) > CONTEXT_LIMIT:
                logging.info("[auto compact]")
                messages[:] = compact_history(messages)

            try:
                response = self.client.chat(messages, tools=self.tools)
            except ContextLengthExceededError as e:
                if context_truncated:
                    yield {"type": "final", "answer": "对话历史过长，请重新开始一个新的查询。", "data": collected}
                    return
                yield {"type": "thinking", "content": f"⚠️ 上下文超限 ({e})，正在压缩历史消息…"}
                messages[:] = auto_compact(messages)
                context_truncated = True
                response = self.client.chat(messages, tools=self.tools)

            context_truncated = False
            choice = response["choices"][0]
            msg = choice["message"]

            # 1) 推理过程
            if msg.get("content"):
                yield {"type": "thinking", "content": msg["content"]}

            # 2) 无工具调用 → 最终回答
            if not msg.get("tool_calls"):
                yield {"type": "final", "answer": msg["content"], "data": collected}
                return

            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": msg["tool_calls"],
            })

            # 3) 依次执行每个工具并 yield 事件
            for idx, tc in enumerate(msg["tool_calls"]):
                func_name = tc["function"]["name"]
                arguments = json.loads(tc["function"]["arguments"])

                yield {
                    "type": "tool_call",
                    "name": func_name,
                    "arguments": arguments,
                    "round": _round,
                    "idx": idx,
                }

                t0 = time.time()
                try:
                    tool_result = self._execute_tool(tc)
                    duration = time.time() - t0
                    result_data = json.loads(tool_result)

                    # 数据收集
                    self._collect_data(collected, func_name, arguments, result_data)

                    yield {
                        "type": "tool_result",
                        "name": func_name,
                        "duration": round(duration, 2),
                        "summary": self._summarize_for_event(result_data),
                    }

                    # 额外 yield 结构化数据事件
                    if func_name == "search_pokemon" and isinstance(result_data, dict) and "id" in result_data:
                        yield {"type": "pokemon", "data": result_data}
                    elif func_name in ("generate_stats_radar", "generate_stats_bar"):
                        chart_path = result_data.get("message", "")
                        if chart_path:
                            yield {"type": "chart", "path": chart_path}

                except Exception as e:
                    duration = time.time() - t0
                    logging.info("执行工具失败: %s, 参数: %s; error: %s", func_name, arguments, e)
                    yield {
                        "type": "tool_result",
                        "name": func_name,
                        "duration": round(duration, 2),
                        "summary": f"❌ {str(e)[:60]}",
                    }
                    tool_result = json.dumps({"error": str(e)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        # 达到最大轮数
        try:
            response = self.client.chat(messages)
        except ContextLengthExceededError:
            messages[:] = auto_compact(messages)
            response = self.client.chat(messages)
        final = response["choices"][0]["message"]["content"]
        yield {"type": "final", "answer": final, "data": collected}

    @staticmethod
    def _collect_data(collected: dict, func_name: str, arguments: dict, data: Any):
        """从工具返回结果中提取结构化宝可梦数据。"""
        if func_name == "search_pokemon" and isinstance(data, dict) and "id" in data:
            # 去重（按 id）
            existing_ids = {p["id"] for p in collected["pokemon"]}
            if data["id"] not in existing_ids:
                collected["pokemon"].append(data)
        elif func_name in ("generate_stats_radar", "generate_stats_bar"):
            chart_path = data.get("message", "") if isinstance(data, dict) else ""
            if chart_path and chart_path not in collected["charts"]:
                collected["charts"].append(chart_path)

    def _run_loop(
        self, user_message: str, max_rounds: int, visualize: bool,
    ) -> dict:
        """Agent 核心循环。"""
        if visualize:
            Visualizer.user_query(user_message)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        context_truncated = False

        for _round in range(1, max_rounds + 1):
            if estimate_context_size(messages) > CONTEXT_LIMIT:
                logging.info("[auto compact]")
                messages[:] = compact_history(messages)

            try:
                response = self.client.chat(messages, tools=self.tools)
            except ContextLengthExceededError as e:
                if context_truncated:
                    logging.error("截断后仍然上下文超限，放弃当前轮次")
                    return {
                        "answer": "对话历史过长，请重新开始一个新的查询。",
                        "error": "context_length_exceeded",
                    }
                logging.warning("上下文超限，即将截断消息: %s", e)
                if visualize:
                    Visualizer.tool_error("系统", f"上下文超限 ({e})，正在压缩历史消息…")
                messages[:] = auto_compact(messages)
                context_truncated = True
                response = self.client.chat(messages, tools=self.tools)

            context_truncated = False
            choice = response["choices"][0]
            msg = choice["message"]

            if visualize:
                Visualizer.thinking(msg.get("content"))

            if not msg.get("tool_calls"):
                if visualize:
                    Visualizer.final_answer(msg["content"])
                return {"answer": msg["content"]}

            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": msg["tool_calls"],
            })

            for idx, tc in enumerate(msg["tool_calls"]):
                func_name = tc["function"]["name"]
                arguments = json.loads(tc["function"]["arguments"])

                if visualize:
                    Visualizer.tool_call(func_name, arguments, _round, idx)

                t0 = time.time()
                try:
                    tool_result = self._execute_tool(tc)
                    duration = time.time() - t0
                    result_data = json.loads(tool_result)

                    if visualize:
                        Visualizer.tool_result(func_name, result_data, duration)

                except Exception as e:
                    duration = time.time() - t0
                    if visualize:
                        Visualizer.tool_error(func_name, str(e))
                    tool_result = json.dumps({"error": str(e)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        logging.warning("达到最大调用轮数 (%d)，请求模型总结", max_rounds)
        try:
            response = self.client.chat(messages)
        except ContextLengthExceededError:
            messages[:] = auto_compact(messages)
            response = self.client.chat(messages)
        final = response["choices"][0]["message"]["content"]
        if visualize:
            Visualizer.final_answer(final)
        return {"answer": final}

    def _execute_tool(self, tool_call: dict) -> str:
        """执行一个工具调用，返回 JSON 字符串。"""
        func_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])

        # 先查数据工具
        handler = NATIVE_HANDLERS.get(func_name)
        if handler:
            logging.info("执行工具: %s, 参数: %s", func_name, arguments)
            result = handler(**arguments)
            return json.dumps(result, ensure_ascii=False, default=str)

        # 再查图表工具
        chart_handler = CHART_FUNC_MAP.get(func_name)
        if chart_handler:
            logging.info("执行图表工具: %s, 参数: %s", func_name, arguments)
            result = chart_handler(**arguments)
            return json.dumps({"message": result}, ensure_ascii=False)

        raise ValueError(f"未知工具: {func_name}")

    @staticmethod
    def _summarize_for_event(data: Any) -> str:
        """为流式事件生成一行摘要。"""
        if isinstance(data, list):
            return f"找到 {len(data)} 个结果" if data else "无结果"
        if isinstance(data, dict):
            name = data.get("name", "")
            if name:
                return f"获取到: {name.capitalize()}"
            if data.get("message"):
                return str(data["message"])[:60]
            return f"返回 {len(data)} 个字段"
        return str(data)[:40] if data else "空"


# ── 图表工具（独立于 PokeAPI 数据工具） ──────────────────────────

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

STAT_LABELS = ["HP", "Attack", "Defense", "Sp. Atk", "Sp. Def", "Speed"]
STAT_KEYS = ["hp", "attack", "defense", "special-attack", "special-defense", "speed"]
COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
]


def _fetch_stats(pokemon_names: list[str]) -> list[tuple[str, dict]]:
    """批量获取宝可梦种族值。"""
    results = []
    for name in pokemon_names:
        try:
            data = search_pokemon(name)
            results.append((data["name"].capitalize(), data["stats"]))
        except Exception as e:
            logging.warning("无法获取 %s 的数据: %s", name, e)
    return results


def _safe_filename(names: list[str]) -> str:
    return "_".join(n.lower().replace("/", "-") for n in names)


def generate_stats_radar(pokemon_names: list[str], title: str = "") -> str:
    """生成种族值雷达图，返回图片保存路径。"""
    pokemon_data = _fetch_stats(pokemon_names)
    if not pokemon_data:
        return "错误：无法获取任何宝可梦数据"

    angles = np.linspace(0, 2 * np.pi, len(STAT_LABELS), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(STAT_LABELS, fontsize=12)
    ax.set_ylim(0, 255)
    ax.set_title(title or "宝可梦种族值雷达图", pad=20, fontsize=14, fontweight="bold")

    for i, (name, stats) in enumerate(pokemon_data):
        values = [stats.get(k, 0) for k in STAT_KEYS]
        values += values[:1]
        color = COLORS[i % len(COLORS)]
        ax.plot(angles, values, "o-", linewidth=2, label=name, color=color)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.legend(loc="upper right", bbox_to_anchor=(1.2, 1.1), fontsize=11)
    ax.grid(True)

    os.makedirs(os.path.join(WORKDIR, "charts"), exist_ok=True)
    filename = f"charts/radar_{_safe_filename(pokemon_names)}.png"
    filepath = os.path.join(WORKDIR, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return filepath


def generate_stats_bar(pokemon_names: list[str], title: str = "") -> str:
    """生成种族值柱状对比图，返回图片保存路径。"""
    pokemon_data = _fetch_stats(pokemon_names)
    if not pokemon_data:
        return "错误：无法获取任何宝可梦数据"

    x = np.arange(len(STAT_LABELS))
    n = len(pokemon_data)
    width = 0.8 / n if n > 0 else 0.5

    fig, ax = plt.subplots(figsize=(max(10, n * 2), 6))

    for i, (name, stats) in enumerate(pokemon_data):
        values = [stats.get(k, 0) for k in STAT_KEYS]
        offset = (i - n / 2 + 0.5) * width
        bars = ax.bar(
            x + offset, values, width,
            label=name, color=COLORS[i % len(COLORS)],
            edgecolor="white", linewidth=1,
        )
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 3,
                str(val), ha="center", va="bottom",
                fontsize=8, fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(STAT_LABELS, fontsize=11)
    ax.set_ylabel("种族值", fontsize=12)
    ax.set_title(title or "宝可梦种族值对比", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.set_ylim(0, 280)
    ax.grid(axis="y", alpha=0.3)

    os.makedirs(os.path.join(WORKDIR, "charts"), exist_ok=True)
    filename = f"charts/bar_{_safe_filename(pokemon_names)}.png"
    filepath = os.path.join(WORKDIR, filename)
    plt.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return filepath


CHART_FUNC_MAP: dict[str, Any] = {
    "generate_stats_radar": generate_stats_radar,
    "generate_stats_bar": generate_stats_bar,
}


# ── 入口 ──────────────────────────────────────────────────────────


def main():
    # 初始化 OpenRouter 客户端
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("请设置环境变量 OPENROUTER_API_KEY")
        return

    model = os.environ["MODEL_ID"]
    logging.info("已加载 %d 个工具", len(NATIVE_TOOLS))

    client = OpenRouterClient(api_key=api_key, model=model)
    agent = PokemonStrategist(client, NATIVE_TOOLS)

    # 交互式模式
    print(f"{Visualizer.BOLD}{Visualizer.GREEN}"
          f"╔══════════════════════════════════════════════════════╗\n"
          f"║      🎮  宝可梦队伍策略师 - Pokemon Strategist       ║\n"
          f"╚══════════════════════════════════════════════════════╝"
          f"{Visualizer.RESET}\n")
    print(f"  模型: {model}  |  工具: {len(NATIVE_TOOLS)} 个\n")

    while True:
        try:
            query = input(f"{Visualizer.CYAN}🎮 you >>{Visualizer.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in ("/exit", "/quit", "exit", "quit"):
            break
        agent.run(query)
        print()


if __name__ == "__main__":
    main()
