"""Dependency-free local review interface for the FormulaWitness demo."""

from __future__ import annotations

import hmac
import json
import mimetypes
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse, urlsplit

from .agent_loop import ChatModel
from .agentic import approve_agentic_proposal, run_agentic
from .models import AuditResult
from .public_benchmark import WORKBOOK_CASES
from .trace import object_hash

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
.panel{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;box-shadow:0 8px 24px rgba(16,35,63,.05)}
h1{font-size:31px;margin:0 0 10px;letter-spacing:-.7px}h2{font-size:17px;margin:0 0 14px}p{color:var(--muted);line-height:1.55}
.metric{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric div{background:#edf3fc;border-radius:10px;padding:13px}.metric b{display:block;font-size:20px;color:var(--navy)}
label{display:block;font-size:12px;font-weight:700;color:#475467;margin-bottom:6px;text-transform:uppercase;letter-spacing:.05em}
select,input{width:100%;padding:11px 12px;border:1px solid #bbc7d7;border-radius:8px;background:#fff;color:var(--ink);font:inherit}
button{border:0;border-radius:8px;padding:11px 16px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer}button.secondary{background:#eef2f7;color:var(--navy)}button:disabled{opacity:.45;cursor:not-allowed}
.actions{display:flex;gap:9px;margin-top:14px}.steps{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:18px 0}.step{padding:10px;border-radius:8px;background:#e8edf4;color:#586578;font-size:12px;font-weight:700;text-align:center}.step.on{background:#dce9ff;color:#164da6}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.hidden{display:none}.status{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:800}.PASS,.EXACT,.NO_CHANGE,.SURVIVED{background:#dcf5e7;color:var(--ok)}.FAIL,.REPAIR,.AMBIGUOUS,.CONFLICT,.BROKEN{background:#fde7e7;color:var(--bad)}.ABSTAIN,.INCONCLUSIVE{background:#fff0cf;color:var(--amber)}
table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;color:#667085;border-bottom:1px solid var(--line);padding:8px}td{padding:8px;border-bottom:1px solid #edf0f4;vertical-align:top}
code{font-family:Consolas,monospace;font-size:11px;background:#f1f4f8;padding:2px 5px;border-radius:4px;word-break:break-all}.quote{border-left:3px solid var(--blue);padding:9px 12px;background:#f7f9fc;color:#39465a;font-size:12px;line-height:1.45;margin:8px 0}.patch{min-width:0;border:1px solid #c9d5e5;border-radius:10px;padding:13px;margin:10px 0}.before,.after{font-family:Consolas,monospace;font-size:11px;overflow-wrap:anywhere;word-break:break-word}.before{color:var(--bad)}.after{color:var(--ok)}
.downloads a{display:inline-block;margin:5px 6px 0 0;padding:8px 10px;border:1px solid #b8c8df;border-radius:7px;text-decoration:none;color:#164da6;background:#f7faff;font-size:12px;font-weight:700}
#message{margin-top:12px;color:var(--muted);font-size:13px}.danger{color:var(--bad)!important}.approval{border:1px solid #efc986;background:#fff9ed}.small{font-size:11px;color:var(--muted)}
.evidence{margin-bottom:18px}.evidence-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.evidence-head p{margin:4px 0 12px}.benchmark-badge{white-space:nowrap;background:#edf3fc;color:var(--navy);border-radius:999px;padding:7px 10px;font-size:11px;font-weight:800}.score-table td:nth-child(n+2),.score-table th:nth-child(n+2){text-align:right}.score-table td.best{font-weight:800;color:var(--ok)}.disclosure{margin-top:12px;padding:10px 12px;border-left:3px solid #7c8ba1;background:#f7f9fc;color:#475467;font-size:12px;line-height:1.5}
@media(max-width:850px){.hero,.grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr}.metric{grid-template-columns:1fr}}
</style></head>
<body><header><div class="brand">FormulaWitness</div><div class="tag">Model-directed spreadsheet assurance</div></header>
<main>
<section class="hero"><div class="panel"><h1>Watch one agent propose—and another try to break it.</h1><p>The audit manager discovers workbook and policy semantics through bounded tools. A fresh-context falsifier challenges every staged repair before a local reviewer can approve a copied workbook.</p><div class="metric"><div><b>2 agents</b><span class="small">manager + falsifier</span></div><div><b>typed tools</b><span class="small">no shell or apply tool</span></div><div><b>0</b><span class="small">automatic source writes</span></div></div></div>
<div class="panel"><label>Server-side runtime</label><div><code id="runtime">Loading configuration…</code></div><label for="case" style="margin-top:16px">Synthetic benchmark workbook</label><select id="case"></select><div class="actions"><button id="audit">Run agent audit</button><button class="secondary" id="reset">Reset</button></div><div id="message">Mutant M10 is the flagship waiver-scope demonstration. A run can take several minutes.</div></div></section>
<section class="panel evidence"><div class="evidence-head"><div><h2>Legacy deterministic regression evidence</h2><p>This frozen scorecard validates the deterministic workbook layer. It is not model-agent performance.</p></div><div class="benchmark-badge" id="benchmarkBadge">Loading benchmark…</div></div><div style="overflow:auto"><table class="score-table"><thead><tr><th>Metric</th><th>Legacy baseline</th><th>Legacy advanced</th><th>Change</th></tr></thead><tbody id="scorecard"></tbody></table></div><div class="disclosure" id="measurementDisclosure"></div></section>
<div class="steps"><div class="step on">1 · Case</div><div class="step" id="s2">2 · Evidence</div><div class="step" id="s3">3 · Experiments</div><div class="step" id="s4">4 · Falsification</div><div class="step" id="s5">5 · Review & approve</div></div>
<section id="results" class="hidden"><div class="grid"><div class="panel"><h2>Mechanically registered policy citations</h2><div id="citations"></div></div><div class="panel"><h2>Agent decision and exact proposal</h2><div id="diagnosis"></div></div></div>
<div class="panel" style="margin-top:18px"><h2>Reproducible sandbox experiments</h2><div style="overflow:auto"><table><thead><tr><th>ID</th><th>Actor</th><th>Purpose</th><th>Observed result</th></tr></thead><tbody id="experiments"></tbody></table></div></div>
<div class="panel" style="margin-top:18px"><h2>Independent falsifier verdict</h2><div id="falsifier"></div></div>
<div class="panel approval" style="margin-top:18px"><h2>Local human approval gate</h2><p>Review the exact proposal, citations, experiments, falsifier verdict, and proposal hash. The model cannot invoke this gate.</p><div class="grid"><div><label for="reviewer">Reviewer label</label><input id="reviewer" value="hackathon-reviewer"></div><div><label>Source SHA-256</label><code id="sourceHash"></code><label style="margin-top:12px">Proposal hash</label><code id="proposalHash"></code></div></div><div class="actions"><button id="approve">Approve exact proposal</button></div><div id="approvalMessage" class="small"></div><div id="downloads" class="downloads"></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id); let current=null; let runtimeConfig=null;
function node(tag,text,cls){const n=document.createElement(tag);n.textContent=text??'';if(cls)n.className=cls;return n}
async function api(path,options){const r=await fetch(path,options);const j=await r.json();if(!r.ok)throw new Error(j.error||r.statusText);return j}
function pct(value){return `${Number(value).toFixed(1)}%`}function seconds(value){return `${Number(value).toFixed(3)} s`}
function renderSummary(s){$('benchmarkBadge').textContent=`${s.benchmark} · ${s.workbook_count} workbooks × ${s.hidden_cases_per_workbook} sealed cases`;$('scorecard').replaceChildren();const rows=[['Primary outcome: E2E-SRR',pct(s.baseline_e2e_srr),pct(s.advanced_e2e_srr),`+${Number(s.improvement_pp).toFixed(1)} pp`],['Clean preservation',pct(s.baseline_clean_preservation),pct(s.advanced_clean_preservation),'no regression'],['Challenging case H01',pct(s.baseline_hard_rate),pct(s.advanced_hard_rate),`+${Number(s.advanced_hard_rate-s.baseline_hard_rate).toFixed(1)} pp`],['Automated wall-clock, M10 median',seconds(s.baseline_runtime_seconds),seconds(s.advanced_runtime_seconds),`+${seconds(s.advanced_runtime_seconds-s.baseline_runtime_seconds)}`],['Human time per task','Not measured','Not measured','No claim'],['Model/API cost per task','$0.00 legacy','$0.00 legacy','Model cost not reported']];for(const values of rows){const tr=document.createElement('tr');for(const value of values)tr.append(node('td',value));$('scorecard').append(tr)}$('measurementDisclosure').textContent='The model-agent manager/falsifier is intentionally reported separately and has not inherited these scores. Every run below exposes its own provider, model, usage, evidence, and outcome.'}
async function init(){const [data,summary,config]=await Promise.all([api('/api/cases'),api('/api/summary'),api('/api/config')]);runtimeConfig=config;for(const c of data.cases){const o=node('option',`${c.id} — ${c.label}`);o.value=c.id;if(c.id==='M10')o.selected=true;$('case').append(o)}$('runtime').textContent=`${config.provider} · ${config.model}`;if(config.public_demo)$('message').textContent='Public live audits are queued, globally rate-limited, and use synthetic workbooks only.';renderSummary(summary)}
async function waitForJob(url){for(let attempt=0;attempt<1050;attempt++){const job=await api(url);if(job.status==='complete')return job.result;if(job.status==='failed')throw new Error(job.error||'Audit failed closed');$('message').textContent=`Agent audit ${job.status}…`;await new Promise(resolve=>setTimeout(resolve,2000))}throw new Error('Audit did not finish within thirty-five minutes')}
function setSteps(n){for(let i=2;i<=5;i++)$('s'+i).classList.toggle('on',i<=n)}
function renderDownloads(files){$('downloads').replaceChildren();for(const f of files||[]){const a=node('a',f);a.href=`/download/${encodeURIComponent(current.result.run_id)}/${encodeURIComponent(f)}`;$('downloads').append(a)}}
function observedSummary(item){const observation=item.observation||{};const applied=(observation.applied_formula_overrides||[]).join(', ')||'source formula';const values=JSON.stringify(observation.observations||{});return `${applied} → ${values}`}
function render(data){current=data;const result=data.result;const state=data.state||{};$('results').classList.remove('hidden');$('sourceHash').textContent=result.source_sha256;$('proposalHash').textContent=data.proposal_hash;setSteps(5);
 $('citations').replaceChildren();for(const c of data.citations||[]){const d=node('div');d.append(node('b',c.citation_id));d.append(node('div',`Page ${c.page} · characters ${c.start_char}–${c.end_char}`,'small'));d.append(node('div',c.exact_quote,'quote'));$('citations').append(d)}if(!(data.citations||[]).length)$('citations').append(node('p','No citation was registered before the agent abstained.'));
 $('diagnosis').replaceChildren(node('div',`Decision: ${result.decision}`,'status '+result.decision),node('div',`${data.provider} · ${data.model}`,'small'));if(state.decision?.explanation)$('diagnosis').append(node('p',state.decision.explanation));for(const p of result.patches||[]){const d=node('div',null,'patch');d.append(node('b',`Patch ${p.cell} · ${(p.rule_ids||[]).join(', ')}`));d.append(node('div',p.old_formula,'before'));d.append(node('div',p.new_formula,'after'));d.append(node('p',p.rationale));$('diagnosis').append(d)}if(!(result.patches||[]).length)$('diagnosis').append(node('p','No workbook patch has been authorized.'));
 $('experiments').replaceChildren();for(const t of data.experiments||[]){const tr=document.createElement('tr');for(const value of [t.experiment_id,t.actor,t.request?.purpose||'—',observedSummary(t)])tr.append(node('td',value));$('experiments').append(tr)}if(!(data.experiments||[]).length){const tr=document.createElement('tr');const td=node('td','No sandbox experiment completed.');td.colSpan=4;tr.append(td);$('experiments').append(tr)}
 $('falsifier').replaceChildren();const v=data.falsifier_verdict;if(v){$('falsifier').append(node('span',v.status,'status '+v.status),node('p',v.explanation));if(v.counterexamples?.length)$('falsifier').append(node('div',`Counterexamples: ${v.counterexamples.join('; ')}`,'danger'));if(v.remaining_risks?.length)$('falsifier').append(node('div',`Remaining risks: ${v.remaining_risks.join('; ')}`,'small'))}else $('falsifier').append(node('p','No falsifier verdict was produced.'));
 const approved=Boolean(result.approval_hash);const survived=v?.status==='SURVIVED';const browserApproval=runtimeConfig?.browser_approval_enabled===true;$('approve').disabled=!browserApproval||result.decision!=='REPAIR'||!survived||approved;$('approvalMessage').textContent=!browserApproval?'Public approval is disabled; only an authenticated administrator can approve artifacts.':(approved?`Approved: ${result.approval_hash}`:(result.decision==='REPAIR'&&!survived?'Repair is locked because independent falsification did not survive.':(result.decision==='REPAIR'?'Review every artifact before approval.':'No repair is eligible for approval.')));renderDownloads(data.downloads)}
$('audit').onclick=async()=>{try{$('audit').disabled=true;$('message').className='';$('message').textContent='The audit manager is choosing evidence and experiments…';let d=await api('/api/audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:$('case').value})});if(d.job_id)d=await waitForJob(d.status_url);render(d);$('message').textContent=`Agent audit ${d.result.run_id} completed with ${d.result.decision}.`}catch(e){$('message').textContent=e.message;$('message').className='danger'}finally{$('audit').disabled=false}};
$('approve').onclick=async()=>{try{$('approve').disabled=true;$('approvalMessage').className='small';$('approvalMessage').textContent='Revalidating evidence and writing a copied workbook…';const d=await api('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:current.result.run_id,reviewer:$('reviewer').value})});render(d)}catch(e){$('approvalMessage').textContent=e.message;$('approvalMessage').className='danger'}finally{$('approve').disabled=Boolean(current?.result?.approval_hash)}};
$('reset').onclick=()=>location.reload();init().catch(e=>{$('message').textContent=e.message;$('message').className='danger'});
</script></body></html>"""


DOWNLOAD_ALLOWLIST = frozenset(
    {
        "agent-state.json",
        "approval.json",
        "formula-diff.json",
        "proposal.json",
        "repaired.xlsx",
        "report.json",
        "trajectory.jsonl",
    }
)


@dataclass(frozen=True)
class PublicServerConfig:
    """Explicit internet-facing demo boundary; secrets never enter browser configuration."""

    origin: str
    max_audits_per_hour: int = 6
    max_audits_per_client_hour: int = 2
    admin_token: str | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}:
            raise ValueError("Public origin must be an HTTPS origin without a path")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Public origin cannot contain credentials, query, or fragment")
        if self.max_audits_per_hour < 1 or self.max_audits_per_client_hour < 1:
            raise ValueError("Public audit limits must be positive")

    @property
    def hostname(self) -> str:
        hostname = urlsplit(self.origin).hostname
        assert hostname is not None
        return hostname.casefold()


class SlidingWindowRateLimiter:
    """Small in-process limiter for the single-instance public demonstration."""

    def __init__(self, *, global_limit: int, client_limit: int, window_seconds: float = 3600):
        self.global_limit = global_limit
        self.client_limit = client_limit
        self.window_seconds = window_seconds
        self._global: deque[float] = deque()
        self._clients: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client: str, *, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        with self._lock:
            while self._global and self._global[0] <= cutoff:
                self._global.popleft()
            client_events = self._clients.get(client, deque())
            while client_events and client_events[0] <= cutoff:
                client_events.popleft()
            global_exhausted = len(self._global) >= self.global_limit
            client_exhausted = len(client_events) >= self.client_limit
            if global_exhausted or client_exhausted:
                candidates: list[float] = []
                if global_exhausted:
                    candidates.append(self._global[0])
                if client_exhausted:
                    candidates.append(client_events[0])
                retry = max(
                    1,
                    round(max(candidates) + self.window_seconds - current),
                )
                return False, retry
            self._global.append(current)
            self._clients[client] = client_events
            client_events.append(current)
            return True, 0


def _is_loopback_host(host: str) -> bool:
    """Return whether a bind/Host-header name is strictly local."""

    normalized = host.strip().strip("[]").casefold()
    if normalized == "localhost":
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _trusted_host_header(value: str | None) -> bool:
    if not value:
        return False
    try:
        hostname = urlsplit(f"//{value}").hostname
    except ValueError:
        return False
    return hostname is not None and _is_loopback_host(hostname)


def _available_downloads(run_dir: Path) -> list[str]:
    return sorted(name for name in DOWNLOAD_ALLOWLIST if (run_dir / name).is_file())


def _agent_review_payload(
    result: AuditResult,
    artifact_root: Path,
    *,
    provider: str,
    model_id: str,
) -> dict[str, Any]:
    """Load the persisted, reviewable agent evidence for one completed local run."""

    run_dir = artifact_root / result.run_id
    proposal = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    state = json.loads((run_dir / "agent-state.json").read_text(encoding="utf-8"))
    citations = state.get("citations", {})
    experiments = state.get("experiments", {})
    if not isinstance(citations, dict) or not isinstance(experiments, dict):
        raise TypeError("Agent state has invalid review evidence")
    return {
        "result": result.to_dict(),
        "state": state,
        "proposal_hash": object_hash(proposal),
        "citations": [citations[key] for key in sorted(citations)],
        "experiments": [experiments[key] for key in sorted(experiments)],
        "falsifier_verdict": state.get("falsifier_verdict"),
        "provider": provider,
        "model": model_id,
        "downloads": _available_downloads(run_dir),
    }


def _summary_payload(root: Path) -> dict[str, Any]:
    evaluation = json.loads((root / "evals/results.json").read_text(encoding="utf-8"))
    performance = json.loads(
        (root / "artifacts/submission/performance-results.json").read_text(encoding="utf-8")
    )
    baseline = evaluation["baseline"]
    advanced = evaluation["advanced"]
    return {
        "benchmark": evaluation["benchmark"],
        "workbook_count": len(advanced["records"]),
        "hidden_cases_per_workbook": evaluation["hidden_case_count_per_workbook"],
        "baseline_e2e_srr": baseline["e2e_semantic_repair_rate"],
        "advanced_e2e_srr": advanced["e2e_semantic_repair_rate"],
        "improvement_pp": evaluation["improvement_percentage_points"],
        "baseline_clean_preservation": baseline["clean_preservation_rate"],
        "advanced_clean_preservation": advanced["clean_preservation_rate"],
        "baseline_hard_rate": baseline["hard_multi_rule_rate"],
        "advanced_hard_rate": advanced["hard_multi_rule_rate"],
        "baseline_runtime_seconds": performance["baseline"]["median_seconds_per_task"],
        "advanced_runtime_seconds": performance["advanced"]["median_seconds_per_task"],
        "human_time_status": performance["human_time_per_task"]["status"],
        "model_api_cost_usd_per_task": performance["model_api_cost_usd_per_task"],
    }


def make_handler(
    root: Path,
    *,
    model: ChatModel,
    provider: str,
    model_id: str,
    public_config: PublicServerConfig | None = None,
    configured_artifact_root: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    sessions: dict[str, dict[str, str]] = {}
    jobs: dict[str, dict[str, Any]] = {}
    jobs_lock = threading.Lock()
    artifact_root = (configured_artifact_root or root / "artifacts/ui").resolve(strict=False)
    artifact_root.mkdir(parents=True, exist_ok=True)
    operation_lock = threading.Lock()
    limiter = (
        None
        if public_config is None
        else SlidingWindowRateLimiter(
            global_limit=public_config.max_audits_per_hour,
            client_limit=public_config.max_audits_per_client_hour,
        )
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "FormulaWitness/0.3"

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(15)

        def _json(
            self,
            payload: Any,
            status: HTTPStatus = HTTPStatus.OK,
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            data = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            if public_config is not None:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].casefold()
            if content_type != "application/json":
                raise ValueError("Content-Type must be application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 20_000:
                raise ValueError("Request too large")
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise TypeError("JSON request body must be an object")
            return cast(dict[str, Any], payload)

        def _trusted_request(self, *, modifying: bool = False) -> bool:
            raw_host = self.headers.get("Host")
            if public_config is None:
                trusted = _trusted_host_header(raw_host)
                message = "Localhost Host header required"
            else:
                try:
                    hostname = urlsplit(f"//{raw_host or ''}").hostname
                except ValueError:
                    hostname = None
                trusted = hostname is not None and hostname.casefold() == public_config.hostname
                message = "Unrecognized public Host header"
                if trusted and modifying:
                    trusted = self.headers.get("Origin") == public_config.origin.rstrip("/")
                    message = "Same-origin request required"
            if trusted:
                return True
            self._json({"error": message}, HTTPStatus.FORBIDDEN)
            return False

        def _client_key(self) -> str:
            forwarded = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
            return (forwarded or self.client_address[0])[:128]

        def _admin_authorized(self) -> bool:
            if public_config is None:
                return True
            token = public_config.admin_token
            supplied = self.headers.get("Authorization", "")
            return bool(
                token
                and supplied.startswith("Bearer ")
                and hmac.compare_digest(supplied[7:], token)
            )

        def _run_public_audit(self, job_id: str, case_id: str) -> None:
            try:
                with jobs_lock:
                    jobs[job_id] = {"status": "running"}
                workbook = root / WORKBOOK_CASES[case_id]
                result = run_agentic(
                    workbook,
                    root / "policies/supplier_rebate_sla_policy.pdf",
                    artifact_root,
                    model=model,
                    model_id=model_id,
                )
                review = _agent_review_payload(
                    result,
                    artifact_root,
                    provider=provider,
                    model_id=model_id,
                )
                sessions[result.run_id] = {
                    "case_id": case_id,
                    "proposal_hash": str(review["proposal_hash"]),
                }
                with jobs_lock:
                    jobs[job_id] = {"status": "complete", "result": review}
            except Exception as exc:  # noqa: BLE001 - async boundary must fail closed
                print(f"[ui] public audit {job_id} failed closed: {type(exc).__name__}: {exc}")
                with jobs_lock:
                    jobs[job_id] = {
                        "status": "failed",
                        "error": "Audit failed closed; consult the server log with this job ID.",
                        "job_id": job_id,
                    }
            finally:
                operation_lock.release()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._json({"status": "ok"})
                return
            if not self._trusted_request():
                return
            if parsed.path == "/":
                data = HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                if public_config is not None:
                    self.send_header("Strict-Transport-Security", "max-age=31536000")
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path == "/api/config":
                self._json(
                    {
                        "provider": provider,
                        "model": model_id,
                        "local_only": public_config is None,
                        "public_demo": public_config is not None,
                        "browser_approval_enabled": public_config is None,
                    }
                )
                return
            if parsed.path == "/api/cases":
                cases = [
                    {"id": case_id, "label": Path(relative).stem}
                    for case_id, relative in WORKBOOK_CASES.items()
                ]
                self._json({"cases": cases})
                return
            if parsed.path == "/api/summary":
                self._json(_summary_payload(root))
                return
            if parsed.path.startswith("/api/jobs/"):
                job_id = parsed.path.removeprefix("/api/jobs/")
                with jobs_lock:
                    job = jobs.get(job_id)
                if job is None:
                    self._json({"error": "Unknown audit job"}, HTTPStatus.NOT_FOUND)
                else:
                    self._json(job)
                return
            if parsed.path.startswith("/download/"):
                parts = [unquote(part) for part in parsed.path.split("/") if part]
                if len(parts) != 3 or parts[1] not in sessions:
                    self._json({"error": "Unknown artifact"}, HTTPStatus.NOT_FOUND)
                    return
                run_id, filename = parts[1], Path(parts[2]).name
                target = artifact_root / run_id / filename
                if filename not in DOWNLOAD_ALLOWLIST or not target.is_file():
                    self._json({"error": "Artifact not available"}, HTTPStatus.NOT_FOUND)
                    return
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type", mimetypes.guess_type(filename)[0] or "application/octet-stream"
                )
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if public_config is not None:
                    self.send_header("Strict-Transport-Security", "max-age=31536000")
                self.end_headers()
                self.wfile.write(data)
                return
            self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._trusted_request(modifying=True):
                return
            try:
                payload = self._body()
                if self.path not in {"/api/audit", "/api/approve"}:
                    self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                    return
                if self.path == "/api/audit":
                    case_id = str(payload.get("case_id", ""))
                    if case_id not in WORKBOOK_CASES:
                        raise ValueError("Unknown benchmark case")
                    if not operation_lock.acquire(blocking=False):
                        self._json(
                            {"error": "Another audit or approval is already running"},
                            HTTPStatus.CONFLICT,
                        )
                        return
                    if public_config is not None:
                        assert limiter is not None
                        allowed, retry_after = limiter.allow(self._client_key())
                        if not allowed:
                            operation_lock.release()
                            self._json(
                                {"error": "Public demo audit limit reached"},
                                HTTPStatus.TOO_MANY_REQUESTS,
                                headers={"Retry-After": str(retry_after)},
                            )
                            return
                        job_id = uuid.uuid4().hex
                        with jobs_lock:
                            if len(jobs) >= 100:
                                oldest = next(iter(jobs))
                                jobs.pop(oldest, None)
                            jobs[job_id] = {"status": "queued"}
                        worker = threading.Thread(
                            target=self._run_public_audit,
                            args=(job_id, case_id),
                            daemon=True,
                            name=f"formulawitness-audit-{job_id[:8]}",
                        )
                        try:
                            worker.start()
                        except Exception:
                            with jobs_lock:
                                jobs.pop(job_id, None)
                            operation_lock.release()
                            raise
                        self._json(
                            {
                                "job_id": job_id,
                                "status": "queued",
                                "status_url": f"/api/jobs/{job_id}",
                            },
                            HTTPStatus.ACCEPTED,
                        )
                        return
                    try:
                        workbook = root / WORKBOOK_CASES[case_id]
                        result = run_agentic(
                            workbook,
                            root / "policies/supplier_rebate_sla_policy.pdf",
                            artifact_root,
                            model=model,
                            model_id=model_id,
                        )
                        review = _agent_review_payload(
                            result,
                            artifact_root,
                            provider=provider,
                            model_id=model_id,
                        )
                        sessions[result.run_id] = {
                            "case_id": case_id,
                            "proposal_hash": str(review["proposal_hash"]),
                        }
                        self._json(review)
                        return
                    finally:
                        operation_lock.release()

                if not self._admin_authorized():
                    self._json(
                        {"error": "Administrator authorization required"}, HTTPStatus.FORBIDDEN
                    )
                    return
                if not operation_lock.acquire(blocking=False):
                    self._json(
                        {"error": "Another audit or approval is already running"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                try:
                    run_id = str(payload.get("run_id", ""))
                    reviewer = str(payload.get("reviewer", "")).strip()
                    if run_id not in sessions or not reviewer or len(reviewer) > 256:
                        raise ValueError(
                            "A known run and reviewer label of 1-256 characters are required"
                        )
                    session = sessions[run_id]
                    case_id = session["case_id"]
                    workbook = root / WORKBOOK_CASES[case_id]
                    result = approve_agentic_proposal(
                        workbook,
                        root / "policies/supplier_rebate_sla_policy.pdf",
                        artifact_root,
                        run_id,
                        reviewer=reviewer,
                        expected_proposal_hash=session["proposal_hash"],
                    )
                    self._json(
                        _agent_review_payload(
                            result,
                            artifact_root,
                            provider=provider,
                            model_id=model_id,
                        )
                    )
                finally:
                    operation_lock.release()
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # noqa: BLE001 - HTTP boundary must fail closed
                if public_config is not None:
                    print(f"[ui] request failed closed: {type(exc).__name__}: {exc}")
                    self._json(
                        {"error": "Operation failed closed; consult the server log."},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                self._json(
                    {"error": f"Audit failed closed: {type(exc).__name__}: {exc}"},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[ui] {self.address_string()} {format % args}")

    return Handler


def serve(
    root: Path,
    host: str,
    port: int,
    *,
    model: ChatModel,
    provider: str,
    model_id: str,
    public_config: PublicServerConfig | None = None,
    artifact_root: Path | None = None,
) -> None:
    if public_config is None and not _is_loopback_host(host):
        raise ValueError("The unauthenticated review UI may bind only to a loopback host")
    if public_config is not None and host not in {"0.0.0.0", "::"}:
        raise ValueError("The public demo must bind to all interfaces behind its HTTPS proxy")
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(
            root,
            model=model,
            provider=provider,
            model_id=model_id,
            public_config=public_config,
            configured_artifact_root=artifact_root,
        ),
    )
    display_url = (
        f"http://{host}:{port}" if public_config is None else public_config.origin.rstrip("/")
    )
    print(f"FormulaWitness review UI: {display_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
