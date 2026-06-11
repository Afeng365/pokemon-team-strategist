import subprocess
from pathlib import Path

import requests

from handlers.memory_system import memory_mgr
from handlers.tasks_system import TASKS
from handlers.todomanager import TODO
from settings.constant import WORKDIR

# ── 工具定义 ──────────────────────────────────────────────────────────

BASE_URL = "https://pokeapi.co/api/v2"
SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon"
HEADERS = {"Accept": "application/json"}


def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        fp.write_text(content.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_save_memory(name: str, description: str, mem_type: str, content: str) -> str:
    return memory_mgr.save_memory(name, description, mem_type, content)


def _get(endpoint: str) -> dict:
    """通用 GET 请求封装"""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── 1. 宝可梦基础信息 ──────────────────────────────────────────────

def search_pokemon(id_or_name: str | int) -> dict:
    """按名称或 ID 查询宝可梦基础信息（种族值、属性、图片等）

    返回字段：id, name, stats, types, abilities, moves, sprites
    """
    data = _get(f"pokemon/{id_or_name}")
    return {
        "id": data["id"],
        "name": data["name"],
        "height": data["height"],
        "weight": data["weight"],
        "stats": {s["stat"]["name"]: s["base_stat"] for s in data["stats"]},
        "types": [t["type"]["name"] for t in data["types"]],
        "abilities": [a["ability"]["name"] for a in data["abilities"]],
        "moves": [m["move"]["name"] for m in data["moves"]],
        "sprites": {
            "front_default": data["sprites"]["front_default"],
            "official_artwork": (
                data["sprites"]["other"]["official-artwork"]["front_default"]
            ),
        },
    }


# ── 2. 宝可梦物种信息 ─────────────────────────────────────────────

def get_pokemon_species(id_or_name: str | int) -> dict:
    """查询宝可梦物种信息（图鉴描述、进化链、世代、栖息地）

    返回字段：flavor_text_entries, evolution_chain_url, generation, habitat, is_legendary, is_mythical
    """
    data = _get(f"pokemon-species/{id_or_name}")
    return {
        "id": data["id"],
        "name": data["name"],
        "flavor_text_entries": [
            {
                "flavor_text": e["flavor_text"].replace("\n", " ").replace("\f", " "),
                "language": e["language"]["name"],
                "version": e["version"]["name"],
            }
            for e in data.get("flavor_text_entries", [])
        ],
        "evolution_chain_url": data["evolution_chain"]["url"] if data.get("evolution_chain") else None,
        "generation": data["generation"]["name"] if data.get("generation") else None,
        "habitat": data["habitat"]["name"] if data.get("habitat") else None,
        "is_legendary": data["is_legendary"],
        "is_mythical": data["is_mythical"],
    }


# ── 3. 属性克制关系 ───────────────────────────────────────────────

def get_type_matchups(id_or_name: str | int) -> dict:
    """查询属性克制关系

    返回字段：name, damage_relations
        damage_relations 包含:
        - double_damage_to / double_damage_from
        - half_damage_to / half_damage_from
        - no_damage_to / no_damage_from
    """
    data = _get(f"type/{id_or_name}")
    dr = data.get("damage_relations", {})
    return {
        "id": data["id"],
        "name": data["name"],
        "damage_relations": {
            "double_damage_to": [t["name"] for t in dr.get("double_damage_to", [])],
            "double_damage_from": [t["name"] for t in dr.get("double_damage_from", [])],
            "half_damage_to": [t["name"] for t in dr.get("half_damage_to", [])],
            "half_damage_from": [t["name"] for t in dr.get("half_damage_from", [])],
            "no_damage_to": [t["name"] for t in dr.get("no_damage_to", [])],
            "no_damage_from": [t["name"] for t in dr.get("no_damage_from", [])],
        },
    }


# ── 4. 招式详情 ───────────────────────────────────────────────────

def get_move_detail(id_or_name: str | int) -> dict:
    """查询招式详情

    返回字段：id, name, power, accuracy, pp, type, damage_class, effect_entries
    """
    data = _get(f"move/{id_or_name}")
    return {
        "id": data["id"],
        "name": data["name"],
        "power": data.get("power"),
        "accuracy": data.get("accuracy"),
        "pp": data.get("pp"),
        "type": data["type"]["name"] if data.get("type") else None,
        "damage_class": data["damage_class"]["name"] if data.get("damage_class") else None,
        "effect_entries": [
            {
                "effect": e["effect"],
                "short_effect": e["short_effect"],
                "language": e["language"]["name"],
            }
            for e in data.get("effect_entries", [])
            if e["language"]["name"] == "en"
        ],
    }


# ── 5. 技能详情 ───────────────────────────────────────────────────

def get_ability(id_or_name: str | int) -> dict:
    """查询技能（特性）详情

    返回字段：id, name, effect_entries, pokemon_with_ability
    """
    data = _get(f"ability/{id_or_name}")
    return {
        "id": data["id"],
        "name": data["name"],
        "effect_entries": [
            {
                "effect": e["effect"],
                "short_effect": e["short_effect"],
                "language": e["language"]["name"],
            }
            for e in data.get("effect_entries", [])
            if e["language"]["name"] == "en"
        ],
        "pokemon_with_ability": [p["pokemon"]["name"] for p in data.get("pokemon", [])],
    }


# ── 6. 进化链 ─────────────────────────────────────────────────────

def get_evolution_chain(chain_id: int) -> dict:
    """查询进化链

    返回字段：id, chain（包含嵌套的进化信息）
    """
    data = _get(f"evolution-chain/{chain_id}")

    def _parse_chain(chain: dict) -> dict:
        node = {
            "name": chain["species"]["name"],
            "evolves_to": [],
        }
        for evolution in chain.get("evolves_to", []):
            node["evolves_to"].append(_parse_chain(evolution))
        return node

    return {
        "id": data["id"],
        "chain": _parse_chain(data["chain"]),
    }


# ── 7. 宝可梦列表（分页）─────────────────────────────────────────

def get_pokemon_list(limit: int = 20, offset: int = 0) -> dict:
    """获取宝可梦列表（分页）

    返回字段：count, next, previous, results（name 和 url 列表）
    """
    data = _get(f"pokemon?limit={limit}&offset={offset}")
    return {
        "count": data["count"],
        "next": data.get("next"),
        "previous": data.get("previous"),
        "results": data["results"],
    }


# ── 8. 所有属性列表 ───────────────────────────────────────────────

def get_types() -> dict:
    """获取所有属性列表

    返回字段：count, results（name 和 url 列表）
    """
    data = _get("type")
    return {
        "count": data["count"],
        "results": data["results"],
    }


# ── 9. 世代信息 ───────────────────────────────────────────────────

def get_generation(id_or_name: str | int) -> dict:
    """查询世代信息

    返回字段：id, name, pokemon_species, types, moves, abilities
    """
    data = _get(f"generation/{id_or_name}")
    return {
        "id": data["id"],
        "name": data["name"],
        "pokemon_species": [s["name"] for s in data.get("pokemon_species", [])],
        "types": [t["name"] for t in data.get("types", [])],
        "moves": [m["name"] for m in data.get("moves", [])],
        "abilities": [a["name"] for a in data.get("abilities", [])],
    }


# ── 10. 获取宝可梦图片 URL ────────────────────────────────────────

def get_pokemon_sprite_url(pokemon_id: int, official: bool = True) -> str:
    """获取宝可梦图片地址

    - official=True: 官方高清艺术图
    - official=False: 默认正面图
    """
    if official:
        return f"{SPRITE_URL}/other/official-artwork/{pokemon_id}.png"
    return f"{SPRITE_URL}/{pokemon_id}.png"


NATIVE_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    "save_memory": lambda **kw: run_save_memory(kw["name"], kw["description"], kw["type"], kw["content"]),
    "todo": lambda **kw: TODO.update(kw["items"]),
    "task_create": lambda **kw: TASKS.create(kw["subject"], kw.get("description", "")),
    "task_update": lambda **kw: TASKS.update(kw["task_id"], kw.get("status"), kw.get("owner"), kw.get("addBlockedBy"),
                                             kw.get("addBlocks")),
    "task_list": lambda **kw: TASKS.list_all(),
    "compress": lambda **kw: "Compressing...",
    "task_get": lambda **kw: TASKS.get(kw["task_id"]),
    "search_pokemon": search_pokemon,
    "get_pokemon_species": get_pokemon_species,
    "get_type_matchups": get_type_matchups,
    "get_move_detail": get_move_detail,
    "get_ability": get_ability,
    "get_evolution_chain": get_evolution_chain,
    "get_pokemon_list": get_pokemon_list,
    "get_types": get_types,
    "get_generation": get_generation,
    "get_pokemon_sprite_url": get_pokemon_sprite_url,

}

NATIVE_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}},
                      "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                                       "new_text": {"type": "string"}},
                      "required": ["path", "old_text", "new_text"]}},
    {"name": "save_memory", "description": "Save a persistent memory that survives across sessions.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Short identifier (e.g. prefer_tabs, db_schema)"},
         "description": {"type": "string", "description": "One-line summary of what this memory captures"},
         "type": {"type": "string", "enum": ["user", "feedback", "project", "reference"],
                  "description": "user=dietary preferences, country/region, feedback=corrections, project=non-obvious project conventions or decision reasons, reference=external resource pointers"},
         "content": {"type": "string", "description": "Full memory content (multi-line OK)"},
     }, "required": ["name", "description", "type", "content"]}},
    {
        "name": "todo",
        "description": "Rewrite the current session plan for multi-step work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "Optional present-continuous label.",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
    {"name": "task_create", "description": "Create a new task.",
     "input_schema": {"type": "object",
                      "properties": {"subject": {"type": "string"}, "description": {"type": "string"}},
                      "required": ["subject"]}},
    {"name": "task_update", "description": "Update a task's status, owner, or dependencies.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string",
                                                                                                  "enum": ["pending",
                                                                                                           "in_progress",
                                                                                                           "completed",
                                                                                                           "deleted"]},
                                                       "owner": {"type": "string",
                                                                 "description": "Set when a teammate claims the task"},
                                                       "addBlockedBy": {"type": "array", "items": {"type": "integer"}},
                                                       "addBlocks": {"type": "array", "items": {"type": "integer"}}},
                      "required": ["task_id"]}},
    {"name": "task_list", "description": "List all tasks with status summary.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "task_get", "description": "Get full details of a task by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "compress", "description": "Manually compress conversation context.",
     "input_schema": {"type": "object", "properties": {}}},
    {
        "type": "function",
        "function": {
            "name": "search_pokemon",
            "description": "按id_or_name查询宝可梦基础信息，返回种族值、属性、技能、招式列表和图片URL。例如 search_pokemon('pikachu') 可获取皮卡丘的全部基础数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "宝可梦的名称（如 'pikachu', 'charizard'）或全国图鉴编号ID（如 25, 6）"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_species",
            "description": "使用id_or_name查询宝可梦物种信息，包括图鉴文字描述(flavor_text)、进化链URL、世代、栖息地、是否为传说/幻之宝可梦。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "宝可梦的名称（如 'pikachu'）或物种ID（如 25）"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_type_matchups",
            "description": "使用id_or_name查询宝可梦属性的克制关系，返回该属性对所有其他属性的双倍伤害、半倍伤害和免疫情况（双向）。例如 electric 属性对 water 造成双倍伤害，但受 ground 属性双倍克制。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "属性名称（如 'fire', 'water', 'grass', 'electric', 'dragon' 等）或属性ID"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_move_detail",
            "description": "使用id_or_name查询招式详情，返回威力(power)、命中率(accuracy)、PP值、属性(type)和伤害类型(damage_class)及效果描述。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "招式名称（如 'thunderbolt', 'flamethrower', 'earthquake'）或招式ID"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_ability",
            "description": "使用id_or_name查询宝可梦技能（特性）详情，返回特性的英文效果描述和拥有该特性的所有宝可梦列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "特性名称（如 'static', 'intimidate', 'levitate'）或特性ID"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_evolution_chain",
            "description": "根据chain_id查询宝可梦的进化链，返回嵌套结构的进化树（如 pichu → pikachu → raichu）。注意输入参数是进化链ID，不是宝可梦ID或名称。可先通过 get_pokemon_species 获取进化链URL中的ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chain_id": {
                        "type": "integer",
                        "description": "进化链ID（如 10 对应皮卡丘家族的进化链），可通过 get_pokemon_species 返回的 evolution_chain_url 获取"
                    }
                },
                "required": ["chain_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_list",
            "description": "获取宝可梦列表（分页），返回总数、下一页链接和当前页的结果列表（含名称和URL）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "每页返回数量，默认20，最大可设为100000获取全部列表",
                        "default": 20
                    },
                    "offset": {
                        "type": "integer",
                        "description": "偏移量，用于翻页。第1页 offset=0，第2页 offset=limit",
                        "default": 0
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_types",
            "description": "获取所有宝可梦属性列表，返回属性总数和每个属性的名称及详情URL。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_generation",
            "description": "使用id_or_name查询世代（地区/版本）信息，返回该世代中包含的所有宝可梦、属性、招式、特性列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id_or_name": {
                        "type": ["string", "integer"],
                        "description": "世代名称（如 'generation-i', 'generation-ii'）或世代ID（如 1, 2, 3...）"
                    }
                },
                "required": ["id_or_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pokemon_sprite_url",
            "description": "使用pokemon_id获取宝可梦的图片URL。可生成默认正面图或官方高清艺术图，用于展示宝可梦形象。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pokemon_id": {
                        "type": "integer",
                        "description": "宝可梦的全国图鉴编号ID（如 25 对应皮卡丘）"
                    },
                    "official": {
                        "type": "boolean",
                        "description": "True=官方高清艺术图（推荐），False=默认正面小图",
                        "default": True
                    }
                },
                "required": ["pokemon_id"]
            }
        }
    }

]
