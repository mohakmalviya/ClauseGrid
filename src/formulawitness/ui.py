"""Dependency-free local review interface for the FormulaWitness demo."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .advanced import run_advanced
from .benchmark import WORKBOOK_CASES
from .policy import extract_rules

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FormulaWitness</title>
<style>
:root{--navy:#10233f;--blue:#2867d3;--ink:#172033;--muted:#667085;--line:#d9e0ea;--paper:#fff;--bg:#f4f7fb;--ok:#137a45;--bad:#c23434;--amber:#a05a00}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,Segoe UI,Arial,sans-serif}
header{background:var(--navy);color:#fff;padding:22px 5vw;display:flex;align-items:center;justify-content:space-between}
.brand{font-size:22px;font-weight:750;letter-spacing:-.3px}.tag{font-size:12px;color:#cdd9ea;text-transform:uppercase;letter-spacing:.12em}
main{max-width:1220px;margin:28px auto;padding:0 22px 60px}.hero{display:grid;grid-template-columns:1.5fr 1fr;gap:20px;margin-bottom:18px}
.panel{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;box-shadow:0 8px 24px rgba(16,35,63,.05)}
h1{font-size:31px;margin:0 0 10px;letter-spacing:-.7px}h2{font-size:17px;margin:0 0 14px}p{color:var(--muted);line-height:1.55}
.metric{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric div{background:#edf3fc;border-radius:10px;padding:13px}.metric b{display:block;font-size:20px;color:var(--navy)}
label{display:block;font-size:12px;font-weight:700;color:#475467;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
select,input{width:100%;padding:11px 12px;border:1px solid #bbc7d7;border-radius:8px;background:#fff;color:var(--ink);font:inherit}
button{border:0;border-radius:8px;padding:11px 16px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer}button.secondary{background:#eef2f7;color:var(--navy)}button:disabled{opacity:.45;cursor:not-allowed}
.actions{display:flex;gap:9px;margin-top:14px}.steps{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:18px 0}.step{padding:10px;border-radius:8px;background:#e8edf4;color:#586578;font-size:12px;font-weight:700;text-align:center}.step.on{background:#dce9ff;color:#164da6}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.hidden{display:none}.status{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800}.PASS{background:#dcf5e7;color:var(--ok)}.FAIL{background:#fde7e7;color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#667085;border-bottom:1px solid var(--line);padding:8px}td{padding:8px;border-bottom:1px solid #edf0f4;vertical-align:top}
code{font-family:Consolas,monospace;font-size:11px;background:#f1f4f8;padding:2px 5px;border-radius:4px;word-break:break-all}.quote{border-left:3px solid var(--blue);padding:9px 12px;background:#f7f9fc;color:#39465a;font-size:12px;line-height:1.45;margin:8px 0}.patch{border:1px solid #c9d5e5;border-radius:10px;padding:13px;margin:10px 0}.before{color:var(--bad)}.after{color:var(--ok)}
.downloads a{display:inline-block;margin:5px 6px 0 0;padding:8px 10px;border:1px solid #b8c8df;border-radius:7px;text-decoration:none;color:#164da6;background:#f7faff;font-size:12px;font-weight:700}
#message{margin-top:12px;color:var(--muted);font-size:13px}.danger{color:var(--bad)!important}.approval{border:1px solid #efc986;background:#fff9ed}.small{font-size:11px;color:var(--muted)}
@media(max-width:850px){.hero,.grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr}.metric{grid-template-columns:1fr}}
</style></head>
<body><header><div class="brand">FormulaWitness</div><div class="tag">Policy-grounded spreadsheet assurance</div></header>
<main>
<section class="hero"><div class="panel"><h1>Make spreadsheet semantics reviewable.</h1><p>Turn written rebate policy into cited rules and discriminating witnesses, localize plausible-but-wrong formulas, and require approval before a repaired copy is written.</p><div class="metric"><div><b>48</b><span class="small">sealed vectors / workbook</span></div><div><b>1 cell</b><span class="small">default repair limit</span></div><div><b>0</b><span class="small">source files overwritten</span></div></div></div>
<div class="panel"><label for="case">Benchmark workbook</label><select id="case"></select><div class="actions"><button id="audit">Run witness audit</button><button class="secondary" id="reset">Reset</button></div><div id="message">Select a case. Mutant M10 is the flagship waiver-scope demo.</div></div></section>
<div class="steps"><div class="step on">1 · Case</div><div class="step" id="s2">2 · Cited rules</div><div class="step" id="s3">3 · Counterexamples</div><div class="step" id="s4">4 · Diagnose</div><div class="step" id="s5">5 · Approve & export</div></div>
<section id="results" class="hidden"><div class="grid"><div class="panel"><h2>Source-cited rules</h2><div id="rules"></div></div><div class="panel"><h2>Diagnosis</h2><div id="diagnosis"></div></div></div>
<div class="panel" style="margin-top:18px"><h2>Counterexample witnesses</h2><div style="overflow:auto"><table><thead><tr><th>Case</th><th>Rule</th><th>Status</th><th>Mismatch</th></tr></thead><tbody id="tests"></tbody></table></div></div>
<div class="panel approval" style="margin-top:18px"><h2>Human approval gate</h2><p>The approval is bound to the source hash, cited-rule bundle, visible case manifest, and exact patch diff.</p><div class="grid"><div><label for="reviewer">Reviewer identity</label><input id="reviewer" value="hackathon-reviewer"></div><div><label>Source SHA-256</label><code id="sourceHash"></code></div></div><div class="actions"><button id="approve">Approve minimal patch</button></div><div id="approvalMessage" class="small"></div><div id="downloads" class="downloads"></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id); let current=null;
function node(tag,text,cls){const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n}
async function api(path,options){const r=await fetch(path,options);const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j}
async function init(){const data=await api('/api/cases'); for(const c of data.cases){const o=node('option',`${c.id} — ${c.label}`);o.value=c.id;if(c.id==='M10')o.selected=true;$('case').append(o)}}
function setSteps(n){for(let i=2;i<=5;i++)$('s'+i).classList.toggle('on',i<=n)}
function render(data){current=data.result;$('results').classList.remove('hidden');$('sourceHash').textContent=current.source_sha256;setSteps(5);$('rules').replaceChildren();for(const r of data.rules){const d=node('div');d.append(node('b',`${r.rule_id} · ${r.title}`));d.append(node('div',`Page ${r.page}`, 'small'));d.append(node('div',r.quote,'quote'));$('rules').append(d)}
 $('diagnosis').replaceChildren(node('div',`Decision: ${current.decision}`,'status '+(current.decision==='REPAIR'?'FAIL':'PASS')));for(const p of current.patches){const d=node('div',null,'patch');d.append(node('b',`Patch ${p.cell} · ${p.rule_ids.join(', ')}`));d.append(node('div',p.old_formula,'before'));d.append(node('div',p.new_formula,'after'));d.append(node('p',p.rationale));$('diagnosis').append(d)}if(!current.patches.length)$('diagnosis').append(node('p','No core formula change is justified.'));
 $('tests').replaceChildren();for(const t of current.tests){const tr=document.createElement('tr');for(const value of [t.case_id,t.rule_ids.join(', '),t.status,t.mismatched_cells.join(', ')||'—']){tr.append(node('td',value,value===t.status?'status '+t.status:null))}$('tests').append(tr)} $('approve').disabled=current.decision!=='REPAIR';$('approvalMessage').textContent=current.decision==='REPAIR'?'Review the cited evidence and exact diff before approving.':'No repair approval is required.'}
$('audit').onclick=async()=>{try{$('audit').disabled=true;$('message').textContent='Extracting rules and executing counterexamples…';const d=await api('/api/audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:$('case').value})});render(d);$('message').textContent=`Audit ${d.result.run_id} complete.`}catch(e){$('message').textContent=e.message;$('message').className='danger'}finally{$('audit').disabled=false}};
$('approve').onclick=async()=>{try{$('approve').disabled=true;$('approvalMessage').textContent='Binding approval and writing repaired copy…';const d=await api('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:current.run_id,reviewer:$('reviewer').value})});current=d.result;$('approvalMessage').textContent=`Approved: ${current.approval_hash}`;$('downloads').replaceChildren();for(const f of d.downloads){const a=node('a',f);a.href=`/download/${encodeURIComponent(current.run_id)}/${encodeURIComponent(f)}`;$('downloads').append(a)}}catch(e){$('approvalMessage').textContent=e.message;$('approvalMessage').className='danger'}finally{$('approve').disabled=false}};
$('reset').onclick=()=>location.reload();init().catch(e=>$('message').textContent=e.message);
</script></body></html>"""


def _rule_payload(root: Path) -> list[dict[str, Any]]:
    rules = extract_rules(root / "policies/supplier_rebate_sla_policy.pdf")
    return [
        {
            "rule_id": rule.rule_id,
            "title": rule.title,
            "page": rule.evidence.page,
            "quote": rule.evidence.exact_quote,
        }
        for rule in rules
    ]


def make_handler(root: Path):
    sessions: dict[str, str] = {}
    artifact_root = root / "artifacts/ui"

    class Handler(BaseHTTPRequestHandler):
        server_version = "FormulaWitness/0.1"

        def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20_000:
                raise ValueError("Request too large")
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                data = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
                )
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path == "/api/cases":
                cases = [
                    {"id": case_id, "label": Path(relative).stem}
                    for case_id, relative in WORKBOOK_CASES.items()
                ]
                self._json({"cases": cases})
                return
            if parsed.path.startswith("/download/"):
                parts = [unquote(part) for part in parsed.path.split("/") if part]
                if len(parts) != 3 or parts[1] not in sessions:
                    self._json({"error": "Unknown artifact"}, HTTPStatus.NOT_FOUND)
                    return
                run_id, filename = parts[1], Path(parts[2]).name
                allowed = {
                    "repaired.xlsx",
                    "rules.yaml",
                    "formula-diff.json",
                    "evidence-graph.json",
                    "report.json",
                    "trajectory.jsonl",
                    "counterexamples.json",
                    "approval.json",
                }
                target = artifact_root / run_id / filename
                if filename not in allowed or not target.is_file():
                    self._json({"error": "Artifact not available"}, HTTPStatus.NOT_FOUND)
                    return
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type", mimetypes.guess_type(filename)[0] or "application/octet-stream"
                )
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            try:
                payload = self._body()
                if self.path == "/api/audit":
                    case_id = str(payload.get("case_id", ""))
                    if case_id not in WORKBOOK_CASES:
                        raise ValueError("Unknown benchmark case")
                    workbook = root / WORKBOOK_CASES[case_id]
                    result = run_advanced(
                        workbook, root / "policies/supplier_rebate_sla_policy.pdf", artifact_root
                    )
                    sessions[result.run_id] = case_id
                    self._json({"result": result.to_dict(), "rules": _rule_payload(root)})
                    return
                if self.path == "/api/approve":
                    run_id = str(payload.get("run_id", ""))
                    reviewer = str(payload.get("reviewer", "")).strip()
                    if run_id not in sessions or not reviewer:
                        raise ValueError("A known run and non-empty reviewer identity are required")
                    case_id = sessions[run_id]
                    workbook = root / WORKBOOK_CASES[case_id]
                    result = run_advanced(
                        workbook,
                        root / "policies/supplier_rebate_sla_policy.pdf",
                        artifact_root,
                        reviewer=reviewer,
                    )
                    downloads = sorted(
                        path.name
                        for path in (artifact_root / result.run_id).iterdir()
                        if path.is_file()
                    )
                    self._json({"result": result.to_dict(), "downloads": downloads})
                    return
                self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001 - HTTP boundary must fail closed
                self._json(
                    {"error": f"Audit failed closed: {type(exc).__name__}: {exc}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[ui] {self.address_string()} {format % args}")

    return Handler


def serve(root: Path, host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(root))
    print(f"FormulaWitness review UI: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
