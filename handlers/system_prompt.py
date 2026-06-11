import platform
import re
from datetime import datetime
from pathlib import Path

from settings.constant import MODEL, WORKDIR, DYNAMIC_BOUNDARY

MEMORY_GUIDANCE = """
应该保存的记忆save memories：

  1. 用户偏好（user 类型）
  - 偏好的属性类型（如"喜欢火系、龙系"）
  - 偏好的宝可梦（如"最爱喷火龙"）
  - 游戏模式倾向（通关/对战/收藏）
  - 对战风格（进攻型/受队/平衡）
  - 世代偏好（Gen1 情怀/只玩最新世代）
  - 规则偏好（单打/双打/神战/普双）

  2. 用户知识水平（user 类型）
  - 新手 vs 老手（影响后续解释详细程度）
  - 已掌握的概念（如"他知道什么是属性一致性"→ 下次不用再解释）

  3. 队伍构建模式（project 类型）
  - 用户常用的组队套路（如"总是带一只地面系联防"）
  - 高频使用的宝可梦列表
  - 之前推荐过且被用户认可的队伍结构

  4. 持续对战环境（project 类型）
  - 用户经常对战的对手/队伍类型
  - 当前关注的 meta 环境（如"最近被受队打得很惨"）
  -> type: reference

不应该保存的记忆 NOT to save memories:：
- PokeAPI 原始返回数据
- 单次对战的完整模拟过程
- 工具调用的中间日志
- 宝可梦种族值/属性克制表
- 完整对话全文
- 图表文件路径
"""


class SystemPromptBuilder:
    def __init__(self, workdir: Path = None, tools: list = None):
        self.workdir = workdir or WORKDIR
        self.tools = tools or []
        self.skills_dir = self.workdir / "skills"
        self.memory_dir = self.workdir / ".memory"

    def _build_core(self) -> str:
        return (
            """你是宝可梦队伍策略师，精通宝可梦对战、属性克制和队伍搭配。
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
            - 需要可视化时自动调用图表工具
            - 生成的图片全部保存在当前目录下./charts文件夹"""

        )

    def _build_tool_listing(self) -> str:
        if not self.tools:
            return ""

        lines = ["# Available tools"]
        for tool in self.tools:
            props = tool.get("input_schema", {}).get("properties", {})
            params = ", ".join(props.keys())
            lines.append(f"- {tool['name']}({params}): {tool['description']}")
        return "\n".join(lines)

    def _build_memory_section(self) -> str:
        if not self.memory_dir.exists():
            return ""
        memories = []
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name == "MEMORY.md":
                continue

            text = md_file.read_text()
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
            if not match:
                continue
            header, body = match.group(1), match.group(2)
            meta = {}
            for line in header.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip()
            name = meta.get("name", md_file.stem)
            mem_type = meta.get("type", "project")
            desc = meta.get("description", "")
            memories.append(f"[{mem_type}]: {name} {desc}\n{body}")
        if not memories:
            return ""
        memories.append(MEMORY_GUIDANCE)
        return "# Memories (persistent)\n\n" + "\n\n".join(memories)

    def _build_claude_md(self) -> str:
        """
        Load CLAUDE.md files in priority order (all are included):
        1. ~/.claude/CLAUDE.md (user-global instructions)
        2. <project-root>/CLAUDE.md (project instructions)
        3. <current-subdir>/CLAUDE.md (directory-specific instructions)
        """
        sources = []

        # User-global
        user_claude = Path.home() / ".claude" / "CLAUDE.md"
        if user_claude.exists():
            sources.append(("user global (~/.claude/CLAUDE.md)", user_claude.read_text()))

        # Project root
        project_claude = self.workdir / "CLAUDE.md"
        if project_claude.exists():
            sources.append(("project root (CLAUDE.md)", project_claude.read_text()))

        # Subdirectory -- in real CC, this walks from cwd up to project root
        # Teaching: check cwd if different from workdir
        cwd = Path.cwd()
        if cwd != self.workdir:
            subdir_claude = cwd / "CLAUDE.md"
            if subdir_claude.exists():
                sources.append((f"subdir ({cwd.name}/CLAUDE.md)", subdir_claude.read_text()))

        if not sources:
            return ""
        parts = ["# CLAUDE.md instructions"]
        for label, content in sources:
            parts.append(f"## From {label}")
            parts.append(content.strip())
        return "\n\n".join(parts)

    def _build_dynamic_context(self) -> str:
        lines = [
            f"Current date: {datetime.today().isoformat()}",
            f"Working directory: {self.workdir}",
            f"Model: {MODEL},"
            f"Platform: {platform.system()},"
        ]
        return "# Dynamic context\n" + "\n".join(lines)

    def build(self) -> str:
        """
        Assemble the full system prompt from all sections.

        Static sections (1-5) are separated from dynamic (6) by
        the DYNAMIC_BOUNDARY marker. In real CC, the static prefix
        is cached across turns to save prompt tokens.
        """
        sections = []

        core = self._build_core()
        if core:
            sections.append(core)

        tools = self._build_tool_listing()
        if tools:
            sections.append(tools)

        memory = self._build_memory_section()
        if memory:
            sections.append(memory)

        claude_md = self._build_claude_md()
        if claude_md:
            sections.append(claude_md)

        # Static/dynamic boundary
        sections.append(DYNAMIC_BOUNDARY)

        dynamic = self._build_dynamic_context()
        if dynamic:
            sections.append(dynamic)

        return "\n\n".join(sections)
