#!/usr/bin/env python3
"""Skills Bank CLI. Zero dependencies.
  find:   list search show deps stats dashboard use
  make:   new create-skill validate prune index export-skill unexport
  run:    render run eval
  sync:   fetch ingest ingest-agents ingest-instructions inventory ingest-all discover sources watch sync-tools
  expose: mcp serve"""
import hashlib, json, os, re, sys, time
from pathlib import Path

def _root():
    env = os.environ.get("SKILLS_BANK_HOME") or os.environ.get("AI_BANK_HOME")
    if env:
        return Path(env).expanduser()
    # walk up from cwd looking for a bank (prompts/ + agents/)
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "prompts").is_dir() and (d / "agents").is_dir():
            return d
    for default in (Path.home() / ".skills-bank", Path.home() / ".ai-bank"):
        if (default / "prompts").is_dir():
            return default
    default = Path.home() / ".skills-bank"
    sys.exit("No Skills Bank found. Set SKILLS_BANK_HOME, or run inside a bank, or clone to " + str(default))

ROOT = _root()
DIRS = {"prompt": "prompts", "agent": "agents", "workflow": "workflows", "model": "models",
        "skill": "skills", "tool": "tools", "connector": "connectors", "eval": "evals", "dataset": "datasets",
        "instruction": "instructions"}
FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def parse_fm(text):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line or line.startswith((" ", "-")):
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        elif v.isdigit():
            v = int(v)
        meta[k.strip()] = v
    return meta, m.group(2)


def entries():
    for d in DIRS.values():
        for p in sorted((ROOT / d).glob("*.md")):
            if p.name.startswith("_"): continue
            meta, body = parse_fm(p.read_text(encoding="utf-8"))
            meta.setdefault("id", p.stem)
            meta["_path"] = str(p.relative_to(ROOT))
            meta["_body"] = body
            yield meta


def find(eid):
    es = list(entries())
    for cand in (eid, "ext-" + eid, "ext-agent-" + eid):
        for e in es:
            if e["id"] == cand:
                return e
    sys.exit(f"not found: {eid}")


def cmd_list(args):
    proj = tag = typ = None
    for a in args:
        if a.startswith("--project="): proj = a.split("=", 1)[1]
        elif a.startswith("--tag="): tag = a.split("=", 1)[1]
        elif a.startswith("--type="): typ = a.split("=", 1)[1]
    # allow "--project jobeng" form
    for i, a in enumerate(args):
        if a == "--project" and i + 1 < len(args): proj = args[i + 1]
        if a == "--tag" and i + 1 < len(args): tag = args[i + 1]
        if a == "--type" and i + 1 < len(args): typ = args[i + 1]
    rows = []
    for e in entries():
        if proj and e.get("project") != proj: continue
        if typ and e.get("type") != typ: continue
        if tag and tag not in (e.get("tags") or []): continue
        rows.append(e)
    w = max((len(e["id"]) for e in rows), default=10)
    for e in rows:
        print(f"{e['id']:<{w}}  {e.get('type','?'):<8} {e.get('project','?'):<9} {e.get('name','')}")
    print(f"\n{len(rows)} entries")


def cmd_search(args):
    q = " ".join(args).lower()
    for e in entries():
        hay = json.dumps({k: v for k, v in e.items() if not k.startswith("_")}).lower() + e["_body"].lower()
        if q in hay:
            print(f"{e['id']:<36} {e.get('name','')}  ({e['_path']})")


def cmd_show(args):
    e = find(args[0])
    print((ROOT / e["_path"]).read_text(encoding="utf-8"))


def cmd_render(args):
    e = find(args[0])
    vals = {}
    for kv in args[1:]:
        k, v = kv.split("=", 1)
        vals[k] = Path(v[1:]).read_text(encoding="utf-8") if v.startswith("@") else v
    out = e["_body"]
    missing = []
    for name in e.get("inputs") or []:
        if name in vals:
            out = out.replace("{{" + name + "}}", vals[name])
        else:
            missing.append(name)
    if missing:
        print(f"# WARNING missing inputs: {', '.join(missing)}", file=sys.stderr)
    print(out)


def cmd_new(args):
    typ, eid = args[0], args[1]
    if typ not in DIRS:
        sys.exit(f"type must be one of {list(DIRS)}")
    p = ROOT / DIRS[typ] / f"{eid}.md"
    if p.exists():
        sys.exit(f"exists: {p}")
    p.write_text(f"""---
id: {eid}
name: {eid.replace('-', ' ').title()}
type: {typ}
project: shared
tags: []
model: claude-sonnet-5-5
inputs: []
lang: en
version: 1
---
<write the {typ} here — use {{{{input_name}}}} placeholders>
""", encoding="utf-8")
    print(f"created {p.relative_to(ROOT)}")
    cmd_index([])


def cmd_index(args):
    idx = [{k: v for k, v in e.items() if k != "_body"} for e in entries()]
    (ROOT / "index.json").write_text(json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"indexed {len(idx)} entries -> index.json")
    if (ROOT / "dashboard.html").exists() and "--no-dashboard" not in args:   # keep an existing dashboard current
        try: cmd_dashboard(["--no-open", "--quiet"])
        except Exception as ex: print("dashboard not rebuilt:", ex)


def cmd_deps(args):
    """Print the dependency tree of an entry (follows `uses:` and `target:`)."""
    seen = set()
    def walk(eid, depth=0):
        if eid in seen: return
        seen.add(eid)
        e = find(eid)
        print("  " * depth + f"{eid}  ({e.get('type')})")
        kids = list(e.get("uses") or [])
        if e.get("target"): kids.append(e["target"])
        for k in kids: walk(k, depth + 1)
    walk(args[0])


def skill_body(e):
    """Body for a SKILL.md: prompts with {{inputs}} become 'collect these, then follow the template'."""
    body = e["_body"].strip()
    ins = e.get("inputs") or []
    if not ins or e.get("type") == "skill":
        return body
    lines = ["## Inputs to collect first", "Ask the user for any of these not already given (one short question, all at once):"]
    lines += [f"- **{i}**" for i in ins]
    lines += ["", "## Then follow this template, substituting the inputs for the {{placeholders}}", "", body]
    if e.get("model"): lines += ["", f"_Preferred model: {e['model']}_"]
    return "\n".join(lines)


def cmd_export_skill(args):
    """export-skill <id|all> [--to DIR] [--types skill,prompt,agent] -> DIR/<id>/SKILL.md (Claude Code / Cowork format)"""
    """export-skill <id|all> [--to DIR]  -> DIR/<id>/SKILL.md (Claude Code / Cowork format)"""
    dest = Path("~/.claude/skills").expanduser()
    if "--to" in args: dest = Path(args[args.index("--to") + 1]).expanduser()
    types = set(args[args.index("--types") + 1].split(",")) if "--types" in args else {"skill"}
    ids = [e["id"] for e in entries() if e.get("type") in types] if args[0] == "all" else [args[0]]
    for eid in ids:
        e = find(eid); eid = e["id"]
        if e.get("type") not in ("skill", "prompt", "agent", "workflow"): sys.exit(f"{eid} is a {e.get('type')} — only skill/prompt/agent/workflow export")
        pub = eid[4:] if eid.startswith("ext-") else eid          # public name: no ext- prefix
        d = dest / pub; d.mkdir(parents=True, exist_ok=True)
        desc = str(e.get("description") or e.get("name", pub)).strip().strip('"').strip("'").replace("\\'", "'")
        trig = e.get("triggers") or []
        if trig: desc += ". Use when the user says: " + ", ".join(str(t) for t in trig)
        desc = desc.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        (d / "SKILL.md").write_text(f'---\nname: {pub}\ndescription: "{desc}"\n---\n{skill_body(e)}\n', encoding="utf-8")
        (d / ".skills-bank-export").write_text(eid + "\n")
        a = ROOT / "skills" / "_assets" / eid
        if a.is_dir():
            import shutil
            for f in a.rglob("*"):
                if f.is_file():
                    t = d / f.relative_to(a); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, t)
        print(f"exported {d / 'SKILL.md'}" + (f" (+assets)" if a.is_dir() else ""))


def cmd_unexport(args):
    """unexport [id|all] [--to DIR] -> remove skills that `export-skill` placed in DIR (marker .skills-bank-export)"""
    import shutil
    dest = Path(args[args.index("--to") + 1]).expanduser() if "--to" in args else Path("~/.claude/skills").expanduser()
    want = None if not args or args[0] in ("all", "--to") else {args[0], "ext-" + args[0]}
    n = 0
    for d in sorted(dest.iterdir()) if dest.is_dir() else []:
        m = d / ".skills-bank-export"
        if not m.exists(): m = d / ".ai-bank-export"
        if d.is_dir() and m.exists() and (want is None or m.read_text().strip() in want):
            shutil.rmtree(d); n += 1; print(f"removed {d}")
    print(f"{n} exported skill(s) removed from {dest}")


def cmd_create_skill(args):
    """create-skill "<what it should do>" [--project P] [--from FILE] [--improve ID] [--model M] [--export] [--dry]
    Drafts a SKILL.md with Claude (ANTHROPIC_API_KEY), saves to skills/<name>.md, validates. Without a key: prints the prompt to paste."""
    api = _mod("api"); b = api.Bank()
    req = next((a for a in args if not a.startswith("--") and args[max(0, args.index(a) - 1)] not in ("--project", "--from", "--improve", "--model")), "")
    proj = args[args.index("--project") + 1] if "--project" in args else "shared"
    model = args[args.index("--model") + 1] if "--model" in args else None
    ref = Path(args[args.index("--from") + 1]).expanduser().read_text(encoding="utf-8", errors="replace")[:20000] if "--from" in args else ""
    existing = ""
    if "--improve" in args:
        e = find(args[args.index("--improve") + 1]); existing = (ROOT / e["_path"]).read_text(encoding="utf-8")
        req = req or f"Improve this skill: tighten triggers, make steps verifiable, add missing rules. Keep its purpose."
    if not req and not ref: sys.exit("give a description, --from FILE, or --improve ID")
    prompt = b.render("shared-skill-writer", strict=False, request=req or "Turn the reference material into a skill.", project=proj, existing_skill=existing, reference_material=ref)
    import shutil
    if not (os.environ.get("ANTHROPIC_API_KEY") or shutil.which("claude")) or "--print-prompt" in args:
        print("# No API key or `claude` CLI — paste this into Claude, then: bank new skill <name> and replace the body\n")
        print(prompt); return
    via = "API" if os.environ.get("ANTHROPIC_API_KEY") and not os.environ["ANTHROPIC_API_KEY"].endswith("...") else "claude CLI"
    print(f"drafting via {via}…", file=sys.stderr)
    try:
        out = api.messages(prompt, model=model or ("claude-opus-5-5" if via == "API" else None), max_tokens=3000).strip()
    except Exception as ex:
        sys.exit(f"error: {ex}")
    out = re.sub(r"^```[a-z]*\n|\n```$", "", out).strip()
    meta, body = parse_fm(out)
    name = _slug(str(meta.get("name") or req[:40]))
    if "--improve" in args:
        name = find(args[args.index("--improve") + 1])["id"]
    dest = ROOT / "skills" / f"{name}.md"
    ver = 1
    if dest.exists() and "--improve" not in args:
        name = f"{name}-{_hash(out)[:4]}"; dest = ROOT / "skills" / f"{name}.md"
    if "--improve" in args:
        ver = int(parse_fm(existing)[0].get("version", 1)) + 1
    fm = ["---", f"id: {name}", f"name: {meta.get('name', name)}", "type: skill", f"project: {proj}",
          f"tags: [{', '.join(meta.get('tags') or ['generated'])}]", f"inputs: [{', '.join(meta.get('inputs') or [])}]",
          f'description: "{str(meta.get("description", "")).replace(chr(34), chr(39))}"', f"model: {model or 'claude-sonnet-5-5'}",
          f"generated: {time.strftime('%Y-%m-%d')}", f"version: {ver}", "---"]
    text = "\n".join(fm) + "\n" + body.strip() + "\n"
    if "--dry" in args:
        print(text); return
    dest.write_text(text, encoding="utf-8")
    print(f"saved {dest.relative_to(ROOT)}"); cmd_index([])
    probs = [p for p in [] ]
    cmd_validate([])
    if "--export" in args: cmd_export_skill([name])
    print(f"\nnext: bank show {name}   |   bank export-skill {name}   |   bank create-skill --improve {name} \"<feedback>\"")


def cmd_prune(args):
    """prune [ID-GLOB] [--type T] [--project P] [--origin REGEX] [--dry] -> delete matching entries (+assets). Always preview with --dry first."""
    import fnmatch, shutil
    dry = "--dry" in args
    glob_ = next((a for a in args if not a.startswith("--") and args[max(0, args.index(a) - 1)] not in ("--type", "--project", "--origin")), "*")
    typ = args[args.index("--type") + 1] if "--type" in args else None
    proj = args[args.index("--project") + 1] if "--project" in args else None
    orx = re.compile(args[args.index("--origin") + 1]) if "--origin" in args else None
    if glob_ == "*" and not (typ or proj or orx): sys.exit("refusing to prune everything — give a glob, --type, --project or --origin")
    n = 0
    for e in entries():
        if not fnmatch.fnmatch(e["id"], glob_): continue
        if typ and e.get("type") != typ: continue
        if proj and e.get("project") != proj: continue
        if orx and not orx.search(str(e.get("origin", ""))): continue
        n += 1; print(f"[{'dry' if dry else 'rm'}] {e['id']:<48} {e.get('type','')}  {e.get('origin','')}"[:160])
        if not dry:
            (ROOT / e["_path"]).unlink(missing_ok=True)
            a = ROOT / "skills" / "_assets" / e["id"]
            if a.is_dir(): shutil.rmtree(a)
    print(f"{n} entr{'y' if n == 1 else 'ies'} {'would be ' if dry else ''}removed")
    if n and not dry: cmd_index([])


def cmd_validate(args):
    bad = 0
    ids = {}
    for e in entries():
        probs = []
        for req in ("id", "name", "type", "project"):
            if req not in e: probs.append(f"missing {req}")
        if e.get("type") not in DIRS: probs.append(f"bad type {e.get('type')}")
        if e["id"] in ids: probs.append(f"duplicate id (also {ids[e['id']]})")
        ids[e["id"]] = e["_path"]
        for ph in ([] if "ingested" in (e.get("tags") or []) else set(re.findall(r"{{(\w+)}}", e["_body"]))):
            if ph.isupper(): continue  # env placeholder
            if ph not in (e.get("inputs") or []): probs.append(f"placeholder {{{{{ph}}}}} not in inputs")
        if probs:
            bad += 1; print(f"{e['_path']}: " + "; ".join(probs))
    all_ids = set(ids)
    for e in entries():
        for u in (e.get("uses") or []) + ([e["target"]] if e.get("target") else []):
            if u not in all_ids: bad += 1; print(f"{e['_path']}: uses unknown id {u}")
    print("OK" if not bad else f"{bad} problem(s)")


def cmd_stats(args):
    from collections import Counter
    es = list(entries())
    print(f"{len(es)} entries")
    for label, key in (("by type", "type"), ("by project", "project")):
        print(label + ":")
        for k, n in sorted(Counter(e.get(key, "?") for e in es).items()): print(f"  {k:<10} {n}")


# ---------- ingest: auto-import skills from wherever they appear ----------
DEFAULT_SOURCES = [
    "~/.claude/skills",                 # Claude Code user skills
    "~/.claude/plugins/*/skills",       # Claude Code plugins
    "~/.claude/plugins/cache/*/*/skills",
    "~/Library/Application Support/Claude/skills",   # Cowork / desktop (macOS)
    "~/.config/claude/skills",
    "~/.*/skills",                      # any AI tool: ~/.codex, ~/.agents, ~/.kiro, ~/.roo, ~/.openclaw ...
    "~/.*/skills/.system",              # codex system skills
    "~/.config/*/skills",               # goose, devin, crush ...
    "~/.config/*/harness",              # kimchi
    "./.claude/skills",                 # project-local skills
]


def _sources(patterns=None):
    env = os.environ.get("SKILLS_BANK_SOURCES") or os.environ.get("AI_BANK_SOURCES")
    srcs = list(patterns) if patterns else ([x for x in env.split(os.pathsep) if x] if env else list(DEFAULT_SOURCES))
    cfg = ROOT / "sources.txt"
    if cfg.exists() and not patterns:
        srcs += [l.strip() for l in cfg.read_text().splitlines() if l.strip() and not l.startswith("#")]
    out = []
    for pat in srcs:
        pat = os.path.expanduser(pat)
        try:
            if any(c in pat for c in "*?["):
                base = Path(pat.split("*", 1)[0]).parent if "*" in pat else Path(pat)
                rel = os.path.relpath(pat, base)
                if base.exists():
                    for d in base.glob(rel):
                        try:
                            if d.is_dir(): out.append(d)
                        except OSError: pass
            elif Path(pat).is_dir():
                out.append(Path(pat))
        except OSError:
            pass  # unreadable/protected location — skip silently
    rr = str(ROOT.resolve())
    return [d for d in out if not str(d.resolve()).startswith(rr)]  # never scan the bank itself (incl. _remote)


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "skill"


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


ASSET_CAP = 3_000_000


def _copy_assets(skdir, eid, dry):
    """Copy a skill folder's supporting files (scripts/, references/, assets/ …) into skills/_assets/<eid>/. Returns list of relative paths."""
    import shutil
    files = [f for f in skdir.rglob("*") if f.is_file() and f.name != "SKILL.md" and "node_modules" not in f.parts and ".git" not in f.parts]
    if not files: return []
    total = sum(f.stat().st_size for f in files)
    if total > ASSET_CAP: return [f"(skipped: {total//1000} KB > cap)"]
    dest = ROOT / "skills" / "_assets" / eid
    if not dry:
        if dest.exists(): shutil.rmtree(dest)
        for f in files:
            t = dest / f.relative_to(skdir); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, t)
    return [str(f.relative_to(skdir)) for f in files]


def cmd_ingest(args):
    """ingest [--dry] [--project P] [--with-assets] [DIR ...]  -> import new/changed SKILL.md into skills/"""
    dry = "--dry" in args
    proj = args[args.index("--project") + 1] if "--project" in args else "shared"
    with_assets = "--with-assets" in args
    extra = [Path(a).expanduser() for a in args if not a.startswith("--") and a != proj]
    roots = extra or _sources()
    existing = {e["id"]: e for e in entries()}
    by_hash = {e.get("source_hash"): e["id"] for e in existing.values() if e.get("source_hash")}
    found = new = updated = 0
    for root in roots:
        try:
            skill_files = sorted(root.rglob("SKILL.md"))
        except OSError:
            continue
        for sk in skill_files:
            if "node_modules" in sk.parts: continue
            if (sk.parent / ".skills-bank-export").exists() or (sk.parent / ".ai-bank-export").exists(): continue   # our own export — never re-ingest
            try:
                text = sk.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta, body = parse_fm(text)
            inside = str(sk.resolve()).startswith(str(ROOT.resolve()))
            if meta.get("source_hash") or (inside and "_remote" not in sk.resolve().parts):
                continue
            found += 1
            name = str(meta.get("name") or sk.parent.name)
            eid = "ext-" + _slug(name)
            h = _hash(text)
            if h in by_hash:
                # identical content already in bank: just record this extra location
                dup = ROOT / "skills" / f"{by_hash[h]}.md"
                txt = dup.read_text(encoding="utf-8")
                if str(sk) not in txt:
                    txt = txt.replace("\n---\n", f"\nalso_at: {sk}\n---\n", 1)
                    if not dry: dup.write_text(txt, encoding="utf-8")
                continue
            prev = existing.get(eid)
            if prev and prev.get("source_hash") == h:
                continue
            # same name but different content from a *different* origin -> keep both as variants
            if prev and str(prev.get("origin", "")) != str(sk):
                eid = f"{eid}-{h[:6]}"
                prev = existing.get(eid)
                if prev and prev.get("source_hash") == h:
                    continue
            dest = ROOT / "skills" / f"{eid}.md"
            desc = str(meta.get("description", "")).replace("\n", " ")
            ver = (prev.get("version", 0) + 1) if prev else 1
            fm = f"""---
id: {eid}
name: {name}
type: skill
project: {prev.get("project", proj) if prev else proj}
tags: [external, ingested]
origin: {sk}
origin_root: {root}
source_hash: {h}
ingested: {time.strftime("%Y-%m-%d")}
description: "{desc.replace('"', "'")}"
version: {ver}
---
"""
            action = "update" if prev else "new"
            if action == "new": new += 1
            else: updated += 1
            print(f"[{action:>6}] {eid:<40} <- {sk}")
            if with_assets:
                assets = _copy_assets(sk.parent, eid, dry)
                if assets: fm = fm.replace("\n---\n", f"\nassets: {len(assets)} file(s) in skills/_assets/{eid}/\n---\n", 1)
            if not dry:
                dest.write_text(fm + body.strip() + "\n", encoding="utf-8")
            by_hash[h] = eid
            existing[eid] = {"id": eid, "source_hash": h, "project": proj, "version": ver, "origin": str(sk)}
    print(f"scanned {len(roots)} source dir(s), {found} skills found, {new} new, {updated} updated"
          + (" (dry run)" if dry else ""))
    if not dry and (new or updated):
        cmd_index([])


SKIP_DIRS = {"node_modules", ".git", ".Trash", "Library/Caches", ".cache", ".npm", ".nvm", ".cocoapods", "Pictures", "Movies", "Music", ".Trash", "DerivedData", "venv", ".venv", "site-packages", "__pycache__"}


def cmd_discover(args):
    """discover [DIR=~] [--ingest] [--max-seconds 120] -> sweep the disk for SKILL.md files outside the default sources"""
    base = Path(next((a for a in args if not a.startswith("--")), "~")).expanduser()
    budget = int(args[args.index("--max-seconds") + 1]) if "--max-seconds" in args else 120
    known = {str(r) for r in _sources()}
    t0 = time.time(); found = {}; scanned = 0
    stack = [base]
    while stack and time.time() - t0 < budget:
        d = stack.pop()
        try: kids = list(d.iterdir())
        except (PermissionError, OSError): continue
        for ch in kids:
          try:
                name = ch.name
                if name in SKIP_DIRS or (name.startswith(".") and name not in (".claude", ".config", ".agents", ".codex") and d != base):
                    continue
                if ch.is_symlink(): continue
                if ch.is_dir():
                    if any(str(ch).startswith(k) for k in known): continue   # already covered by ingest
                    stack.append(ch); scanned += 1
                elif name == "SKILL.md":
                    found.setdefault(str(ch.parent.parent), []).append(ch)
          except (PermissionError, OSError):
            continue
    roots = sorted(found, key=lambda k: -len(found[k]))
    for r in roots: print(f"{len(found[r]):>4}  {r}")
    print(f"{sum(len(v) for v in found.values())} skills in {len(roots)} new location(s); scanned {scanned} dirs in {time.time()-t0:.0f}s" + (" (time budget hit — rerun with --max-seconds)" if stack else ""))
    if "--ingest" in args and roots:
        cmd_ingest(roots)
        # remember these roots for future ingests
        cfg = ROOT / "sources.txt"
        old = cfg.read_text().splitlines() if cfg.exists() else []
        cfg.write_text("\n".join(sorted(set(old + roots))) + "\n")
        print(f"saved {len(roots)} root(s) to {cfg} — ingest will scan them from now on")


AGENT_SOURCES = ["~/.claude/agents", "~/.*/agents", "~/.config/*/agents", "./.claude/agents", "~/.claude/plugins/*/agents", "~/.claude/plugins/cache/*/*/agents"]
LOCALE_SKIP = {"docs", "doc", "i18n", "locales", "locale", "translations", "lang", "languages", "_remote", "examples", "templates", "test", "tests", "fixtures"}
INSTRUCTION_NAMES = {"CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules", ".windsurfrules", ".clinerules", "copilot-instructions.md", "QWEN.md", "CONVENTIONS.md"}
AI_TOOLS = {  # dotfolder -> display name
    "claude": "Claude Code", "codex": "OpenAI Codex", "cursor": "Cursor", "kiro": "Kiro", "roo": "Roo Code", "cline": "Cline", "continue": "Continue",
    "aider-desk": "Aider Desk", "aider": "Aider", "gemini": "Gemini CLI", "copilot": "GitHub Copilot", "windsurf": "Windsurf", "trae": "Trae", "trae-cn": "Trae CN",
    "qoder": "Qoder", "qoder-cn": "Qoder CN", "zed": "Zed", "ollama": "Ollama", "lmstudio": "LM Studio", "openclaw": "OpenClaw", "kilocode": "Kilo Code",
    "agents": "Agents (shared skills)", "factory": "Factory Droid", "hermes": "Hermes", "augment": "Augment", "codeium": "Codeium", "tabnine": "Tabnine",
    "junie": "JetBrains Junie", "rovodev": "Atlassian Rovo Dev", "qwen": "Qwen Code", "kimi-code": "Kimi Code", "minimax": "MiniMax", "grok": "Grok",
    "iflow": "iFlow", "lingma": "Alibaba Lingma", "codebuddy": "CodeBuddy", "openhands": "OpenHands", "claude-mem": "claude-mem", "bob": "IBM Bob",
    "autohand": "Autohand", "commandcode": "CommandCode", "forge": "Forge", "mux": "Mux", "neovate": "Neovate", "pi": "Pi", "pochi": "Pochi", "zencoder": "Zencoder",
    "codex-cli": "Codex CLI", "goose": "Goose", "devin": "Devin", "crush": "Crush", "kimchi": "Kimchi", "mcpjam": "MCPJam", "mcporter": "MCPorter", "omniroute": "OmniRoute",
    "agent-reach": "Agent Reach", "ona": "Ona", "opencli": "OpenCLI", "reasonix": "Reasonix", "terramind": "Terramind", "vibe": "Vibe", "zcode": "ZCode", "kode": "Kode",
    "jazz": "Jazz", "moxby": "Moxby", "inferencesh": "inference.sh", "graphify": "Graphify", "codeartsdoer": "CodeArts Doer", "codemaker": "CodeMaker", "codestudio": "CodeStudio",
}
AI_CLIS = ["claude", "codex", "gemini", "aider", "ollama", "cursor", "goose", "crush", "opencode", "kiro", "roo", "copilot", "qwen", "kimi", "droid", "openhands", "jules", "amp", "cline"]
AI_APPS = ["Claude", "ChatGPT", "Cursor", "Windsurf", "Zed", "Kiro", "Trae", "Ollama", "LM Studio", "Visual Studio Code", "Warp", "Raycast", "Perplexity", "Gemini", "Msty", "Jan", "Aider Desk", "Qoder", "Xcode"]


def _ingest_file(sk, kind, eid, name, proj, extra_tags, existing, by_hash, dry):
    """Shared by agents/instructions ingest. Returns 'new'|'update'|'dup'|'same'."""
    try: text = sk.read_text(encoding="utf-8", errors="replace")
    except OSError: return "skip"
    meta, body = parse_fm(text)
    if meta.get("source_hash"): return "skip"
    h = _hash(text)
    if h in by_hash: return "dup"
    prev = existing.get(eid)
    if prev and prev.get("source_hash") == h: return "same"
    if prev and str(prev.get("origin", "")) != str(sk):
        eid = f"{eid}-{h[:6]}"; prev = existing.get(eid)
        if prev and prev.get("source_hash") == h: return "same"
    desc = str(meta.get("description", "")).replace("\n", " ").replace('"', "'")
    ver = (prev.get("version", 0) + 1) if prev else 1
    fm = f"""---
id: {eid}
name: {name}
type: {kind}
project: {prev.get("project", proj) if prev else proj}
tags: [external, ingested, {", ".join(extra_tags)}]
origin: {sk}
source_hash: {h}
ingested: {time.strftime("%Y-%m-%d")}
description: "{desc}"
version: {ver}
---
"""
    extra = "".join(f"{k}: {v}\n" for k, v in meta.items() if k in ("tools", "model", "color") and not isinstance(v, list))
    if extra: fm = fm.replace("\n---\n", "\n" + extra + "---\n", 1) if fm.count("---") >= 2 else fm
    if not dry:
        (ROOT / DIRS[kind] / f"{eid}.md").write_text(fm + body.strip() + "\n", encoding="utf-8")
    by_hash[h] = eid; existing[eid] = {"id": eid, "source_hash": h, "origin": str(sk), "version": ver}
    return "update" if prev else "new"


def cmd_ingest_agents(args):
    """ingest-agents [--dry] [DIR ...] -> import agent definitions (agents/*.md) from every AI tool"""
    dry = "--dry" in args
    extra = [Path(a).expanduser() for a in args if not a.startswith("--")]
    roots = extra or _sources(AGENT_SOURCES)
    existing = {e["id"]: e for e in entries()}
    by_hash = {e.get("source_hash"): e["id"] for e in existing.values() if e.get("source_hash")}
    c = {"new": 0, "update": 0, "dup": 0, "same": 0, "skip": 0}
    for r in roots:
        try: files = sorted(x for x in r.rglob("*.md") if "node_modules" not in x.parts and x.name != "README.md")
        except OSError: continue
        for f in files:
            meta, _ = parse_fm(f.read_text(encoding="utf-8", errors="replace")) if f.stat().st_size < 400_000 else ({}, "")
            name = str(meta.get("name") or f.stem)
            res = _ingest_file(f, "agent", "ext-agent-" + _slug(name), name, "shared", ["agent-def", tool_of_path(f)], existing, by_hash, dry)
            c[res] += 1
            if res in ("new", "update"): print(f"[{res:>6}] ext-agent-{_slug(name):<34} <- {f}")
    print(f"agents: scanned {len(roots)} dir(s): {c['new']} new, {c['update']} updated, {c['dup']} duplicates, {c['same']} unchanged" + (" (dry)" if dry else ""))
    if not dry and (c["new"] or c["update"]): cmd_index([])


def tool_of_path(p):
    m = re.search(r"/\.([A-Za-z0-9_-]+)/", str(p))
    return m.group(1) if m else "other"


def cmd_ingest_instructions(args):
    """ingest-instructions [--dry] [DIR=~] [--max-seconds 120] -> find CLAUDE.md / AGENTS.md / .cursorrules / GEMINI.md … in project folders and store them"""
    dry = "--dry" in args
    base = Path(next((a for a in args if not a.startswith("--") and not a.isdigit()), "~")).expanduser()
    budget = int(args[args.index("--max-seconds") + 1]) if "--max-seconds" in args else 120
    existing = {e["id"]: e for e in entries()}
    by_hash = {e.get("source_hash"): e["id"] for e in existing.values() if e.get("source_hash")}
    t0 = time.time(); stack = [base]; c = {"new": 0, "update": 0, "dup": 0, "same": 0, "skip": 0}
    while stack and time.time() - t0 < budget:
        d = stack.pop()
        try: kids = list(d.iterdir())
        except (PermissionError, OSError): continue
        for ch in kids:
          try:
                n = ch.name
                if ch.is_symlink(): continue
                if ch.is_dir():
                    if n in SKIP_DIRS or (n.startswith(".") and n not in (".claude", ".github", ".cursor")): continue
                    if str(ch) == str(ROOT): continue
                    if n == "agents" and d.name == ".claude":   # per-project agents
                        for f in sorted(ch.glob("*.md")):
                            meta, _ = parse_fm(f.read_text(encoding="utf-8", errors="replace"))
                            nm = str(meta.get("name") or f.stem); proj = _slug(d.parent.name)
                            res = _ingest_file(f, "agent", f"ext-agent-{proj}-{_slug(nm)}", nm, proj, ["agent-def", "project"], existing, by_hash, dry)
                            c[res] += 1
                            if res in ("new", "update"): print(f"[{res:>6}] ext-agent-{proj}-{_slug(nm):<30} <- {f}")
                        continue
                    stack.append(ch)
                elif n in INSTRUCTION_NAMES and ch.stat().st_size > 40:
                    parts = [x.lower() for x in ch.parts]
                    if any(x in LOCALE_SKIP for x in parts) or any(re.fullmatch(r"[a-z]{2}(-[a-z]{2,4})?", x) for x in parts[-3:-1]):
                        continue   # translated docs (zh-tw/, docs/i18n/…), not project rules
                    proj = _slug(ch.parent.name if ch.parent.name not in (".claude", ".github", ".cursor") else ch.parent.parent.name)
                    eid = f"ext-rules-{proj}-{_slug(n.strip('.').replace('.md',''))}"
                    res = _ingest_file(ch, "instruction", eid, f"{proj}: {n}", proj, ["rules", _slug(n.strip('.'))], existing, by_hash, dry)
                    c[res] += 1
                    if res in ("new", "update"): print(f"[{res:>6}] {eid:<44} <- {ch}")
          except (PermissionError, OSError): continue
    print(f"instructions: {c['new']} new, {c['update']} updated, {c['dup']} dup, {c['same']} unchanged in {time.time()-t0:.0f}s" + (" (budget hit)" if stack else "") + (" (dry)" if dry else ""))
    if not dry and (c["new"] or c["update"]): cmd_index([])


def cmd_inventory(args):
    """inventory -> detect every AI tool on this machine (dotfolders, CLIs, apps) and write connectors/ai-tools-inventory.md"""
    import shutil, subprocess
    home = Path.home(); rows = []
    for d in sorted(home.iterdir()):
        if not d.name.startswith(".") or not d.is_dir(): continue
        key = d.name[1:]
        if key not in AI_TOOLS: continue
        sk = ag = 0
        for sub in ("skills", "agents", "plugins"):
            p = d / sub
            if p.is_dir():
                try:
                    if sub == "agents": ag += sum(1 for _ in p.rglob("*.md"))
                    else: sk += sum(1 for _ in p.rglob("SKILL.md"))
                except OSError: pass
        rows.append((AI_TOOLS[key], f"~/.{key}", sk, ag))
    cfg = home / ".config"
    if cfg.is_dir():
        for d in sorted(cfg.iterdir()):
            if d.is_dir() and d.name in AI_TOOLS:
                sk = sum(1 for _ in d.rglob("SKILL.md")) if (d / "skills").is_dir() or (d / "harness").is_dir() else 0
                rows.append((AI_TOOLS[d.name], f"~/.config/{d.name}", sk, 0))
    clis = []
    for c in AI_CLIS:
        p = shutil.which(c)
        if p:
            try: v = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0][:40]
            except Exception: v = ""
            clis.append((c, p, v))
    apps = [a for a in AI_APPS if Path(f"/Applications/{a}.app").exists() or (home / "Applications" / f"{a}.app").exists()]
    mcp = []
    for f in [home / ".claude.json", home / ".claude" / "settings.json", home / ".codex" / "config.toml", home / ".cursor" / "mcp.json", home / "Library/Application Support/Claude/claude_desktop_config.json"]:
        try:
            if f.exists(): mcp.append((str(f).replace(str(home), "~"), len(re.findall(r'"(?:command|url)"\s*:', f.read_text(errors="replace")))))
        except OSError: pass
    out = ["---", "id: ai-tools-inventory", "name: AI Tools Inventory", "type: connector", "project: shared", "tags: [inventory, ai-tools, auto]",
           f"generated: {time.strftime('%Y-%m-%d')}", "version: 1", "---", f"Auto-generated by `bank inventory` on {time.strftime('%Y-%m-%d')}. {len(rows)} config folders, {len(clis)} CLIs, {len(apps)} apps.", "",
           "## Config folders", "| Tool | Path | Skills | Agents |", "|---|---|---|---|"] + [f"| {n} | `{p}` | {s} | {a} |" for n, p, s, a in rows]
    out += ["", "## CLIs on PATH", "| CLI | Path | Version |", "|---|---|---|"] + [f"| {c} | `{p}` | {v} |" for c, p, v in clis]
    out += ["", "## Apps", ", ".join(apps) or "none detected", "", "## MCP config files", "| File | server entries |", "|---|---|"] + [f"| `{f}` | {n} |" for f, n in mcp]
    dest = ROOT / "connectors" / "ai-tools-inventory.md"; dest.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[9:])); print(f"\nwritten {dest}"); cmd_index([])


def cmd_ingest_all(args):
    """ingest-all [--dry] -> skills + agents + instructions + inventory in one go"""
    cmd_ingest(args); cmd_ingest_agents(args); cmd_ingest_instructions(args + ["--max-seconds", "90"]);
    if (ROOT / "remotes.txt").exists() and "--dry" not in args:
        try: cmd_fetch(["--update"])
        except SystemExit: pass
    if "--dry" not in args: cmd_inventory([])


def _repo_slug(spec):
    spec = spec.strip().rstrip("/")
    spec = re.sub(r"^(https?://github\.com/|git@github\.com:)", "", spec).removesuffix(".git")
    if "/" not in spec: sys.exit(f"use owner/repo or a GitHub URL: {spec}")
    return spec


def cmd_fetch(args):
    """fetch <owner/repo|url> [--project P] [--branch B] [--no-assets]   | fetch --update  | fetch --list
    Clone a GitHub repo into <bank>/_remote/<owner>__<repo>, ingest every SKILL.md (+assets), remember it."""
    import subprocess
    cache = ROOT / "_remote"; cache.mkdir(exist_ok=True)
    reg = ROOT / "remotes.txt"
    known = [l.split() for l in reg.read_text().splitlines() if l.strip()] if reg.exists() else []
    if "--list" in args:
        for k in known: print("  ".join(k))
        print(f"{len(known)} remote(s)"); return
    if "--update" in args:
        for k in known:
            slug, proj = k[0], (k[1] if len(k) > 1 else "github")
            d = cache / slug.replace("/", "__")
            print(f"== {slug}")
            if d.exists(): subprocess.run(["git", "-C", str(d), "pull", "-q", "--ff-only"], check=False)
            else: subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{slug}.git", str(d)], check=False)
            cmd_ingest(["--project", proj, "--with-assets", str(d)])
        return
    spec = next((a for a in args if not a.startswith("--")), None)
    if not spec: sys.exit("usage: bank fetch owner/repo [--project P]")
    slug = _repo_slug(spec)
    proj = args[args.index("--project") + 1] if "--project" in args else "github:" + slug.split("/")[0]
    d = cache / slug.replace("/", "__")
    cmd = ["git", "clone", "-q", "--depth", "1"] + (["-b", args[args.index("--branch") + 1]] if "--branch" in args else []) + [f"https://github.com/{slug}.git", str(d)]
    if d.exists(): subprocess.run(["git", "-C", str(d), "pull", "-q", "--ff-only"], check=False)
    else:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode: sys.exit(f"clone failed: {r.stderr.strip()[:300]}")
    n = sum(1 for _ in d.rglob("SKILL.md"))
    print(f"{slug}: {n} SKILL.md file(s)")
    cmd_ingest(["--project", proj] + ([] if "--no-assets" in args else ["--with-assets"]) + [str(d)])
    if not any(k[0] == slug for k in known):
        with reg.open("a") as f: f.write(f"{slug} {proj}\n")
        print(f"remembered in remotes.txt — `bank fetch --update` refreshes all")


def cmd_sources(args):
    """sources -> print the directories ingest will scan"""
    for d in _sources(): print(d)
    print("(override with SKILLS_BANK_SOURCES=dir1:dir2 or pass dirs to `bank ingest`)")


def cmd_watch(args):
    """watch [--interval SECONDS] -> run ingest in a loop (default 300s)"""
    iv = int(args[args.index("--interval") + 1]) if "--interval" in args else 300
    print(f"watching {len(_sources())} source dir(s) every {iv}s — Ctrl-C to stop")
    while True:
        try:
            cmd_ingest([a for a in args if a not in ("--interval", str(iv))])
        except SystemExit:
            pass
        time.sleep(iv)


def cmd_dashboard(args):
    """dashboard [--no-open] -> build dashboard.html from all entries and open it"""
    try:
        from . import dashboard
    except ImportError:  # run as a plain script
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import dashboard
    out = dashboard.build(list(entries()), ROOT / "dashboard.html", ROOT)
    if "--quiet" not in args: print(f"built {out}")
    if "--no-open" not in args:
        import webbrowser; webbrowser.open(out.as_uri())


def _mod(name):
    try:
        import importlib; return importlib.import_module(f"skills_bank.{name}")
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import importlib; return importlib.import_module(name)


def _kv(args):
    out = {}
    for kv in args:
        if "=" not in kv or kv.startswith("--"): continue
        k, v = kv.split("=", 1)
        out[k] = Path(v[1:]).expanduser().read_text(encoding="utf-8") if v.startswith("@") else v
    return out


def cmd_run(args):
    """run <id> [k=v|k=@file ...] [--model M] -> render and send to Claude (ANTHROPIC_API_KEY)"""
    api = _mod("api"); b = api.Bank()
    model = args[args.index("--model") + 1] if "--model" in args else None
    try: print(b.run(args[0], model=model, **_kv(args[1:])))
    except Exception as ex: sys.exit(f"error: {ex}")


def cmd_eval(args):
    """eval <eval-id|all> [--run] -> list eval cases; with --run execute the target per case (JSON cases with inputs)"""
    api = _mod("api"); b = api.Bank()
    ids = [e["id"] for e in entries() if e.get("type") == "eval"] if args[0] == "all" else [args[0]]
    for eid in ids:
        r = b.evaluate(eid, run="--run" in args)
        print(f"== {eid} -> {r['target']}")
        for c in r.get("cases") or r.get("results") or []:
            print(f"  [{c.get('name','?')}] expected: {c.get('expected','')}")
            if "output" in c: print("     output:", c["output"][:400].replace("\n", " "))


def cmd_sync_tools(args):
    """sync-tools [--dry] [--only tool1,tool2] -> copy every skill to every tool dir that lacks it (as <dir>/<id>/SKILL.md)"""
    dry = "--dry" in args
    only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
    roots = [r for r in _sources() if r.name == "skills" and ".claude/plugins" not in str(r) and "/.system" not in str(r)]
    skills = [e for e in entries() if e.get("type") == "skill"]
    n = 0
    for r in roots:
        tool = r.parent.name.lstrip(".")
        if only and tool not in only: continue
        for e in skills:
            sid = e["id"][4:] if e["id"].startswith("ext-") else e["id"]
            dest = r / sid / "SKILL.md"
            if dest.exists() or any(str(r) in str(x) for x in [e.get("origin", "")]): continue
            n += 1
            print(f"[{'dry' if dry else 'copy'}] {sid:<40} -> {tool}")
            if not dry:
                dest.parent.mkdir(parents=True, exist_ok=True)
                desc = str(e.get("description") or e.get("name", sid)).replace("\n", " ")
                dest.write_text(f"---\nname: {sid}\ndescription: {desc}\n---\n{e['_body'].strip()}\n", encoding="utf-8")
    print(f"{n} skill copies {'would be' if dry else ''} written across {len(roots)} tool dirs")


def cmd_use(args):
    """use [query] -> interactive pick, copies the body (or rendered prompt) to the clipboard"""
    q = " ".join(args).lower()
    es = [e for e in entries() if not q or q in (e["id"] + e.get("name", "")).lower()]
    for i, e in enumerate(es, 1): print(f"{i:>3}. {e['id']:<40} {e.get('type','')}")
    try: pick = es[int(input("pick #: ")) - 1]
    except (ValueError, IndexError): sys.exit("cancelled")
    vals = {}
    for name in pick.get("inputs") or []:
        vals[name] = input(f"{name}: ")
    text = _mod("api").Bank().render(pick["id"], strict=False, **vals)
    try:
        import subprocess
        cmd = "pbcopy" if sys.platform == "darwin" else "xclip -selection clipboard"
        subprocess.run(cmd.split(), input=text.encode(), check=True); print("copied to clipboard")
    except Exception:
        print(text)


def cmd_mcp(args):
    """mcp -> run as an MCP stdio server (claude mcp add skills-bank -- bank mcp)"""
    _mod("mcp_server").serve()


def cmd_serve(args):
    """serve [--port 7777] -> local HTTP API: /entries /entry/<id> /render/<id>?k=v /search?q= /dashboard"""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs
    port = int(args[args.index("--port") + 1]) if "--port" in args else 7777
    api = _mod("api")
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
            self.send_header("content-type", "application/json; charset=utf-8"); self.send_header("access-control-allow-origin", "*"); self.end_headers(); self.wfile.write(body)
        def do_GET(self):
            u = urlparse(self.path); qs = {k: v[0] for k, v in parse_qs(u.query).items()}; b = api.Bank()
            slim = lambda e: {k: v for k, v in e.items() if k != "_body"}
            try:
                if u.path == "/entries": return self._json([slim(e) for e in b.entries()])
                if u.path == "/search": return self._json([slim(e) for e in b.search(qs.get("q", ""))])
                if u.path.startswith("/entry/"): e = b.get(u.path[7:]); return self._json({**slim(e), "body": e["_body"]})
                if u.path.startswith("/render/"): return self._json({"text": b.render(u.path[8:], strict=False, **qs)})
                if u.path in ("/", "/dashboard"):
                    cmd_dashboard(["--no-open"]); html = (ROOT / "dashboard.html").read_bytes()
                    self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(html); return
                self._json({"error": "not found"}, 404)
            except KeyError as ex: self._json({"error": f"no entry {ex}"}, 404)
    print(f"Skills Bank API on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


CMDS = {"list": cmd_list, "dashboard": cmd_dashboard, "run": cmd_run, "eval": cmd_eval, "sync-tools": cmd_sync_tools,
        "use": cmd_use, "mcp": cmd_mcp, "serve": cmd_serve, "discover": cmd_discover,
        "fetch": cmd_fetch, "ingest-agents": cmd_ingest_agents, "ingest-instructions": cmd_ingest_instructions, "inventory": cmd_inventory, "ingest-all": cmd_ingest_all, "ingest": cmd_ingest, "sources": cmd_sources, "watch": cmd_watch, "deps": cmd_deps, "export-skill": cmd_export_skill,
        "validate": cmd_validate, "prune": cmd_prune, "create-skill": cmd_create_skill, "unexport": cmd_unexport, "stats": cmd_stats, "search": cmd_search, "show": cmd_show,
        "render": cmd_render, "new": cmd_new, "index": cmd_index}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); print("commands:", ", ".join(CMDS)); print("bank root:", ROOT); sys.exit(1)
    CMDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
