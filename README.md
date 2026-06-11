# Pokemon Team Strategist · 宝可梦队伍策略师

> 基于 AI Agent 的宝可梦对战队伍推荐系统。用户用自然语言描述对战需求，Agent 自动查询宝可梦数据、分析属性克制、生成可视化图表，推荐最优队伍组合。

---

## 项目简介

本项目通过 **OpenRouter API** 接入大语言模型（Claude / GPT / Gemini 等），构建了一个具备 **Function Calling** 能力的 AI Agent，专精于宝可梦对战策略。核心能力：

- 自然语言理解对战需求（如"帮我组一支雨天队"）
- 调用 [PokeAPI](https://pokeapi.co/) 查询宝可梦数据（种族值、属性、特性、技能等）
- 自动生成多维度可视化图表（雷达图、柱状图、属性克制热力图等）
- SSE 流式实时输出思考过程与结果

## 快速启动

### 环境要求

- Python 3.12+
- 虚拟环境（推荐 venv / conda）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

```bash
# 必填：OpenRouter API Key（https://openrouter.ai/keys）
export OPENROUTER_API_KEY="sk-or-v1-xxxxxxxx"

# 可选：指定模型（默认由 OpenRouter 决定）
export MODEL_ID="anthropic/claude-sonnet-4-6"

# 可选：服务端口（默认 5001）
export PORT=5001
```

### 启动服务

```bash
python app.py
```

启动日志示例：

```
INFO  Agent 初始化完成, 模型=anthropic/claude-sonnet-4-6, 工具=12 个
INFO  启动 Flask 服务, port=5001
```

### 访问方式

打开浏览器访问 **http://localhost:5001**

Web 界面支持：
- 输入自然语言描述对战需求
- 实时流式查看 Agent 思考过程
- 查看推荐队伍与可视化图表

---

## 目录结构

```
pokemon-team-strategist/
├── app.py                  # Flask Web 入口 + SSE 流式接口
├── agent.py                # 核心 Agent：LLM 对话循环 + Function Calling
├── tools.py                # 工具函数集（PokeAPI 查询、文件读写等）
├── log.py                  # 日志配置
├── requirements.txt        # Python 依赖

├── handlers/
│   ├── system_prompt.py    # 系统提示词构造
│   ├── compact_context.py  # 上下文压缩（控制 Token 用量）
│   ├── error_recovery.py   # 错误恢复 & 自动重试
│   ├── memory_system.py    # 记忆系统（持久化存储）
│   ├── tasks_system.py     # 任务管理
│   ├── todomanager.py      # Todo 管理器
│   └── hook_system.py      # Hook 事件系统

├── services/
│   └── agent_service.py    # Agent 服务层（与 Claude Code 集成）

├── settings/
│   ├── __init__.py
│   └── constant.py         # 全局常量与配置

├── templates/
│   └── index.html          # 前端页面（SSE 实时交互）

├── charts/                 # 生成的图表输出目录
├── static/                 # 静态资源目录
└── logs/                   # 运行日志
```

## 技术架构

```
┌─────────────┐     HTTP/SSE      ┌──────────────────────┐
│   Browser   │ ◄──────────────►  │   Flask Web Server   │
│  (index.html)│  流式事件推送      │   (app.py)           │
└─────────────┘                   └────────┬─────────────┘
                                           │
                                    ┌──────▼──────────────┐
                                    │   PokemonStrategist │
                                    │   Agent 核心         │
                                    │   (agent.py)         │
                                    └──────┬──────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
           ┌────────────────┐    ┌────────────────┐    ┌────────────────┐
           │  Function      │    │  PokeAPI       │    │  Matplotlib    │
           │  Calling 工具   │    │  外部数据接口   │    │  图表生成      │
           │  (tools.py)    │    │  REST API      │    │  (*_chart.py)  │
           └────────────────┘    └────────────────┘    └────────────────┘

                    ┌──────────────────────────────────────┐
                    │  Infrastructure Layer                │
                    │  handlers/ · services/ · settings/   │
                    │  日志 · 记忆 · 任务 · 错误恢复       │
                    └──────────────────────────────────────┘
```

### 核心流程

1. **用户输入** → 浏览器发送消息到 `/api/chat`（POST）
2. **SSE 流式响应** → Flask 返回 `text/event-stream`，实时推送 thinking / tool_call / tool_result / chart / final 事件
3. **Agent 循环** → `PokemonStrategist.run_stream()` 执行 LLM 对话循环，触发 Function Calling
4. **工具执行** → `tools.py` 中的函数查询 PokeAPI、读写文件、执行命令等
5. **图表生成** → Matplotlib 生成雷达图、柱状图、热力图等
6. **结果返回** → Agent 生成最终推荐，连同图表路径推送给前端

### 关键特性

| 特性 | 说明 |
|------|------|
| **多模型支持** | 通过 OpenRouter 接入任意 LLM（Claude、GPT、Gemini 等） |
| **流式输出** | SSE 协议实时推送 Agent 思考过程，前端逐行展示 |
| **Function Calling** | Agent 自主决策调用外部工具（查询、计算、绘图） |
| **上下文管理** | 自动压缩历史对话，防止 Token 溢出 |
| **错误恢复** | 自动重试、指数退避、上下文回滚 |
| **可视化** | 种族值雷达图、属性克制热力图、速度对比、攻防分析等 |
| **记忆系统** | 持久化存储用户偏好和会话信息 |
