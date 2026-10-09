"""Generate a self-contained HTML dashboard from the bank's entries (with derived analytics)."""
import json, re, time
from collections import Counter
from pathlib import Path

TOOL_RE = re.compile(r"/\.?([A-Za-z0-9_-]+)/(?:skills|plugins|harness)")


def tool_of(path):
    """~/.codex/skills/x -> codex ; ~/.config/goose/skills -> goose ; ~/.claude/plugins/foo/skills -> claude:foo"""
    p = str(path)
    m = re.search(r"/_remote/([^/]+)__([^/]+)/", p)
    if m: return f"github:{m.group(1)}/{m.group(2)}"
    m = re.search(r"/\.claude/plugins/(?:cache/)?([^/]+)/", p)
    if m: return "claude:" + m.group(1)
    if "/.claude/skills/synced/" in p: return "claude:synced"
    m = re.search(r"/\.config/([^/]+)/", p)
    if m: return m.group(1)
    m = re.search(r"/\.([A-Za-z0-9_-]+)/(?:skills|plugins|harness)", p)
    if m: return m.group(1)
    if "/.claude/skills" in p: return "claude"
    return "other"


def enrich(entries):
    ids = {e["id"] for e in entries}
    used_by = {}
    for e in entries:
        for u in (e.get("uses") or []) + ([e["target"]] if e.get("target") else []):
            used_by.setdefault(u, []).append(e["id"])
    evals_for = {e["target"]: e["id"] for e in entries if e.get("type") == "eval" and e.get("target")}
    out = []
    for e in entries:
        d = {k: v for k, v in e.items() if k != "_body"}
        body = e["_body"].strip()
        d["body"] = body
        d["chars"] = len(body)
        d["words"] = len(body.split())
        d["placeholders"] = sorted(set(re.findall(r"{{(\w+)}}", body)))
        d["used_by"] = sorted(used_by.get(e["id"], []))
        d["eval"] = evals_for.get(e["id"])
        d["external"] = "ingested" in (e.get("tags") or [])
        locs = []
        if e.get("origin"): locs.append(str(e["origin"]))
        # also_at may be repeated keys; our parser keeps last. Re-read file for all.
        try:
            raw = Path(e["_root"]).joinpath(e["_path"]).read_text(encoding="utf-8") if e.get("_root") else ""
            locs += re.findall(r"^also_at: (.+)$", raw, re.M)
        except OSError:
            pass
        d["locations"] = locs
        d["tools"] = sorted({tool_of(l) for l in locs})
        d["tool_count"] = len(d["tools"])
        probs = []
        for req in ("name", "type", "project"):
            if not e.get(req): probs.append(f"missing {req}")
        if not d["external"]:
            for ph in d["placeholders"]:
                if not ph.isupper() and ph not in (e.get("inputs") or []): probs.append(f"placeholder {ph} not in inputs")
        for u in (e.get("uses") or []):
            if u not in ids: probs.append(f"uses unknown {u}")
        if e.get("type") in ("prompt", "agent") and not d["eval"]: probs.append("no eval")
        if e.get("type") in ("prompt", "agent", "workflow", "skill") and not d["external"] and not d["used_by"] and e.get("type") != "skill" and e.get("type") != "workflow":
            probs.append("unused")
        if d["words"] < 15: probs.append("very short body")
        if not e.get("description") and d["external"]: probs.append("no description")
        d["problems"] = probs
        out.append(d)
    return out


def build(entries, out_path, root=None):
    for e in entries:
        e["_root"] = str(root) if root else None
    data = {"generated": time.strftime("%Y-%m-%d %H:%M"), "entries": enrich(entries)}
    # tool x project matrix and per-tool counts
    tc = Counter()
    for e in data["entries"]:
        for t in e["tools"]: tc[t] += 1
    data["tool_counts"] = dict(tc.most_common())
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out_path.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    return out_path


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Bank</title>
<style>
:root{--bg:#f6f5f1;--card:#fff;--ink:#1c1b18;--mute:#6b6861;--line:#e4e1d9;--acc:#0f5f8a;--warn:#b8552e;--ok:#2e7d4f;--chip:#eeece5;--sel:#e3eef5}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15161a;--card:#1e2026;--ink:#ecebe6;--mute:#9a9892;--line:#2c2f37;--acc:#6db3dc;--warn:#e58b63;--ok:#6cc08b;--chip:#2a2d35;--sel:#243240}}
:root[data-theme=dark]{--bg:#15161a;--card:#1e2026;--ink:#ecebe6;--mute:#9a9892;--line:#2c2f37;--acc:#6db3dc;--warn:#e58b63;--ok:#6cc08b;--chip:#2a2d35;--sel:#243240}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
header{padding:16px 16px 0;max-width:1400px;margin:0 auto;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between}
h1{margin:0;font-size:20px}h1 small{color:var(--mute);font-weight:400;font-size:12px;margin-left:8px}
nav{display:flex;gap:4px;flex-wrap:wrap}nav button{border:0;background:transparent;padding:8px 12px;border-radius:8px 8px 0 0;color:var(--mute);font:inherit;cursor:pointer}nav button.on{background:var(--card);color:var(--ink);border:1px solid var(--line);border-bottom-color:var(--card)}
main{max-width:1400px;margin:0 auto;padding:12px 16px 40px}.tab{display:none}.tab.on{display:block}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:8px 0 14px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;cursor:pointer}.tile:hover,.tile.on{border-color:var(--acc)}
.tile b{display:block;font-size:22px;font-weight:600}.tile span{color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}.card h3{margin:0 0 8px;font-size:13px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em}
.row{display:grid;grid-template-columns:140px 1fr 40px;gap:8px;align-items:center;font-size:13px;margin:3px 0;cursor:pointer}.row:hover{color:var(--acc)}
.meter{height:10px;background:var(--chip);border-radius:5px;overflow:hidden}.meter i{display:block;height:100%;background:var(--acc)}
.row .n{text-align:right;color:var(--mute);font-variant-numeric:tabular-nums}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center}
input,select,textarea{font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}input.q{flex:1;min-width:200px}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}.chip{background:var(--chip);border-radius:999px;padding:2px 9px;font-size:12px;cursor:pointer}.chip.on{background:var(--acc);color:#fff}
.layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}@media(max-width:900px){.layout{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}th{font-size:11px;color:var(--mute);text-transform:uppercase;letter-spacing:.06em;cursor:pointer;white-space:nowrap;user-select:none}
tr.r{cursor:pointer}tr.r:hover,tr.sel{background:var(--sel)}
.t{font-size:11px;padding:1px 7px;border-radius:5px;background:var(--chip);white-space:nowrap}.id{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.p{color:var(--warn)}.g{color:var(--ok)}.m{color:var(--mute)}
.detail{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;position:sticky;top:10px;max-height:calc(100vh - 20px);overflow:auto}
.detail h2{margin:0 0 2px;font-size:17px}.sub{display:flex;gap:4px;margin:10px 0;flex-wrap:wrap}.sub button{font:inherit;font-size:12px;border:1px solid var(--line);background:transparent;color:var(--mute);border-radius:6px;padding:4px 9px;cursor:pointer}.sub button.on{background:var(--chip);color:var(--ink)}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);padding:10px;border-radius:8px;font-size:12.5px;direction:auto;margin:0}
.kv div{margin:2px 0;font-size:13px}.kv b{color:var(--mute);font-weight:500;display:inline-block;min-width:110px}
.empty{color:var(--mute);padding:36px;text-align:center}.cnt{color:var(--mute);font-size:12px;margin:4px 0}
button.b{font:inherit;font-size:13px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer}button.b:hover{border-color:var(--acc)}
a.l{color:var(--acc);cursor:pointer;text-decoration:none}a.l:hover{text-decoration:underline}
.inp label{display:block;font-size:12px;color:var(--mute);margin:8px 0 2px}.inp textarea{width:100%;min-height:54px}
kbd{font:11px ui-monospace,Menlo,monospace;background:var(--chip);padding:1px 5px;border-radius:4px}
.matrix{overflow:auto}.matrix td,.matrix th{text-align:center;padding:4px 6px}.matrix td.y{background:color-mix(in srgb,var(--acc) 22%,transparent)}.matrix th:first-child,.matrix td:first-child{text-align:left}
.dep{margin:4px 0}.dep .k{color:var(--mute);font-size:12px}
</style></head><body>
<header><h1>AI Bank <small id="gen"></small></h1>
<nav><button data-tab="overview" class="on">Overview</button><button data-tab="entries">Entries</button><button data-tab="health">Health</button><button data-tab="tools">Tools</button></nav>
<div class="bar" style="margin:0"><button class="b" onclick="dl('json')">Export JSON</button><button class="b" onclick="dl('csv')">Export CSV</button><button class="b" onclick="theme()">◐</button></div></header>
<main>
<section class="tab on" id="overview">
 <div class="tiles" id="tiles"></div>
 <div class="grid2">
  <div class="card"><h3>By project</h3><div id="byproj"></div></div>
  <div class="card"><h3>By type</h3><div id="bytype"></div></div>
  <div class="card"><h3>Top tags</h3><div id="bytag"></div></div>
  <div class="card"><h3>Installed across tools</h3><div id="bytool"></div></div>
  <div class="card"><h3>Recently ingested</h3><div id="recent"></div></div>
  <div class="card"><h3>Largest entries</h3><div id="largest"></div></div>
 </div>
</section>
<section class="tab" id="entries">
 <div class="bar"><input class="q" id="q" placeholder="Search id, name, tags, description, body…  (press / )"><select id="proj"><option value="">All projects</option></select><select id="typ"><option value="">All types</option></select><select id="src"><option value="">Authored + external</option><option value="own">Authored only</option><option value="ext">External only</option></select><select id="flt"><option value="">No filter</option><option value="probs">Has problems</option><option value="noeval">Missing eval</option><option value="multi">In 2+ tools</option><option value="inputs">Has inputs</option></select></div>
 <div class="chips" id="tags"></div>
 <div class="cnt" id="cnt"></div>
 <div class="layout"><div><table><thead><tr><th data-k="id">ID</th><th data-k="type">Type</th><th data-k="project">Proj</th><th data-k="name">Name</th><th data-k="tool_count" title="installed in N tools">Tools</th><th data-k="words">Words</th><th data-k="version">v</th><th data-k="problems">!</th></tr></thead><tbody id="rows"></tbody></table></div>
 <div class="detail" id="detail"><div class="empty">Select an entry — <kbd>j</kbd>/<kbd>k</kbd> to move, <kbd>/</kbd> to search</div></div></div>
</section>
<section class="tab" id="health"><div id="healthbody"></div></section>
<section class="tab" id="tools"><div class="card matrix" id="matrix"></div></section>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);const E=D.entries;const byId=Object.fromEntries(E.map(e=>[e.id,e]));
document.getElementById('gen').textContent=E.length+' entries · generated '+D.generated;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const count=(k,arr=false)=>E.reduce((m,e)=>{(arr?(e[k]||[]):[e[k]||'?']).forEach(v=>m[v]=(m[v]||0)+1);return m},{});
let F={q:'',proj:'',typ:'',tag:'',src:'',flt:'',sort:'id',dir:1},sel=null,sub='body';
// ---- tabs
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.id===b.dataset.tab));try{localStorage.tab=b.dataset.tab}catch(e){}});
function goTab(t){document.querySelector(`nav button[data-tab=${t}]`).click()}
// ---- overview
function meters(el,obj,onclick,limit=12){const ents=Object.entries(obj).sort((a,b)=>b[1]-a[1]).slice(0,limit);const mx=Math.max(1,...ents.map(x=>x[1]));document.getElementById(el).innerHTML=ents.map(([k,v])=>`<div class="row" data-k="${esc(k)}"><span>${esc(k)}</span><div class="meter"><i style="width:${v/mx*100}%"></i></div><span class="n">${v}</span></div>`).join('')||'<div class="m">none</div>';document.getElementById(el).onclick=e=>{const r=e.target.closest('.row');if(r)onclick(r.dataset.k)}}
const types=count('type');
document.getElementById('tiles').innerHTML=[['',E.length,'total'],...Object.entries(types).sort((a,b)=>b[1]-a[1]).map(([k,v])=>[k,v,k+'s'])].map(([k,v,l])=>`<div class="tile" data-t="${k}"><b>${v}</b><span>${l}</span></div>`).join('')+`<div class="tile" data-h="1"><b class="p">${E.filter(e=>e.problems.length).length}</b><span>with issues</span></div><div class="tile" data-t="" data-src="ext"><b>${E.filter(e=>e.external).length}</b><span>external</span></div>`;
document.getElementById('tiles').onclick=e=>{const t=e.target.closest('.tile');if(!t)return;if(t.dataset.h){goTab('health');return}F.typ=t.dataset.t;F.src=t.dataset.src||'';syncSel();goTab('entries');render()};
meters('byproj',count('project'),k=>{F.proj=k;syncSel();goTab('entries');render()});
meters('bytype',types,k=>{F.typ=k;syncSel();goTab('entries');render()});
meters('bytag',count('tags',true),k=>{F.tag=k;goTab('entries');render()},15);
meters('bytool',D.tool_counts,k=>{F.q='';goTab('tools')},20);
const lst=(el,arr,fmt)=>document.getElementById(el).innerHTML=arr.map(e=>`<div class="dep"><a class="l" onclick="open_('${e.id}')">${esc(e.id)}</a> <span class="k">${fmt(e)}</span></div>`).join('')||'<div class="m">none</div>';
lst('recent',E.filter(e=>e.ingested).sort((a,b)=>(b.ingested>a.ingested?1:-1)).slice(0,8),e=>e.ingested+' · '+e.tool_count+' tool(s)');
lst('largest',[...E].sort((a,b)=>b.words-a.words).slice(0,8),e=>e.words+' words');
// ---- entries
const fill=(id,obj)=>{const s=document.getElementById(id);Object.keys(obj).sort().forEach(k=>s.insertAdjacentHTML('beforeend',`<option>${esc(k)}</option>`))};fill('proj',count('project'));fill('typ',types);
const tagc=count('tags',true);document.getElementById('tags').innerHTML=Object.entries(tagc).sort((a,b)=>b[1]-a[1]).slice(0,36).map(([t,n])=>`<span class="chip" data-tag="${esc(t)}">${esc(t)} ${n}</span>`).join('');
document.getElementById('tags').onclick=e=>{const c=e.target.closest('.chip');if(!c)return;F.tag=F.tag===c.dataset.tag?'':c.dataset.tag;render()};
['q','proj','typ','src','flt'].forEach(id=>document.getElementById(id).oninput=e=>{F[id]=e.target.value;render()});
function syncSel(){['proj','typ','src','flt','q'].forEach(id=>document.getElementById(id).value=F[id])}
document.querySelectorAll('#entries th').forEach(th=>th.onclick=()=>{if(F.sort===th.dataset.k)F.dir*=-1;else{F.sort=th.dataset.k;F.dir=th.dataset.k==='words'||th.dataset.k==='tool_count'?-1:1}render()});
function list(){const q=F.q.toLowerCase();return E.filter(e=>(!F.proj||e.project===F.proj)&&(!F.typ||e.type===F.typ)&&(!F.tag||(e.tags||[]).includes(F.tag))&&(F.src!=='own'||!e.external)&&(F.src!=='ext'||e.external)&&(F.flt!=='probs'||e.problems.length)&&(F.flt!=='noeval'||(['prompt','agent'].includes(e.type)&&!e.eval))&&(F.flt!=='multi'||e.tool_count>=2)&&(F.flt!=='inputs'||(e.inputs||[]).length)&&(!q||(e.id+' '+e.name+' '+(e.tags||[]).join(' ')+' '+(e.description||'')+' '+e.body).toLowerCase().includes(q))).sort((a,b)=>{let x=a[F.sort]??'',y=b[F.sort]??'';if(Array.isArray(x)){x=x.length;y=y.length}return (x>y?1:x<y?-1:0)*F.dir})}
let cur=[];
function render(){cur=list();document.querySelectorAll('.tile').forEach(t=>t.classList.toggle('on',t.dataset.t===F.typ&&!t.dataset.h&&(t.dataset.src||'')===F.src));document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c.dataset.tag===F.tag));
document.getElementById('cnt').textContent=cur.length+' shown · '+cur.reduce((s,e)=>s+e.words,0).toLocaleString()+' words';
document.getElementById('rows').innerHTML=cur.map(e=>`<tr class="r ${sel===e.id?'sel':''}" data-id="${e.id}"><td class="id">${esc(e.id)}</td><td><span class="t">${e.type}</span></td><td>${esc(e.project)}</td><td>${esc(e.name)}</td><td>${e.tool_count||''}</td><td class="m">${e.words}</td><td class="m">${e.version||''}</td><td>${e.problems.length?`<span class="p" title="${esc(e.problems.join('; '))}">${e.problems.length}</span>`:'<span class="g">✓</span>'}</td></tr>`).join('')||'<tr><td colspan=8 class="empty">Nothing matches</td></tr>'}
document.getElementById('rows').onclick=e=>{const r=e.target.closest('tr.r');if(r)open_(r.dataset.id)};
function open_(id){sel=id;goTab('entries');show(byId[id]);render();const r=document.querySelector('tr.sel');if(r)r.scrollIntoView({block:'nearest'})}
const SKIP=new Set(['id','name','body','_path','_root','problems','locations','tools','used_by','eval','placeholders','chars','words','external','tool_count']);
function show(e){const d=document.getElementById('detail');const tabs=['body','meta','deps','where','render','export'];
d.innerHTML=`<h2>${esc(e.name)}</h2><div class="id m">${esc(e.id)} · ${esc(e._path)}${e.external?' · <span class="t">external</span>':''}</div>
<div class="sub">${tabs.map(t=>`<button data-s="${t}" class="${sub===t?'on':''}">${{body:'Body',meta:'Metadata',deps:'Dependencies',where:'Locations ('+e.locations.length+')',render:'Render',export:'Export'}[t]}</button>`).join('')}</div><div id="subbody"></div>`;
d.querySelectorAll('.sub button').forEach(b=>b.onclick=()=>{sub=b.dataset.s;show(e)});
const sb=d.querySelector('#subbody');
if(sub==='body')sb.innerHTML=`${e.problems.length?`<div class="p" style="margin-bottom:8px">⚠ ${esc(e.problems.join(' · '))}</div>`:''}<pre>${esc(e.body)}</pre>`;
if(sub==='meta')sb.innerHTML=`<div class="kv">${Object.entries(e).filter(([k,v])=>!SKIP.has(k)&&v!==''&&v!=null).map(([k,v])=>`<div><b>${esc(k)}</b> ${esc(Array.isArray(v)?v.join(', '):v)}</div>`).join('')}<div><b>words / chars</b> ${e.words} / ${e.chars}</div><div><b>placeholders</b> ${e.placeholders.join(', ')||'—'}</div><div><b>eval</b> ${e.eval?`<a class="l" onclick="open_('${e.eval}')">${e.eval}</a>`:'<span class="p">none</span>'}</div></div>`;
if(sub==='deps'){const link=x=>byId[x]?`<a class="l" onclick="open_('${x}')">${esc(x)}</a> <span class="k">(${byId[x].type})</span>`:`<span class="p">${esc(x)} (missing)</span>`;
 const tree=(id,depth,seen)=>{if(seen.has(id)||depth>5)return'';seen.add(id);const x=byId[id];if(!x)return'';const kids=[...(x.uses||[]),...(x.target?[x.target]:[])];return kids.map(k=>`<div class="dep" style="margin-left:${depth*16}px">↳ ${link(k)}</div>`+tree(k,depth+1,seen)).join('')};
 sb.innerHTML=`<div class="dep"><b>Uses</b></div>${tree(e.id,1,new Set())||'<div class="m dep">nothing</div>'}<div class="dep" style="margin-top:10px"><b>Used by</b></div>${e.used_by.map(u=>`<div class="dep">↰ ${link(u)}</div>`).join('')||'<div class="m dep">nothing</div>'}`}
if(sub==='where')sb.innerHTML=e.locations.length?`<div class="kv">${e.tools.map(t=>`<div><b>${esc(t)}</b></div>`).join('')}</div><pre style="margin-top:8px">${esc(e.locations.join('\n'))}</pre>`:'<div class="m">Authored in the bank — not ingested from elsewhere.</div>';
if(sub==='render'){const ins=e.inputs||[];sb.innerHTML=ins.length||e.placeholders.length?`<div class="inp">${(ins.length?ins:e.placeholders).map(i=>`<label>${esc(i)}</label><textarea data-i="${esc(i)}"></textarea>`).join('')}</div><div class="bar" style="margin-top:10px"><button class="b" id="doRender">Render</button><button class="b" id="cpOut">Copy output</button><button class="b" id="cpCmd">Copy CLI command</button></div><pre id="out" style="margin-top:8px">${esc(e.body)}</pre>`:'<div class="m">No inputs — nothing to fill.</div><div class="bar" style="margin-top:10px"><button class="b" id="cpOut">Copy body</button></div>';
 const outEl=sb.querySelector('#out');const vals=()=>Object.fromEntries([...sb.querySelectorAll('textarea')].map(t=>[t.dataset.i,t.value]));
 const doR=()=>{let o=e.body;for(const [k,v] of Object.entries(vals()))if(v)o=o.split('{{'+k+'}}').join(v);if(outEl)outEl.textContent=o;return o};
 sb.querySelector('#doRender')&&(sb.querySelector('#doRender').onclick=doR);sb.querySelectorAll('textarea').forEach(t=>t.oninput=doR);
 sb.querySelector('#cpOut').onclick=()=>navigator.clipboard.writeText(outEl?doR():e.body);
 sb.querySelector('#cpCmd')&&(sb.querySelector('#cpCmd').onclick=()=>navigator.clipboard.writeText(`bank render ${e.id} `+ins.map(i=>`${i}=@${i}.txt`).join(' ')))}
if(sub==='export'){const ins=e.inputs||[];const pub=e.id.replace(/^ext-/,'');const body=(ins.length&&e.type!=='skill')?`## Inputs to collect first\nAsk the user for any of these not already given (one short question, all at once):\n${ins.map(i=>'- **'+i+'**').join('\n')}\n\n## Then follow this template, substituting the inputs for the {{placeholders}}\n\n${e.body}${e.model?'\n\n_Preferred model: '+e.model+'_':''}`:e.body;const skill=`---\nname: ${pub}\ndescription: "${(e.description||e.name)+((e.triggers||[]).length?'. Use when the user says: '+e.triggers.join(', '):'')}"\n---\n${body}\n`;sb.innerHTML=`<div class="bar"><button class="b" id="cpSkill">Copy as SKILL.md</button><button class="b" id="cpJson">Copy JSON</button><button class="b" id="cpPath">Copy path</button></div><pre style="margin-top:8px">${esc(skill)}</pre>`;
 sb.querySelector('#cpSkill').onclick=()=>navigator.clipboard.writeText(skill);sb.querySelector('#cpJson').onclick=()=>navigator.clipboard.writeText(JSON.stringify(e,null,2));sb.querySelector('#cpPath').onclick=()=>navigator.clipboard.writeText(e._path)}}
// ---- health
(function(){const groups={};E.forEach(e=>e.problems.forEach(p=>{const k=p.replace(/ \S+$/,m=>p.startsWith('uses unknown')||p.startsWith('placeholder')?'…':m);(groups[k]=groups[k]||[]).push(e)}));
 const variants={};E.filter(e=>/-[0-9a-f]{6}$/.test(e.id)).forEach(e=>{const b=e.id.replace(/-[0-9a-f]{6}$/,'');(variants[b]=variants[b]||[]).push(e.id)});
 const pct=(n)=>Math.round(n/Math.max(1,E.length)*100);
 const evalable=E.filter(e=>['prompt','agent'].includes(e.type));const covered=evalable.filter(e=>e.eval).length;
 document.getElementById('healthbody').innerHTML=`<div class="tiles"><div class="tile"><b class="${E.filter(e=>e.problems.length)?'p':'g'}">${E.filter(e=>e.problems.length).length}</b><span>entries with issues</span></div><div class="tile"><b>${covered}/${evalable.length}</b><span>prompts+agents with evals</span></div><div class="tile"><b>${Object.keys(variants).length}</b><span>name conflicts</span></div><div class="tile"><b>${E.filter(e=>e.external).length}</b><span>external (${pct(E.filter(e=>e.external).length)}%)</span></div><div class="tile"><b>${E.filter(e=>!e.external).length}</b><span>authored</span></div></div>
 <div class="grid2">${Object.entries(groups).sort((a,b)=>b[1].length-a[1].length).map(([k,arr])=>`<div class="card"><h3>${esc(k)} <span class="m">(${arr.length})</span></h3>${arr.slice(0,40).map(e=>`<div class="dep"><a class="l" onclick="open_('${e.id}')">${esc(e.id)}</a> <span class="k">${e.type} · ${esc(e.project)}</span></div>`).join('')}${arr.length>40?`<div class="m">…and ${arr.length-40} more</div>`:''}</div>`).join('')}
 <div class="card"><h3>Same name, different content (variants)</h3>${Object.entries(variants).map(([b,ids])=>`<div class="dep"><a class="l" onclick="open_('${b}')">${esc(b)}</a> ↔ ${ids.map(i=>`<a class="l" onclick="open_('${i}')">${esc(i)}</a>`).join(', ')}<div class="k">Decide which is canonical; delete the other file in skills/.</div></div>`).join('')||'<div class="m">none</div>'}</div></div>`})();
// ---- tools matrix
(function(){const tools=Object.keys(D.tool_counts);const ext=E.filter(e=>e.tool_count);if(!tools.length){document.getElementById('matrix').innerHTML='<div class="m">No external skills ingested yet.</div>';return}
 const rows=[...ext].sort((a,b)=>b.tool_count-a.tool_count||a.id.localeCompare(b.id));
 document.getElementById('matrix').innerHTML=`<h3>Skill × tool — where each skill is installed (${tools.length} tools, ${ext.length} skills). Click a cell's row to open.</h3><table><thead><tr><th>skill</th><th>#</th>${tools.map(t=>`<th title="${esc(t)}">${esc(t.length>10?t.slice(0,9)+'…':t)}</th>`).join('')}</tr></thead><tbody>${rows.map(e=>`<tr class="r" data-id="${e.id}"><td class="id">${esc(e.id.replace(/^ext-/,''))}</td><td>${e.tool_count}</td>${tools.map(t=>`<td class="${e.tools.includes(t)?'y':''}">${e.tools.includes(t)?'●':''}</td>`).join('')}</tr>`).join('')}<tr><td><b>total</b></td><td>${ext.length}</td>${tools.map(t=>`<td><b>${D.tool_counts[t]}</b></td>`).join('')}</tr></tbody></table>`;
 document.getElementById('matrix').onclick=e=>{const r=e.target.closest('tr.r');if(r)open_(r.dataset.id)}})();
// ---- export / theme / keys
function dl(kind){let blob,name;if(kind==='json'){blob=new Blob([JSON.stringify(E,null,2)],{type:'application/json'});name='ai-bank.json'}else{const cols=['id','type','project','name','version','tool_count','words','external','tags','problems'];const csv=[cols.join(',')].concat(E.map(e=>cols.map(c=>{let v=e[c];if(Array.isArray(v))v=v.join('; ');return '"'+String(v??'').replace(/"/g,'""')+'"'}).join(','))).join('\n');blob=new Blob([csv],{type:'text/csv'});name='ai-bank.csv'}const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click()}
function theme(){const r=document.documentElement;const cur=r.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');r.dataset.theme=cur==='dark'?'light':'dark';try{localStorage.theme=r.dataset.theme}catch(e){}}
try{if(localStorage.theme)document.documentElement.dataset.theme=localStorage.theme;if(localStorage.tab)goTab(localStorage.tab)}catch(e){}
document.addEventListener('keydown',ev=>{if(ev.target.matches('input,textarea,select')){if(ev.key==='Escape')ev.target.blur();return}if(ev.key==='/'){ev.preventDefault();goTab('entries');document.getElementById('q').focus()}if(ev.key==='j'||ev.key==='k'){const i=cur.findIndex(e=>e.id===sel);const n=cur[Math.min(cur.length-1,Math.max(0,i+(ev.key==='j'?1:-1)))];if(n)open_(n.id)}});
render();
</script></body></html>
"""
