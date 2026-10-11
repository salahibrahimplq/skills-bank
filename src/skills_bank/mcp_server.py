"""Minimal MCP server (stdio, JSON-RPC 2.0, zero deps) exposing the bank to Claude Code / Cowork / any MCP client.

Register in Claude Code:   claude mcp add skills-bank -- bank mcp
Or in settings JSON:       {"mcpServers": {"skills-bank": {"command": "bank", "args": ["mcp"]}}}
"""
import json, sys

TOOLS = [
    {"name": "bank_search", "description": "Full-text search the Skills Bank (prompts, agents, skills, workflows, tools, evals). Returns id, type, project, name, description.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "type": {"type": "string", "description": "optional: prompt|agent|skill|workflow|tool|eval|dataset|model|connector"}, "project": {"type": "string"}}, "required": ["query"]}},
    {"name": "bank_list", "description": "List entries, optionally filtered by type and/or project.",
     "inputSchema": {"type": "object", "properties": {"type": {"type": "string"}, "project": {"type": "string"}}}},
    {"name": "bank_get", "description": "Get one entry in full (metadata + body) by id.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "bank_render", "description": "Fill an entry's {{placeholders}} with inputs and return the ready-to-use text.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "inputs": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["id"]}},
    {"name": "bank_deps", "description": "Dependency tree (uses:) and reverse dependencies for an entry.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "bank_skill_writer_prompt", "description": "Return the bank's skill-writer meta-prompt filled with a request, so the calling agent can draft a SKILL.md itself, then save it with bank_add (type=skill).",
     "inputSchema": {"type": "object", "properties": {"request": {"type": "string"}, "project": {"type": "string"}, "existing_skill_id": {"type": "string"}}, "required": ["request"]}},
    {"name": "bank_add", "description": "Create a new entry in the bank. Body may contain {{placeholders}}; list them in inputs.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "type": {"type": "string"}, "name": {"type": "string"}, "project": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "inputs": {"type": "array", "items": {"type": "string"}}, "model": {"type": "string"}, "body": {"type": "string"}}, "required": ["id", "type", "name", "body"]}},
]


def _bank():
    from .api import Bank
    return Bank()


def _slim(e):
    return {k: e.get(k) for k in ("id", "type", "project", "name", "description", "tags", "inputs", "model", "version")}


def call(name, a):
    b = _bank()
    if name == "bank_search":
        rs = b.search(a["query"])
        rs = [e for e in rs if (not a.get("type") or e.get("type") == a["type"]) and (not a.get("project") or e.get("project") == a["project"])]
        return [_slim(e) for e in rs[:30]]
    if name == "bank_list":
        f = {k: a[k] for k in ("type", "project") if a.get(k)}
        return [_slim(e) for e in b.list(**f)]
    if name == "bank_get":
        e = b.get(a["id"]); d = _slim(e); d["body"] = e["_body"].strip(); d["uses"] = e.get("uses"); d["path"] = e["_path"]; return d
    if name == "bank_render":
        return b.render(a["id"], strict=False, **(a.get("inputs") or {}))
    if name == "bank_deps":
        ids = {e["id"]: e for e in b.entries()}
        def down(i, seen):
            if i in seen or i not in ids: return []
            seen.add(i); e = ids[i]
            kids = list(e.get("uses") or []) + ([e["target"]] if e.get("target") else [])
            return [{"id": k, "type": ids.get(k, {}).get("type"), "uses": down(k, seen)} for k in kids]
        up = [e["id"] for e in ids.values() if a["id"] in (e.get("uses") or []) or e.get("target") == a["id"]]
        return {"id": a["id"], "uses": down(a["id"], set()), "used_by": up}
    if name == "bank_skill_writer_prompt":
        ex = b.get(a["existing_skill_id"])["_body"] if a.get("existing_skill_id") else ""
        return b.render("shared-skill-writer", strict=False, request=a["request"], project=a.get("project", "shared"), existing_skill=ex, reference_material="")
    if name == "bank_add":
        from . import cli
        p = cli.ROOT / cli.DIRS[a["type"]] / f"{a['id']}.md"
        if p.exists(): raise ValueError(f"{a['id']} exists")
        fm = {"id": a["id"], "name": a["name"], "type": a["type"], "project": a.get("project", "shared"),
              "tags": a.get("tags") or [], "model": a.get("model", "claude-sonnet-5-5"), "inputs": a.get("inputs") or [], "lang": "en", "version": 1}
        lines = [f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}" for k, v in fm.items()]
        p.write_text("---\n" + "\n".join(lines) + "\n---\n" + a["body"].strip() + "\n", encoding="utf-8")
        cli.cmd_index([])
        return {"created": str(p)}
    raise ValueError(f"unknown tool {name}")


def serve():
    def send(obj):
        sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": params.get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "skills-bank", "version": "0.8.0"}}})
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            try:
                res = call(params["name"], params.get("arguments") or {})
                text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False, indent=1)
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}})
            except Exception as ex:
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"error: {ex}"}], "isError": True}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}})
