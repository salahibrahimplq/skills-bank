"""Python SDK: from ai_bank import Bank
b = Bank()                                   # finds ~/.ai-bank or AI_BANK_HOME
b.get("jobeng-cv-screen")                    # dict with metadata + body
b.render("jobeng-cv-screen", job_description="...", cv_text="...")
b.run("jobeng-cv-screen", job_description="...", cv_text="...")   # calls Claude (ANTHROPIC_API_KEY)
b.search("tender"); b.list(project="jobeng", type="prompt")
"""
import json, os, re, urllib.error, urllib.request
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"


class Bank:
    def __init__(self, root=None):
        from . import cli  # reuse the parser and root discovery
        self._cli = cli
        self.root = Path(root) if root else cli.ROOT
        if root:
            cli.ROOT = self.root

    # ---- read
    def entries(self):
        return list(self._cli.entries())

    def list(self, **f):
        return [e for e in self.entries() if all(e.get(k) == v for k, v in f.items())]

    def get(self, eid):
        for e in self.entries():
            if e["id"] == eid:
                return e
        raise KeyError(eid)

    def search(self, q):
        q = q.lower()
        return [e for e in self.entries()
                if q in (json.dumps({k: v for k, v in e.items() if not k.startswith("_")}) + e["_body"]).lower()]

    # ---- render / run
    def render(self, eid, strict=True, **inputs):
        e = self.get(eid)
        out = e["_body"]
        for k, v in inputs.items():
            out = out.replace("{{" + k + "}}", str(v))
        missing = [m for m in set(re.findall(r"{{(\w+)}}", out)) if not m.isupper()]
        if missing and strict:
            raise ValueError(f"missing inputs: {sorted(missing)}")
        return out.strip()

    def run(self, eid, model=None, max_tokens=2048, system=None, **inputs):
        """Render then call Claude. Returns text. Needs ANTHROPIC_API_KEY."""
        e = self.get(eid)
        prompt = self.render(eid, **inputs)
        model = model or e.get("model") or DEFAULT_MODEL
        if e.get("type") == "agent" and system is None:
            # agent entries: body is the system prompt; user turn is the inputs
            system, prompt = prompt, json.dumps(inputs, ensure_ascii=False) or "Begin."
        return messages(prompt, model=model, max_tokens=max_tokens, system=system)

    def evaluate(self, eval_id, run=False, **kw):
        """Return the eval cases for an eval entry; with run=True, execute target with each case's inputs."""
        ev = self.get(eval_id)
        target = ev.get("target")
        cases = parse_cases(ev["_body"])
        if not run:
            return {"target": target, "cases": cases}
        results = []
        for c in cases:
            inputs = c.get("inputs") or {}
            try:
                out = self.run(target, **inputs, **kw)
            except Exception as ex:
                out = f"ERROR: {ex}"
            results.append({**c, "output": out})
        return {"target": target, "results": results}


def parse_cases(body):
    """Cases from a markdown table (# | case | expected) or a ```json block [{name, inputs, expected}]."""
    m = re.search(r"```json\s*(\[.*?\])\s*```", body, re.S)
    if m:
        return json.loads(m.group(1))
    cases = []
    for line in body.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0].isdigit():
            cases.append({"name": cells[1], "expected": cells[2]})
    return cases


def _claude_cli(prompt, model=None, system=None):
    """Use the logged-in `claude` CLI (Claude Code subscription) — no API key needed."""
    import shutil, subprocess
    exe = shutil.which("claude")
    if not exe:
        return None
    cmd = [exe, "-p", "--output-format", "text"]
    if model: cmd += ["--model", model]
    if system: cmd += ["--system-prompt", system]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise RuntimeError("claude CLI failed: " + (r.stderr or r.stdout).strip()[:400])
    return r.stdout.strip()


def messages(prompt, model=DEFAULT_MODEL, max_tokens=2048, system=None):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or key.endswith("..."):
        out = _claude_cli(prompt, model=model, system=system)
        if out is not None:
            return out
        raise RuntimeError("No ANTHROPIC_API_KEY and no `claude` CLI found. Set a real key (export ANTHROPIC_API_KEY=sk-ant-…) or install Claude Code.")
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode("utf-8", "replace")[:300]
        hint = {401: "invalid API key — check ANTHROPIC_API_KEY (or unset it to use the `claude` CLI instead)",
                404: f"model '{model}' not found — pass --model", 429: "rate limited — retry shortly"}.get(ex.code, "")
        raise RuntimeError(f"Claude API {ex.code}: {hint or detail}") from None
    return "".join(b.get("text", "") for b in data.get("content", []))
