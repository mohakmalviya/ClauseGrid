"""Dependency-free local review interface for the ClauseGrid demo."""

from __future__ import annotations

import hmac
import json
import mimetypes
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from urllib.parse import unquote, urlparse, urlsplit

from .agent_loop import ChatModel
from .agentic import DEMO_AGENT_LIMITS, approve_agentic_proposal, run_agentic
from .models import AuditResult
from .ooxml import sha256_file
from .policy_pack import (
    MaterializedPolicyPack,
    materialize_policy_pack,
    validate_materialized_policy_pack,
)
from .policy_pack_runtime import verify_with_policy_pack
from .public_benchmark import WORKBOOK_CASES
from .trace import object_hash
from .ui_page import build_html
from .uploaded_inputs import (
    MAX_POLICY_BYTES,
    MAX_UPLOADS_PER_SERVER,
    MAX_WORKBOOK_BYTES,
    UPLOAD_TTL_SECONDS,
    StagedWorkbook,
    UploadCleanupRequired,
    UploadedAuditInput,
    UploadRejected,
    UploadResidue,
    UploadTooLarge,
    remove_upload,
    stage_policy,
    stage_workbook,
)

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClauseGrid</title>
<style>
:root{--navy:#081a2f;--navy-2:#102b4a;--blue:#2867e8;--cyan:#35d0b5;--ink:#142033;--muted:#657188;--line:#dbe3ee;--paper:#fff;--bg:#f3f6fa;--soft:#eef4fb;--ok:#117a50;--bad:#bd343d;--amber:#9b6000;--radius:14px;--radius-small:10px;--page-gutter:clamp(12px,1vw,20px);--shadow:0 12px 34px rgba(8,26,47,.07)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;overflow-x:hidden;background:radial-gradient(circle at 85% 8%,#e5f6f3 0,transparent 23%),var(--bg);color:var(--ink);font-family:Inter,"Segoe UI",Arial,sans-serif;-webkit-font-smoothing:antialiased}
header{position:sticky;top:0;z-index:10;background:rgba(8,26,47,.96);backdrop-filter:blur(12px);color:#fff;border-bottom:1px solid rgba(255,255,255,.08)}.header-inner{width:100%;margin:0;padding:14px var(--page-gutter);display:flex;align-items:center;justify-content:space-between}.brand-wrap{display:flex;align-items:center;gap:11px}.brand-mark{display:grid;place-items:center;width:36px;height:36px;border-radius:var(--radius-small);background:linear-gradient(145deg,var(--cyan),#6fe2ce);color:var(--navy);font-size:18px;font-weight:900;box-shadow:0 0 0 4px rgba(53,208,181,.12)}.brand{font-size:19px;font-weight:800;letter-spacing:-.35px}.tag{font-size:10px;color:#b8c8dc;text-transform:uppercase;letter-spacing:.16em}
main{width:100%;max-width:none;margin:0;padding:18px var(--page-gutter) 64px}.panel{width:100%;min-width:0;height:auto;background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:var(--radius);padding:clamp(18px,1.7vw,26px);box-shadow:var(--shadow)}
h1{max-width:800px;font-size:clamp(34px,4.2vw,58px);line-height:1.04;margin:0 0 18px;letter-spacing:-2.4px}h2{font-size:19px;margin:0 0 14px;letter-spacing:-.25px}h3{color:var(--navy)}p{color:var(--muted);line-height:1.62}.eyebrow{display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;color:#a9f1e4;font-size:10px;font-weight:850;letter-spacing:.14em;text-transform:uppercase}.eyebrow:before{content:"";width:22px;height:2px;background:var(--cyan)}
.product-intro{position:relative;overflow:hidden;display:grid;grid-template-columns:1.35fr .65fr;gap:34px;margin-bottom:18px;padding:44px;background:linear-gradient(130deg,var(--navy),#102d50 67%,#14425a);border:0;color:#fff}.product-intro:after{content:"";position:absolute;right:-90px;top:-120px;width:360px;height:360px;border:1px solid rgba(92,224,200,.18);border-radius:50%;box-shadow:0 0 0 55px rgba(92,224,200,.04),0 0 0 110px rgba(92,224,200,.025)}.product-intro p{color:#c7d4e3}.intro-copy{max-width:710px;margin:0;font-size:16px}.hero-proof{position:relative;z-index:1;align-self:end;padding:21px;border:1px solid rgba(255,255,255,.15);border-radius:16px;background:rgba(255,255,255,.06);backdrop-filter:blur(9px)}.proof-label{font-size:10px;color:#a8bad0;text-transform:uppercase;letter-spacing:.12em;font-weight:800}.proof-flow{display:grid;gap:10px;margin-top:15px}.proof-node{display:flex;align-items:center;gap:12px;color:#fff;font-size:13px;font-weight:700}.proof-node i{display:grid;place-items:center;width:29px;height:29px;border-radius:50%;background:rgba(53,208,181,.14);border:1px solid rgba(53,208,181,.45);color:var(--cyan);font-style:normal}.proof-line{width:1px;height:12px;margin:-4px 0 -4px 14px;background:rgba(53,208,181,.4)}
.difference{margin-bottom:18px;padding:30px;background:linear-gradient(145deg,#fff,#f8fbff)}.difference-head{display:grid;grid-template-columns:.72fr 1.28fr;gap:28px;align-items:end}.difference h2{font-size:clamp(25px,3vw,36px);line-height:1.12;margin:5px 0 0;color:var(--navy);letter-spacing:-1px}.difference-lead{margin:0;font-size:14px}.comparison-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:22px}.comparison-card{padding:19px;border:1px solid var(--line);border-radius:14px;background:#fff}.comparison-card.assurance{border-color:#9edfd4;background:linear-gradient(150deg,#f7fffd,#edf9f6)}.comparison-label{display:block;margin-bottom:10px;color:#617087;font-size:10px;font-weight:850;letter-spacing:.1em;text-transform:uppercase}.comparison-card.assurance .comparison-label{color:var(--ok)}.comparison-card h3{margin:0 0 10px;font-size:17px}.comparison-card ul{display:grid;gap:8px;margin:0;padding-left:18px;color:#536176;font-size:12px;line-height:1.5}.difference-verdict{margin-top:12px;padding:13px 15px;border-left:4px solid var(--blue);background:#edf4ff;color:#193b70;font-size:13px;font-weight:800}
.guide-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.guide-card{position:relative;background:rgba(255,255,255,.88);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 8px 24px rgba(8,26,47,.04)}.guide-index{display:block;margin-bottom:18px;color:var(--blue);font-family:Consolas,monospace;font-size:11px;font-weight:800}.guide-card h3{font-size:14px;margin:0 0 7px}.guide-card p{font-size:12px;margin:0;line-height:1.55}
.pack-overview{margin-bottom:18px;border-top:4px solid var(--blue);background:linear-gradient(145deg,#fff,#f6faff)}.pack-head{display:flex;align-items:flex-start;justify-content:space-between;gap:22px}.pack-head h2{font-size:clamp(24px,3vw,34px);margin:5px 0 8px}.pack-head p{max-width:720px;margin:0}.zero-badge{flex:0 0 auto;padding:9px 12px;border:1px solid #9edfd4;border-radius:999px;background:#effaf7;color:var(--ok);font-size:11px;font-weight:850}.pack-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:22px 0 16px}.pack-metric{padding:15px;border:1px solid var(--line);border-radius:12px;background:#fff}.pack-metric span{display:block;color:#748095;font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.pack-metric b{display:block;margin-top:7px;color:var(--navy);font-size:18px}.hash-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.hash-item{min-width:0;padding:12px;border-radius:10px;background:#edf3fa}.hash-item span{display:block;margin-bottom:5px;color:#718096;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.hash-item code{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.governance-warning{margin-top:14px;padding:13px 15px;border-left:4px solid var(--amber);background:#fff7e8;color:#6f4b0b;font-size:12px;line-height:1.55}.lifecycle{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:16px}.lifecycle-step{padding:13px;border:1px solid var(--line);border-radius:11px;background:#fff;color:#526078;font-size:11px;line-height:1.45}.lifecycle-step b{display:block;margin-bottom:5px;color:var(--blue)}
.verify-panel{margin-bottom:18px;display:block}.verify-copy{max-width:940px}.verify-copy h2{font-size:26px;margin:5px 0 10px}.verify-copy p{margin:0}.verify-controls{width:100%;margin-top:20px;padding:19px;border:1px solid #cfe4df;border-radius:var(--radius);background:#f6fffc}.verify-mode{display:flex;justify-content:space-between;gap:10px;margin-bottom:15px;color:var(--ok);font-size:11px;font-weight:850}.verify-result{width:100%;margin-top:15px;padding:16px;border:1px solid var(--line);border-radius:var(--radius);background:#fff}.verify-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.verify-details{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.verify-details div{padding:10px;border-radius:8px;background:#f2f6fb;color:#526078;font-size:10px}.verify-details b{display:block;margin-top:4px;color:var(--navy);font-size:13px}.verify-failures{margin:12px 0 0;padding-left:18px;color:var(--bad);font-size:11px;line-height:1.5}
.hero{display:grid;grid-template-columns:1.18fr .82fr;gap:18px;align-items:start;margin-bottom:18px}.hero-title{font-size:29px;line-height:1.18;margin:0 0 11px;letter-spacing:-.8px}.agent-visual{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;margin:23px 0}.agent-card{min-height:112px;padding:16px;border:1px solid #d8e4f2;border-radius:var(--radius);background:linear-gradient(160deg,#fff,#f2f7fd)}.agent-card.falsifier{background:linear-gradient(160deg,#fff,#effaf7);border-color:#d4ece7}.agent-icon{display:grid;place-items:center;width:34px;height:34px;border-radius:var(--radius-small);background:#dce9ff;color:var(--blue);font-size:17px;font-weight:900}.falsifier .agent-icon{background:#dff6f0;color:var(--ok)}.agent-card b{display:block;margin:10px 0 3px}.agent-card span{font-size:11px;color:var(--muted)}.handoff{color:#94a3b8;font-size:20px}.metric{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.metric div{border-top:1px solid var(--line);padding:13px 3px 0}.metric b{display:block;font-size:15px;color:var(--navy)}
.launch-panel{position:relative;overflow:hidden;border-top:4px solid var(--cyan);padding-top:20px}.launch-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.runtime-state{display:inline-flex;align-items:center;gap:7px;color:var(--ok);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.runtime-state:before{content:"";width:7px;height:7px;border-radius:50%;background:var(--cyan);box-shadow:0 0 0 4px rgba(53,208,181,.14)}
label{display:block;font-size:10px;font-weight:800;color:#526078;margin-bottom:7px;text-transform:uppercase;letter-spacing:.1em}select,input{width:100%;padding:13px 14px;border:1px solid #b9c7d9;border-radius:10px;background:#fff;color:var(--ink);font:inherit;outline:none;transition:.2s}select:focus,input:focus{border-color:var(--blue);box-shadow:0 0 0 4px rgba(40,103,232,.11)}code{font-family:Consolas,monospace;font-size:11px;background:#edf2f7;padding:3px 6px;border-radius:5px;word-break:break-all}
.source-tabs{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:18px 0 14px;padding:5px;border-radius:12px;background:#edf2f7}.source-tabs.single-tab{grid-template-columns:1fr}.source-tab{padding:10px;background:transparent;color:#536176;box-shadow:none}.source-tab.active{background:#fff;color:var(--navy);box-shadow:0 5px 14px rgba(8,26,47,.09)}.source-tab:hover:not(:disabled){transform:none;box-shadow:none}.upload-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.file-box{padding:12px;border:1px dashed #aabbd0;border-radius:11px;background:#f8fbff}.file-box label{margin:0 0 7px}.file-box input[type=file]{padding:9px;background:#fff;font-size:11px}.consent{display:flex;align-items:flex-start;gap:9px;margin-top:11px;padding:11px;border:1px solid #d9e3ef;border-radius:9px;background:#f8fafc;color:#536176;font-size:10px;line-height:1.45}.consent input{width:auto;margin:2px 0 0;accent-color:var(--blue)}.upload-manifest{margin-top:10px;padding:10px 12px;border-left:3px solid var(--cyan);background:#effaf7;color:#315b54;font-size:10px;line-height:1.5}.profile-note{margin:9px 0 0;font-size:10px;color:#718096;line-height:1.45}
button{border:0;border-radius:10px;padding:12px 17px;background:linear-gradient(135deg,var(--blue),#1c56cc);color:#fff;font-weight:750;cursor:pointer;box-shadow:0 8px 18px rgba(40,103,232,.2);transition:transform .15s,box-shadow .15s}button:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 10px 24px rgba(40,103,232,.26)}button.secondary{background:#edf1f6;color:var(--navy);box-shadow:none}button:disabled{opacity:.45;cursor:not-allowed}.actions{display:flex;gap:9px;margin-top:15px}.actions #audit{flex:1}#verifyMessage{min-height:20px;margin-top:12px}.run-status{margin-top:15px;padding:13px;border:1px solid #e1e8f1;border-radius:11px;background:#f7f9fc}.status-line{display:flex;align-items:flex-start;gap:9px;min-height:44px}.status-dot{flex:0 0 auto;width:8px;height:8px;margin-top:6px;border-radius:50%;background:#94a3b8}.status-dot.live{background:var(--cyan);box-shadow:0 0 0 4px rgba(53,208,181,.13);animation:pulse 1.6s infinite}.progress-track{height:4px;margin-top:11px;overflow:hidden;border-radius:99px;background:#e3e9f1}.progress-bar{width:0;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--blue),var(--cyan));transition:width .45s ease}.status-meta{min-height:13px;margin-top:7px;color:#8893a5;font-size:10px;font-family:Consolas,monospace}@keyframes pulse{50%{opacity:.45}}
button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid rgba(40,103,232,.35);outline-offset:3px}#verificationResult:focus-visible{outline:2px solid rgba(40,103,232,.28);outline-offset:-2px}#results:focus-visible{outline:none}
.steps{position:relative;display:grid;grid-template-columns:repeat(5,1fr);gap:0;margin:24px 0}.steps:before{content:"";position:absolute;top:17px;left:10%;right:10%;height:1px;background:#ccd7e5}.step{position:relative;z-index:1;color:#7a8799;font-size:11px;font-weight:750;text-align:center}.step:before{content:"";display:grid;width:11px;height:11px;margin:12px auto 9px;border:6px solid var(--bg);border-radius:50%;background:#b8c3d2;box-shadow:0 0 0 1px #b8c3d2}.step.on{color:#164fae}.step.on:before{background:var(--blue);box-shadow:0 0 0 1px var(--blue)}
.evidence{margin-bottom:18px}.evidence-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.evidence-head p{margin:4px 0 12px}.section-kicker{color:var(--blue);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.1em}.benchmark-badge{max-width:300px;background:#edf3fc;color:var(--navy);border-radius:9px;padding:8px 10px;font-size:10px;font-weight:800;text-align:right}.score-table td:nth-child(n+2),.score-table th:nth-child(n+2){text-align:right}.disclosure{margin-top:13px;padding:11px 13px;border-left:3px solid #7c8ba1;background:#f7f9fc;color:#536176;font-size:11px;line-height:1.5}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}.hidden{display:none!important}#results{scroll-margin-top:78px;display:grid;gap:14px}.results-grid{display:grid;grid-template-columns:1fr;gap:14px}.decision-panel{position:static;order:-1}.result-detail{overflow:hidden}.result-detail summary{cursor:pointer;color:var(--navy);font-size:16px;font-weight:800;list-style:none}.result-detail summary::-webkit-details-marker{display:none}.result-detail summary:after{content:'+';float:right;color:var(--blue);font-size:20px}.result-detail[open] summary:after{content:'−'}.result-detail>div{margin-top:18px}.citation-panel #citations{max-height:none;overflow:visible;padding:0}.outcome-panel{border-top:5px solid var(--amber);background:#fff}.outcome-panel.outcome-REPAIR{border-top-color:var(--blue)}.outcome-panel.outcome-NO_CHANGE{border-top-color:var(--ok)}.outcome-panel.outcome-REPAIR_REJECTED{border-top-color:var(--bad)}.outcome-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.outcome-head h2{margin:5px 0 0;font-size:clamp(24px,2.4vw,34px);line-height:1.15}.outcome-label{color:var(--muted);font-size:10px;font-weight:850;letter-spacing:.11em;text-transform:uppercase}.outcome-body{max-width:920px;margin:18px 0 0;font-size:15px;line-height:1.65}.outcome-foot{margin:16px 0 0;padding:12px 14px;border-left:3px solid var(--line);background:#f6f8fb;color:#536176;font-size:12px}.status{display:inline-flex;align-items:center;min-height:28px;padding:6px 10px;border-radius:999px;font-size:10px;font-weight:850;white-space:nowrap}.PASS,.EXACT,.NO_CHANGE,.SURVIVED{background:#dcf5e7;color:var(--ok)}.FAIL,.AMBIGUOUS,.CONFLICT,.BROKEN,.REPAIR_REJECTED{background:#fde7e7;color:var(--bad)}.REPAIR{background:#e5efff;color:#164fae}.ABSTAIN,.INCONCLUSIVE,.SAFETY_LIMIT_REACHED,.HUMAN_REVIEW{background:#fff0cf;color:var(--amber)}table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:#6a7688;border-bottom:1px solid var(--line);padding:11px 9px;text-transform:uppercase;letter-spacing:.05em;font-size:10px}td{padding:12px 9px;border-bottom:1px solid #edf0f4;vertical-align:top}.quote{border-left:3px solid var(--blue);padding:12px 14px;background:#f7f9fc;color:#39465a;font-size:13px;line-height:1.55;margin:10px 0}.patch{min-width:0;border:1px solid #c9d5e5;border-radius:var(--radius);padding:16px;margin:15px 0;background:#fbfdff}.formula-label{display:block;margin:13px 0 5px;color:#778398;font-size:10px;font-weight:800;text-transform:uppercase}.before,.after{padding:11px;border-radius:8px;background:#f5f7fa;font-family:Consolas,monospace;font-size:12px;overflow-wrap:anywhere;word-break:break-word}.before{border-left:3px solid var(--bad);color:#8e2931}.after{border-left:3px solid var(--ok);color:#0b6843}.downloads a{display:inline-block;margin:6px 6px 0 0;padding:9px 11px;border:1px solid #b8c8df;border-radius:8px;text-decoration:none;color:#164da6;background:#f7faff;font-size:12px;font-weight:750}.danger{color:var(--bad)!important}.approval{border:1px solid #efc986;background:#fff9ed}.small{font-size:12px;color:var(--muted)}
.comparison-card,.guide-card,.agent-card{border-radius:var(--radius)}.pack-metric,.hash-item,.lifecycle-step,.verify-details div,.file-box,.consent,.upload-manifest,.run-status,.patch,.before,.after,.downloads a,select,input,button,.source-tabs{border-radius:var(--radius-small)}
@media(max-width:900px){.product-intro,.difference-head,.comparison-grid,.hero,.grid,.verify-panel{grid-template-columns:1fr}.guide-grid,.pack-grid{grid-template-columns:1fr 1fr}.hash-grid{grid-template-columns:1fr}.hero-proof{align-self:stretch}.tag{display:none}.product-intro{padding:30px}h1{letter-spacing:-1.5px}.evidence-head{display:block}.benchmark-badge{text-align:left;max-width:none}.lifecycle{grid-template-columns:1fr 1fr}.outcome-head{display:grid}.outcome-head .status{justify-self:start}}
@media(max-width:580px){:root{--page-gutter:10px}main{padding:12px var(--page-gutter) 52px}.header-inner{padding:13px var(--page-gutter)}.guide-grid,.metric,.upload-grid,.pack-grid,.lifecycle,.verify-details{grid-template-columns:1fr}.pack-head{display:block}.zero-badge{display:inline-block;margin-top:13px}.product-intro{padding:25px 21px}.agent-visual{grid-template-columns:1fr}.handoff{transform:rotate(90deg);text-align:center}.steps{grid-template-columns:1fr}.steps:before{display:none}.step{text-align:left}.step:before{display:inline-block;margin:7px 10px -4px 0}.panel{padding:17px}.verify-controls,.verify-result{padding:14px}#verifyPack{min-height:56px}.actions{flex-wrap:wrap}.actions button{width:100%}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*:before,*:after{animation:none!important;transition:none!important}}
</style></head>
<body><header><div class="header-inner"><div class="brand-wrap"><div class="brand-mark">C</div><div class="brand">ClauseGrid</div></div><div class="tag">Approved policy assurance</div></div></header>
<main>
<section class="panel product-intro" aria-labelledby="productIntroTitle"><div><span class="eyebrow">Why ClauseGrid exists</span><h1 id="productIntroTitle">Decide what the policy means once. Test every workbook the same way.</h1><p class="intro-copy">ClauseGrid turns policy clauses into explicit examples and executable rules. AI may draft an interpretation, but qualified people decide what is correct. Once approved, the meaning is frozen and recurring audits run with deterministic code—without asking a model to reinterpret the policy.</p></div><aside class="hero-proof"><span class="proof-label">The governed policy lifecycle</span><div class="proof-flow"><div class="proof-node"><i>1</i>Cite the exact source clause</div><div class="proof-line"></div><div class="proof-node"><i>2</i>Compare interpretations with examples</div><div class="proof-line"></div><div class="proof-node"><i>3</i>Two qualified roles approve behavior</div><div class="proof-line"></div><div class="proof-node"><i>4</i>Reuse frozen tests with zero AI calls</div></div></aside></section>
<section class="panel difference" aria-labelledby="differenceTitle"><div class="difference-head"><div><span class="section-kicker">Why not just use Claude?</span><h2 id="differenceTitle">Claude can help once. ClauseGrid remembers the approved answer.</h2></div><p class="difference-lead"><b>Yes—Claude or another model can read a policy and suggest a formula.</b> But a new chat can reinterpret the same sentence differently. ClauseGrid separates that useful drafting step from the trusted control: people approve concrete behavior, then independent deterministic code owns every recurring pass or fail.</p></div><div class="comparison-grid"><article class="comparison-card"><span class="comparison-label">AI assistant</span><h3>Useful during setup and investigation</h3><ul><li>Finds relevant clauses</li><li>Drafts possible interpretations</li><li>Suggests workbook mappings or repairs</li><li>Never defines the approved expected answer</li></ul></article><article class="comparison-card assurance"><span class="comparison-label">ClauseGrid approved pack</span><h3>Runs the same control every time</h3><ul><li>Freezes cited rules and concrete examples</li><li>Generates boundary tests and keeps regressions</li><li>Uses an independent policy oracle for expected results</li><li>Returns the same evidence for the same hashes with zero model calls</li></ul></article></div><div class="difference-verdict">AI helps draft. People own policy meaning. Deterministic code owns recurring pass or fail.</div></section>
<section class="guide-grid" aria-label="Product overview"><div class="guide-card"><span class="guide-index">01 / APPROVE</span><h3>Review real behavior</h3><p>The policy owner and controls reviewer approve examples, thresholds, exceptions, dates, and rounding—not technical code.</p></div><div class="guide-card"><span class="guide-index">02 / FREEZE</span><h3>Publish an immutable pack</h3><p>Both reviewers attest one release hash covering the rules, complete tests, workbook mapping, and deterministic engines.</p></div><div class="guide-card"><span class="guide-index">03 / REUSE</span><h3>Audit without an LLM</h3><p>Known workbook templates run against the approved oracle and test suite. A model is not called for recurring checks.</p></div><div class="guide-card"><span class="guide-index">04 / IMPROVE</span><h3>Keep every defect class</h3><p>Production governance turns a new edge case into a reviewed regression or successor version instead of silently rewriting active meaning.</p></div></section>
<section class="panel pack-overview" aria-labelledby="packTitle"><div class="pack-head"><div><span class="section-kicker">Active controlled Policy Pack</span><h2 id="packTitle">Approved meaning that can be inspected and replayed</h2><p>The public deployment exposes one synthetic supplier-rebate pack so the complete verification mechanism is testable. Its governance view is read-only. Real version changes require authenticated reviewers, durable pack history, and an audit registry that this public demo does not claim to provide.</p></div><span class="zero-badge">Recurring audit · 0 AI calls</span></div><div class="pack-grid"><div class="pack-metric"><span>Policy version</span><b id="packVersion">Loading…</b></div><div class="pack-metric"><span>Approved rules</span><b id="packRules">—</b></div><div class="pack-metric"><span>Generated tests</span><b id="packGenerated">—</b></div><div class="pack-metric"><span>Regression tests</span><b id="packRegressions">—</b></div></div><div class="hash-grid"><div class="hash-item"><span>Policy Pack hash</span><code id="packHash">—</code></div><div class="hash-item"><span>Test-suite hash</span><code id="suiteHash">—</code></div><div class="hash-item"><span>Workbook-mapping hash</span><code id="mappingHash">—</code></div></div><div class="lifecycle" aria-label="Required production policy change lifecycle"><div class="lifecycle-step"><b>1 · Capture</b>Save the smallest real edge case.</div><div class="lifecycle-step"><b>2 · Classify</b>Test gap, policy ambiguity, mapping drift, engine gap, or bad data.</div><div class="lifecycle-step"><b>3 · Compare</b>Show source wording, concrete examples, and historical impact.</div><div class="lifecycle-step"><b>4 · Approve</b>Policy owner and controls reviewer approve the exact candidate hash.</div><div class="lifecycle-step"><b>5 · Supersede</b>A governed deployment would publish a successor and queue audits bound to the old hash.</div></div><div class="governance-warning" id="packWarning">Approval means an authorized interpretation, not proof that the policy can never be wrong. Production correction requires durable version and audit history; the public demo is read-only.</div></section>
<section class="panel verify-panel" aria-labelledby="verifyTitle"><div class="verify-copy"><span class="section-kicker">Try the real differentiator</span><h2 id="verifyTitle">Run a recurring audit with no model call</h2><p>Select a known workbook version. ClauseGrid loads the frozen Policy Pack, calculates expected outcomes with its independent rule interpreter, executes the workbook separately, and compares every generated and regression case. The source file is never modified.</p></div><div class="verify-controls"><div class="verify-mode"><span>DETERMINISTIC APPROVED-PACK MODE</span><span>MODEL CALLS: 0</span></div><label for="verifyCase">Controlled workbook version</label><select id="verifyCase"></select><div class="actions"><button id="verifyPack">Run deterministic verification</button></div><div id="verifyMessage" class="small" role="status" aria-live="polite">Ready to replay the approved suite.</div></div><div id="verificationResult" class="verify-result hidden" tabindex="-1"></div></section>
<section class="hero"><div class="panel"><span class="section-kicker">Optional AI-assisted setup and investigation</span><h2 class="hero-title">Use agents only when interpretation or diagnosis is needed</h2><p>A manager can investigate a new policy or unfamiliar workbook and a fresh-context falsifier can challenge its proposal. Neither agent can change an approved Policy Pack, set the trusted expected result, or issue the recurring deterministic verdict.</p><div class="agent-visual"><div class="agent-card"><div class="agent-icon">M</div><b>Audit manager</b><span>Finds evidence · runs experiments · proposes a draft</span></div><div class="handoff">→</div><div class="agent-card falsifier"><div class="agent-icon">F</div><b>Independent falsifier</b><span>Searches for counterexamples · blocks weak proposals</span></div></div><div class="metric"><div><b>Optional model</b><span class="small">Setup and diagnosis only</span></div><div><b>Fail-closed</b><span class="small">Uncertainty becomes ABSTAIN</span></div><div><b>No policy authority</b><span class="small">People approve meaning</span></div></div></div>
<div class="panel launch-panel"><div class="launch-head"><div><span class="section-kicker">AI-assisted investigation</span><h2 style="margin:4px 0 0">Investigate unfamiliar evidence</h2></div><span class="runtime-state">Runtime ready</span></div><label>Optional server-side AI runtime</label><div><code id="runtime">Loading configuration…</code></div><div class="source-tabs" role="tablist" aria-label="Audit input"><button type="button" class="source-tab active" id="benchmarkTab" role="tab" aria-selected="true" aria-controls="benchmarkSource">Controlled benchmark</button><button type="button" class="source-tab" id="uploadTab" role="tab" aria-selected="false" aria-controls="uploadSource">Upload workbook + policy</button></div><div id="benchmarkSource" role="tabpanel" aria-labelledby="benchmarkTab"><label for="case">Synthetic benchmark workbook</label><select id="case"></select></div><div id="uploadSource" class="hidden" role="tabpanel" aria-labelledby="uploadTab"><div class="upload-grid"><div class="file-box"><label for="workbookFile">Compatible .xlsx workbook</label><input id="workbookFile" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div><div class="file-box"><label for="policyFile">Matching policy .pdf</label><input id="policyFile" type="file" accept=".pdf,application/pdf"></div></div><label class="consent"><input id="uploadConsent" type="checkbox"><span>I confirm these files contain public, synthetic, or approved data. Selected cells, formulas, and policy passages may be sent to <b id="consentProvider">the managed AI service</b> and retained in the evidence trace.</span></label><p class="profile-note">Supported profile: calculation-focused .xlsx only; no macros, external links, drawings, comments, embedded objects, Power Query, defined names, shared/array formulas, conditional formatting, data validation, worksheet extensions, cross-sheet formula chains, or functions outside arithmetic, IF, AND, OR, MAX, MIN, ROUND, LOOKUP, and literal equality COUNTIF. Qualified raw inputs such as Inputs!A1 can be varied in experiments. Temporary input copies expire after 30 minutes.</p><div id="uploadManifest" class="upload-manifest hidden"></div></div><div class="actions"><button id="audit">Run AI investigation</button><button class="secondary" id="reset">Reset</button></div><div class="run-status"><div class="status-line"><span class="status-dot" id="statusDot"></span><div id="message" role="status" aria-live="polite">M10 demonstrates a subtle waiver-scope failure. An AI investigation can take several minutes.</div></div><div class="progress-track" role="progressbar" aria-label="AI investigation progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><div class="progress-bar" id="progressBar"></div></div><div class="status-meta" id="progressMeta">READY · waiting for a case</div></div></div></section>
<div class="steps" aria-label="Audit workflow"><div class="step on">1 · Inputs</div><div class="step" id="s2">2 · Evidence</div><div class="step" id="s3">3 · Experiments</div><div class="step" id="s4">4 · Falsification</div><div class="step" id="s5">5 · Review & approve</div></div>
<section class="panel evidence"><div class="evidence-head"><div><span class="section-kicker">Measured deterministic layer</span><h2 style="margin-top:5px">Legacy deterministic regression evidence</h2><p>This frozen scorecard validates the deterministic workbook layer. It is not model-agent performance.</p></div><div class="benchmark-badge" id="benchmarkBadge">Loading benchmark…</div></div><div style="overflow:auto"><table class="score-table"><thead><tr><th>Metric</th><th>Legacy baseline</th><th>Legacy advanced</th><th>Change</th></tr></thead><tbody id="scorecard"></tbody></table></div><div class="disclosure" id="measurementDisclosure"></div></section>
<section id="results" class="hidden" tabindex="-1"><div class="results-grid"><div class="panel decision-panel outcome-panel" id="outcomePanel"><div class="outcome-head"><div><span class="outcome-label">AI investigation result</span><h2 id="outcomeTitle">Investigation result</h2></div><span id="outcomeBadge" class="status ABSTAIN">REVIEW</span></div><div id="diagnosis"></div><p id="outcomeFoot" class="outcome-foot"></p></div></div>
<details class="panel result-detail citation-panel" open><summary>Policy evidence</summary><div id="citations"></div></details>
<details class="panel result-detail"><summary>Reproducible sandbox experiments</summary><div style="overflow:auto"><table><thead><tr><th>ID</th><th>Actor</th><th>Purpose</th><th>Observed result</th></tr></thead><tbody id="experiments"></tbody></table></div></details>
<details class="panel result-detail"><summary>Independent falsifier verdict</summary><div id="falsifier"></div></details>
<div class="panel approval hidden" id="approvalPanel"><h2>Private human approval</h2><p>This applies only to the exact copied-workbook repair above. It does not approve or change Policy Pack meaning. Review the citations experiments falsifier result and proposal hash before authorizing a copy.</p><div class="grid"><div><label for="reviewer">Reviewer label</label><input id="reviewer" value="hackathon-reviewer"></div><div><label>Source SHA-256</label><code id="sourceHash"></code><label style="margin-top:12px">Proposal hash</label><code id="proposalHash"></code></div></div><div class="actions"><button id="approve">Approve exact repair proposal</button></div><div id="approvalMessage" class="small" role="status" aria-live="polite"></div><div id="downloads" class="downloads"></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id); let current=null; let runtimeConfig=null; let activePack=null; let inputMode='benchmark'; let preparedUploadId=null; let preparedUploadSignature=null;
function node(tag,text,cls){const n=document.createElement(tag);n.textContent=text??'';if(cls)n.className=cls;return n}
const TOOL_ACTIVITY=Object.freeze({policy_manifest:['Read policy manifest','Checks the policy file hash and page count'],search_policy:['Search policy','Finds relevant policy clauses'],read_policy_page:['Read policy passage','Opens a bounded cited passage'],workbook_manifest:['Inspect workbook','Maps sheets and used regions'],read_region:['Read workbook cells','Reads a bounded cell region'],list_formulas:['List formulas','Finds formulas in a selected sheet'],inspect_dependencies:['Trace dependencies','Checks which cells feed a formula'],run_experiment:['Run sandbox test','Executes a controlled workbook experiment'],stage_candidate:['Stage repair candidate','Creates an exact proposal without changing the file'],falsify_candidate:['Start independent challenge','Hands the proposal to the fresh-context falsifier'],submit_repair:['Submit repair for review','Returns a reviewable proposal'],finish_no_change:['Finish with no change','Closes the investigation without a repair'],request_human:['Request human review','Stops safely when evidence is not enough'],report_falsification:['Report challenge result','Records whether the candidate survived']});
function ensureActivityFeed(){let feed=$('activityFeed');if(feed)return feed;feed=node('section',null,'activity-feed');feed.id='activityFeed';feed.hidden=true;feed.setAttribute('aria-label','Live agent tool activity');const head=node('div',null,'activity-feed-head');head.append(node('span','Live agent activity','activity-feed-title'));const count=node('span','0 events','activity-feed-count');count.id='activityCount';head.append(count);const list=document.createElement('ol');list.id='activityList';list.className='activity-list';list.setAttribute('aria-live','polite');list.setAttribute('aria-relevant','additions text');feed.append(head,list);$('progressMeta').insertAdjacentElement('afterend',feed);return feed}
function toolActivity(name){if(TOOL_ACTIVITY[name])return TOOL_ACTIVITY[name];const label=String(name||'tool').replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());return [label,'Completed an agent tool action']}
function compactActivityEvents(events=[]){const compact=[];for(const event of Array.isArray(events)?events:[]){let matched=-1;if(event.event==='tool_result'){for(let index=compact.length-1;index>=0;index--){const candidate=compact[index];if(candidate.event==='tool_call'&&candidate.actor===event.actor&&candidate.tool===event.tool&&candidate.turn===event.turn){matched=index;break}}}if(matched>=0)compact.splice(matched,1);compact.push(event)}return compact.slice(-10)}
function renderActivityFeed(events=[],finished=false){const feed=ensureActivityFeed();const visible=compactActivityEvents(events);if(!visible.length){feed.hidden=true;$('activityList').replaceChildren();$('activityCount').textContent='0 events';return}feed.hidden=false;$('activityCount').textContent=`${visible.length} recent event${visible.length===1?'':'s'}`;const list=$('activityList');list.replaceChildren();for(const [index,event] of visible.entries()){const item=node('li',null,'activity-event');const failed=event.ok===false;const thinking=event.event==='model_response';const calling=event.event==='tool_call';const eventActive=(thinking||calling)&&!finished&&index===visible.length-1;const state=failed?'failed':eventActive?'active':'done';item.classList.add(`activity-${state}`);const marker=node('span',failed?'!':eventActive?'…':'✓','activity-marker');marker.setAttribute('aria-hidden','true');const body=node('div',null,'activity-event-body');const top=node('div',null,'activity-event-top');const actor=event.actor==='falsifier'?'Falsifier':event.actor==='controller'?'Controller':'Audit manager';top.append(node('span',actor,'activity-actor'));let label,description;if(event.event==='run_started'){label='Run safety checks';description='Verifies the controlled inputs before agent work starts'}else if(thinking){label='Model response received';description=eventActive?'Selecting the next allowed evidence action':'The response was processed'}else{[label,description]=toolActivity(event.tool);if(calling&&eventActive)description=`Running now · ${description}`}top.append(node('strong',label,'activity-action'));const meta=[];if(event.turn!==undefined&&event.turn!==null)meta.push(`turn ${event.turn}/${event.turn_limit||'?'}`);if(event.elapsed_seconds!==undefined&&event.elapsed_seconds!==null)meta.push(`${Math.round(Number(event.elapsed_seconds))}s`);if(failed)meta.push('rejected safely');body.append(top,node('p',description,'activity-description'),node('span',meta.join(' · '),'activity-meta'));item.append(marker,body);list.append(item)}}
function splitFormulaSegments(value){const source=String(value||'').trim(),segments=[];let cursor=0;for(let i=0;i<source.length;i++){if(source[i]!=='='||!/[A-Za-z]/.test(source[i+1]||''))continue;let depth=0,sawParenthesis=false,inQuote=false,j=i+1;for(;j<source.length;j++){const ch=source[j];if(ch==='"'){if(inQuote&&source[j+1]==='"'){j++;continue}inQuote=!inQuote;continue}if(inQuote)continue;if(ch==='('){depth++;sawParenthesis=true}else if(ch===')'&&sawParenthesis){depth--;if(depth===0){j++;break}}}if(!sawParenthesis||depth!==0)continue;if(i>cursor)segments.push({type:'text',value:source.slice(cursor,i)});segments.push({type:'formula',value:source.slice(i,j)});cursor=j;i=j-1}if(cursor<source.length)segments.push({type:'text',value:source.slice(cursor)});return segments.length?segments:[{type:'text',value:source}]}
function proseParagraphs(value){const text=String(value||'').replace(/\s+/g,' ').trim();if(!text)return[];let sentences;if(typeof Intl.Segmenter==='function'){sentences=[...new Intl.Segmenter(undefined,{granularity:'sentence'}).segment(text)].map(item=>item.segment.trim()).filter(Boolean)}else{sentences=text.match(/[^.!?]+(?:[.!?]+|$)/g)?.map(item=>item.trim()).filter(Boolean)||[text]}const paragraphs=[];for(let i=0;i<sentences.length;i+=2)paragraphs.push(sentences.slice(i,i+2).join(' '));return paragraphs}
function appendReadableNarrative(container,value,wrapperClass='outcome-narrative'){const wrapper=node('div',null,wrapperClass);wrapper.append(node('span','Agent explanation','narrative-label'));let proseIndex=0;for(const segment of splitFormulaSegments(value)){if(segment.type==='formula'){const formula=node('div',null,'narrative-formula');formula.append(node('span','Formula referenced','formula-label'),node('code',segment.value));wrapper.append(formula);continue}for(const paragraph of proseParagraphs(segment.value)){const copy=node('p',paragraph,proseIndex===0?'narrative-lead':'narrative-copy');wrapper.append(copy);proseIndex++}}container.append(wrapper)}
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function decodedResponse(response,text,path){let data=null;try{data=JSON.parse(text)}catch{}if(!response.ok){const detail=data?.error||text.trim()||response.statusText;const e=new Error(`${path} failed (${response.status}): ${detail}`);e.status=response.status;throw e}if(data===null||typeof data!=='object'){throw new Error(`${path} returned an invalid server response. Reload once the runtime is ready.`)}return data}
async function api(path,options){const method=String(options?.method||'GET').toUpperCase();const attempts=method==='GET'?9:1;for(let attempt=0;attempt<attempts;attempt++){let response;try{response=await fetch(path,options)}catch(error){if(attempt+1<attempts){$('message').textContent='Connecting to the audit runtime…';await sleep(Math.min(5000,750*2**attempt));continue}throw new Error(`${path} could not reach the audit runtime: ${error.message}`)}const text=await response.text();const contentType=response.headers.get('content-type')||'';const renderColdStart=method==='GET'&&!contentType.includes('application/json')&&[404,502,503,504].includes(response.status);if(renderColdStart&&attempt+1<attempts){$('message').textContent='The hosted runtime is waking up. Retrying automatically…';$('progressMeta').textContent=`CONNECTING · RETRY ${attempt+1}/${attempts-1}`;await sleep(Math.min(5000,750*2**attempt));continue}return decodedResponse(response,text,path)}throw new Error(`${path} could not reach the audit runtime.`)}
async function sendFile(path,file,contentType){const response=await fetch(path,{method:'POST',headers:{'Content-Type':contentType},body:file});const text=await response.text();return decodedResponse(response,text,path)}
function setInputMode(mode){if(mode==='upload'&&!runtimeConfig?.uploads_enabled)return;inputMode=mode;const custom=mode==='upload';$('benchmarkSource').classList.toggle('hidden',custom);$('uploadSource').classList.toggle('hidden',!custom);$('benchmarkTab').classList.toggle('active',!custom);$('uploadTab').classList.toggle('active',custom);$('benchmarkTab').setAttribute('aria-selected',String(!custom));$('uploadTab').setAttribute('aria-selected',String(custom));$('message').textContent=custom?'Choose a compatible workbook and its matching policy. Preflight runs before the model is called.':'M10 demonstrates a subtle waiver-scope failure. An AI investigation can take several minutes.';$('progressMeta').textContent=`READY · ${custom?'WAITING FOR FILES':'WAITING FOR A CASE'}`}
function renderUploadManifest(m){const sheetNames=(m.sheets||[]).map(s=>s.name).join(', ');$('uploadManifest').textContent=`Preflight passed · ${m.formula_count} formulas · ${m.sheets?.length||0} sheets (${sheetNames}) · ${m.policy_page_count} policy pages · workbook ${m.workbook_sha256.slice(0,12)}… · policy ${m.policy_sha256.slice(0,12)}…`;$('uploadManifest').classList.remove('hidden')}
async function uploadInputs(){const workbook=$('workbookFile').files[0],policy=$('policyFile').files[0];if(!workbook||!policy)throw new Error('Select both a compatible .xlsx workbook and its matching policy .pdf.');if(!workbook.name.toLowerCase().endsWith('.xlsx'))throw new Error('Workbook must use the .xlsx extension.');if(!policy.name.toLowerCase().endsWith('.pdf'))throw new Error('Policy must use the .pdf extension.');if(!$('uploadConsent').checked)throw new Error('Confirm data authorization and model-processing consent before upload.');const limits=runtimeConfig.upload_limits||{};if(workbook.size>Number(limits.workbook_bytes||0))throw new Error('Workbook exceeds the server upload limit.');if(policy.size>Number(limits.policy_bytes||0))throw new Error('Policy PDF exceeds the server upload limit.');const signature=`${workbook.name}:${workbook.size}:${workbook.lastModified}|${policy.name}:${policy.size}:${policy.lastModified}`;if(preparedUploadId&&preparedUploadSignature===signature)return preparedUploadId;preparedUploadId=null;preparedUploadSignature=null;$('message').textContent='Validating workbook safety and supported formulas before any model call…';$('progressMeta').textContent='PREFLIGHT · OOXML SAFETY · FORMULA PROFILE';const staged=await sendFile('/api/uploads/workbook',workbook,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');const ready=await sendFile(`/api/uploads/${staged.upload_id}/policy`,policy,'application/pdf');renderUploadManifest(ready);preparedUploadId=ready.upload_id;preparedUploadSignature=signature;return ready.upload_id}
function pct(value){return `${Number(value).toFixed(1)}%`}function seconds(value){return `${Number(value).toFixed(3)} s`}
function renderSummary(s){$('benchmarkBadge').textContent=`${s.benchmark} · ${s.workbook_count} workbooks × ${s.hidden_cases_per_workbook} sealed cases`;$('scorecard').replaceChildren();const rows=[['Primary outcome: E2E-SRR',pct(s.baseline_e2e_srr),pct(s.advanced_e2e_srr),`+${Number(s.improvement_pp).toFixed(1)} pp`],['Clean preservation',pct(s.baseline_clean_preservation),pct(s.advanced_clean_preservation),'no regression'],['Challenging case H01',pct(s.baseline_hard_rate),pct(s.advanced_hard_rate),`+${Number(s.advanced_hard_rate-s.baseline_hard_rate).toFixed(1)} pp`],['Automated wall-clock, M10 median',seconds(s.baseline_runtime_seconds),seconds(s.advanced_runtime_seconds),`+${seconds(s.advanced_runtime_seconds-s.baseline_runtime_seconds)}`],['Human time per task','Not measured','Not measured','No claim'],['Model/API cost per task','$0.00 legacy','$0.00 legacy','Model cost not reported']];for(const values of rows){const tr=document.createElement('tr');for(const value of values)tr.append(node('td',value));$('scorecard').append(tr)}$('measurementDisclosure').textContent='The live agent run is reported separately and has not inherited these legacy scores. Public results expose evidence and outcome while runtime identity remains in controlled server-side artifacts.'}
function renderPack(pack){activePack=pack;$('packVersion').textContent=`${pack.policy_id} · v${pack.version}`;$('packRules').textContent=String(pack.rule_count);$('packGenerated').textContent=String(pack.generated_test_count);$('packRegressions').textContent=String(pack.regression_test_count);$('packHash').textContent=pack.pack_hash;$('suiteHash').textContent=pack.test_suite_hash;$('mappingHash').textContent=pack.mapping_hash;$('packWarning').textContent=`${pack.approval_warning} Both recorded roles attest the exact release hash above. Approval means an authorized interpretation, not proof that the policy can never be wrong. A production correction would require a new approved version and a durable registry to find audits tied to the old hash; this public demo is read-only.`}
function renderVerification(data){const v=data.verification,box=$('verificationResult');box.replaceChildren();const summary=node('div',null,'verify-summary');if(v.decision==='INCONCLUSIVE'){summary.append(node('span','INCOMPLETE','status INCONCLUSIVE'),node('b','ClauseGrid could not finish verification'),node('span','0 AI calls','small'));box.append(summary);box.append(node('p',`Some checks could not run so no pass or fail was issued · ${v.error_count} errors · ${v.skipped_count} skipped.`,'outcome-body'));if(v.failed_count)box.append(node('p',`${v.failed_count} checks disagreed but coverage was incomplete so this is not a final policy verdict.`,'small danger'))}else if(v.decision==='FAIL'){summary.append(node('span','ISSUE FOUND','status FAIL'),node('b',`${v.failed_count} of ${v.test_count} approved checks failed`),node('span',`${v.passed_count} passed · 0 AI calls`,'small'));box.append(summary);box.append(node('p','This workbook does not match the approved policy. The source file was not changed.','outcome-body'));for(const record of v.records.filter(item=>item.status==='FAIL').slice(0,8)){const failure=node('div',null,'patch');failure.append(node('b',`${record.case_id} · ${record.mismatched_cells.join(', ')}`));for(const cell of record.mismatched_cells){failure.append(node('span',`${cell} expected`,'formula-label'),node('div',String(record.expected?.[cell]),'after'),node('span',`${cell} workbook result`,'formula-label'),node('div',String(record.actual?.[cell]),'before'))}box.append(failure)}box.append(node('p',`Affected approved rules: ${v.affected_rule_ids.join(', ')||'none'}`,'small'))}else{summary.append(node('span','VERIFIED','status PASS'),node('b','Workbook matches the approved policy'),node('span',`${v.test_count} passed · 0 AI calls`,'small'));box.append(summary);box.append(node('p','Every generated boundary and retained regression check passed. The source file was not changed.','outcome-body'))}const details=document.createElement('details');details.className='small';const heading=node('summary','Evidence hashes');details.append(heading);const hashes=node('div',null,'verify-details');for(const [label,value] of [['Policy Pack',v.policy_pack_hash.slice(0,12)+'…'],['Test suite',v.test_suite_hash.slice(0,12)+'…'],['Evidence',v.evidence_hash.slice(0,12)+'…']]){const item=node('div');item.append(node('span',label),node('b',value));hashes.append(item)}details.append(hashes);box.append(details);box.classList.remove('hidden');box.focus()}
function updateProgress(p={}){const actor=p.actor||'';const turn=Number(p.turn||0),limit=Math.max(1,Number(p.turn_limit||1));let percent=actor==='falsifier'?60+(turn/limit)*27:10+(turn/limit)*45;if(!actor)percent=5;percent=Math.min(92,percent);$('progressBar').style.width=`${percent}%`;$('progressBar').parentElement.setAttribute('aria-valuenow',String(Math.round(percent)));$('statusDot').classList.add('live');const elapsed=p.elapsed_seconds===undefined?'starting':`${Number(p.elapsed_seconds).toFixed(0)}s elapsed`;const action=p.last_tool?`${p.last_tool}${p.last_ok===false?' · rejected, recovering':''}`:'preparing tools';$('progressMeta').textContent=`${actor||'CONTROLLER'} · ${elapsed} · ${action}`.toUpperCase()}
async function init(){await api('/healthz');const [data,summary,config,pack]=await Promise.all([api('/api/cases'),api('/api/summary'),api('/api/config'),api('/api/policy-pack')]);runtimeConfig=config;for(const c of data.cases){for(const id of ['case','verifyCase']){const o=node('option',`${c.id} — ${c.label}`);o.value=c.id;if(c.id==='M10')o.selected=true;$(id).append(o)}}$('runtime').textContent=config.runtime_label;$('consentProvider').textContent='the managed AI service';$('progressMeta').textContent='READY · OPTIONAL MANAGED AI RUNTIME';if(!config.uploads_enabled){$('uploadTab').classList.add('hidden');$('uploadTab').disabled=true;$('uploadTab').parentElement.classList.add('single-tab')}if(config.public_demo)$('message').textContent=config.uploads_enabled?'Public AI investigations are queued and rate-limited. Deterministic verification above never calls the model.':'Public AI investigations are queued and rate-limited. Deterministic verification above never calls the model.';renderPack(pack);renderSummary(summary)}
async function waitForJob(url){for(let attempt=0;attempt<480;attempt++){const job=await api(url);renderActivityFeed(job.activity||[],job.status==='complete'||job.status==='failed');if(job.status==='complete')return job.result;if(job.status==='failed')throw new Error(job.error||'Audit failed closed');const p=job.progress||{};if(p.actor==='falsifier')setSteps(4);else if(p.last_tool==='run_experiment')setSteps(3);else if(job.status==='running')setSteps(2);const turn=p.turn===undefined?'':` · turn ${p.turn}/${p.turn_limit}`;const elapsed=p.elapsed_seconds===undefined?'':` · ${Number(p.elapsed_seconds).toFixed(0)}s`;const action=p.last_tool?` · ${p.last_tool}${p.last_ok===false?' rejected':''}`:'';$('message').textContent=`${p.phase||'Agent audit'}${turn}${elapsed}${action}`;updateProgress(p);await new Promise(resolve=>setTimeout(resolve,1000))}throw new Error('Fast demo did not finish within eight minutes')}
function setSteps(n){for(let i=2;i<=5;i++)$('s'+i).classList.toggle('on',i<=n)}
function renderDownloads(files){$('downloads').replaceChildren();for(const f of files||[]){const a=node('a',f);a.href=`/download/${encodeURIComponent(current.result.run_id)}/${encodeURIComponent(f)}`;$('downloads').append(a)}}
function observedSummary(item){const observation=item.observation||{};const applied=(observation.applied_formula_overrides||[]).join(', ')||'source formula';const values=JSON.stringify(observation.observations||{});return `${applied} → ${values}`}
function render(data){current=data;const result=data.result;const state=data.state||{},decision=state.decision||{};$('results').classList.remove('hidden');$('sourceHash').textContent=result.source_sha256;$('proposalHash').textContent=data.proposal_hash;setSteps(5);$('progressBar').style.width='100%';$('progressBar').parentElement.setAttribute('aria-valuenow','100');$('statusDot').classList.remove('live');$('progressMeta').textContent=`COMPLETE · ${result.decision} · ${result.run_id}`;
 $('citations').replaceChildren();for(const c of data.citations||[]){const d=node('div');d.append(node('b',c.citation_id));d.append(node('div',`Page ${c.page} · characters ${c.start_char}–${c.end_char}`,'small'));d.append(node('div',c.exact_quote,'quote'));$('citations').append(d)}if(!(data.citations||[]).length)$('citations').append(node('p','No policy citation was captured during this investigation.'));
 const v=data.falsifier_verdict,reason=decision.reason_code||'';let title='The evidence was not strong enough to decide',badge='HUMAN REVIEW NEEDED',badgeClass='HUMAN_REVIEW',foot='ClauseGrid made no claim that the workbook is correct or incorrect. Nothing was changed.';if(result.decision==='REPAIR'&&(result.patches||[]).length){title='A possible formula repair is ready for review';badge='REPAIR PROPOSED';badgeClass='REPAIR';foot='This is a proposal only. The source workbook has not been changed.'}else if(result.decision==='REPAIR'){title='The repair result is incomplete';badge='RUN FAILED';badgeClass='REPAIR_REJECTED';foot='A REPAIR result without an exact formula diff is invalid and cannot be approved.'}else if(result.decision==='NO_CHANGE'){title='The investigation found no supported formula change';badge='NO REPAIR RECOMMENDED';badgeClass='NO_CHANGE';foot='This is an AI investigation result not an approved Policy Pack verdict.'}else if(reason==='REPAIR_REJECTED'||v?.status==='BROKEN'){title='The proposed repair did not pass independent checks';badge='REPAIR REJECTED';badgeClass='REPAIR_REJECTED';foot='The proposal was rejected and the original workbook was left unchanged.'}else if(reason==='SAFETY_LIMIT_REACHED'){title='The investigation stopped at a safety limit';badge='INCOMPLETE';badgeClass='SAFETY_LIMIT_REACHED';foot='No correctness claim was made and the original workbook was left unchanged.'}else if(reason==='MODEL_UNAVAILABLE'||reason==='RUNTIME_FAILURE'){title='The investigation could not complete';badge='RUN FAILED';badgeClass='REPAIR_REJECTED';foot='The run failed closed and the original workbook was left unchanged.'}$('outcomeTitle').textContent=title;$('outcomeBadge').textContent=badge;$('outcomeBadge').className=`status ${badgeClass}`;$('outcomePanel').className=`panel decision-panel outcome-panel outcome-${badgeClass}`;$('outcomeFoot').textContent=foot;$('diagnosis').replaceChildren();if(decision.explanation)appendReadableNarrative($('diagnosis'),decision.explanation);for(const p of result.patches||[]){const d=node('div',null,'patch');d.append(node('b',`${p.cell} · ${(p.rule_ids||[]).join(', ')}`),node('span','Current formula','formula-label'),node('div',p.old_formula,'before'),node('span','Proposed formula','formula-label'),node('div',p.new_formula,'after'),node('p',p.rationale,'patch-rationale'));$('diagnosis').append(d)}if(result.decision==='REPAIR'&&!runtimeConfig?.browser_approval_enabled)$('diagnosis').append(node('p','Human approval is available only in a private authenticated deployment.','small'));
 $('experiments').replaceChildren();for(const t of data.experiments||[]){const tr=document.createElement('tr');for(const value of [t.experiment_id,t.actor,t.request?.purpose||'—',observedSummary(t)])tr.append(node('td',value));$('experiments').append(tr)}if(!(data.experiments||[]).length){const tr=document.createElement('tr');const td=node('td','No sandbox experiment completed.');td.colSpan=4;tr.append(td);$('experiments').append(tr)}
 $('falsifier').replaceChildren();if(v){$('falsifier').append(node('span',v.status,'status '+v.status));if(v.explanation)appendReadableNarrative($('falsifier'),v.explanation,'verdict-narrative');if(v.counterexamples?.length)$('falsifier').append(node('div',`Counterexamples: ${v.counterexamples.join('; ')}`,'danger'));if(v.remaining_risks?.length)$('falsifier').append(node('div',`Remaining risks: ${v.remaining_risks.join('; ')}`,'small'))}else $('falsifier').append(node('p','No independent falsifier run was required or completed.'));
 const approved=Boolean(result.approval_hash),survived=v?.status==='SURVIVED',browserApproval=runtimeConfig?.browser_approval_enabled===true,showApproval=browserApproval&&result.decision==='REPAIR'&&survived;$('approvalPanel').classList.toggle('hidden',!showApproval);$('approve').disabled=!showApproval||approved;$('approvalMessage').textContent=approved?`Approved: ${result.approval_hash}`:'Review every artifact before approval.';if(data.cleanup_warning)$('approvalMessage').textContent+=` ${data.cleanup_warning}`;renderDownloads(data.downloads)}
$('benchmarkTab').onclick=()=>setInputMode('benchmark');$('uploadTab').onclick=()=>setInputMode('upload');
$('verifyPack').onclick=async()=>{try{$('verifyPack').disabled=true;$('verifyPack').textContent='Verifying…';$('verifyMessage').className='small';$('verifyMessage').textContent='Replaying the frozen suite with deterministic code. No model is being called.';const data=await api('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case_id:$('verifyCase').value})});renderVerification(data);$('verifyMessage').textContent=`Verification complete · ${data.verification.decision} · ${data.verification.model_calls} model calls.`}catch(e){$('verifyMessage').textContent=e.message;$('verifyMessage').className='danger'}finally{$('verifyPack').disabled=false;$('verifyPack').textContent='Run approved checks'}};
$('audit').onclick=async()=>{try{$('audit').disabled=true;$('audit').textContent='Investigation running…';$('message').className='';renderActivityFeed([]);let request;if(inputMode==='upload'){const uploadId=await uploadInputs();request={upload_id:uploadId}}else{request={case_id:$('case').value}}$('message').textContent='The audit manager is choosing evidence and experiments…';updateProgress({phase:'Starting safety checks'});let d=await api('/api/audit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});if(inputMode==='upload'){preparedUploadId=null;preparedUploadSignature=null}if(d.job_id)d=await waitForJob(d.status_url);render(d);$('message').textContent=`Investigation completed with ${d.result.decision}. Review the evidence below.`;$('results').scrollIntoView({behavior:'smooth',block:'start'});$('results').focus()}catch(e){if(inputMode==='upload'&&e.status===400){preparedUploadId=null;preparedUploadSignature=null}$('message').textContent=e.message;$('message').className='danger';$('statusDot').classList.remove('live');$('progressMeta').textContent='STOPPED · AUDIT FAILED CLOSED'}finally{$('audit').disabled=false;$('audit').textContent='Run AI investigation'}};
$('approve').onclick=async()=>{try{$('approve').disabled=true;$('approvalMessage').className='small';$('approvalMessage').textContent='Revalidating evidence and writing a copied workbook…';const d=await api('/api/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({run_id:current.result.run_id,reviewer:$('reviewer').value})});render(d)}catch(e){$('approvalMessage').textContent=e.message;$('approvalMessage').className='danger'}finally{$('approve').disabled=Boolean(current?.result?.approval_hash)}};
$('reset').onclick=()=>location.reload();
</script></body></html>"""

_LEGACY_SCRIPT_START = HTML.index("<script>") + len("<script>")
_LEGACY_SCRIPT_END = HTML.rindex("</script>")
HTML = build_html(HTML[_LEGACY_SCRIPT_START:_LEGACY_SCRIPT_END])


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
APPROVAL_GATED_DOWNLOADS = frozenset({"approval.json", "repaired.xlsx", "report.json"})
PUBLIC_DOWNLOAD_BLOCKLIST = frozenset({"proposal.json", "report.json", "trajectory.jsonl"})
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_CONCURRENT_UPLOAD_PROCESSING = 2
MAX_PUBLIC_ACTIVITY_EVENTS = 32


def _public_activity_event(update: dict[str, object], *, sequence: int) -> dict[str, object]:
    """Reduce an agent callback to safe, observable UI activity metadata."""

    actor = str(update.get("actor", "audit-manager"))
    if actor not in {"audit-manager", "falsifier"}:
        actor = "audit-manager"
    event = str(update.get("event", "progress"))
    if event not in {"model_response", "tool_call", "tool_result"}:
        event = "progress"
    budget = cast(dict[str, Any], update.get("budget", {}))
    manager = actor == "audit-manager"
    turn_key = "manager_turns_used" if manager else "falsifier_turns_used"
    limit_key = "manager_turn_limit" if manager else "falsifier_turn_limit"
    entry: dict[str, object] = {
        "sequence": sequence,
        "event": event,
        "actor": actor,
        "phase": "Audit manager" if manager else "Independent falsifier",
        "turn": budget.get(turn_key),
        "turn_limit": budget.get(limit_key),
        "elapsed_seconds": budget.get("elapsed_time_seconds"),
    }
    tool = update.get("tool")
    if isinstance(tool, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", tool):
        entry["tool"] = tool
    ok = update.get("ok")
    if isinstance(ok, bool):
        entry["ok"] = ok
    return entry


@dataclass(frozen=True)
class PublicServerConfig:
    """Explicit internet-facing demo boundary; secrets never enter browser configuration."""

    origin: str
    max_audits_per_hour: int = 6
    max_audits_per_client_hour: int = 2
    admin_token: str | None = None
    uploads_enabled: bool = False

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


def _start_upload_reaper(
    reap_uploads: Callable[[], None], retention_seconds: float
) -> tuple[threading.Event, threading.Thread]:
    stop = threading.Event()
    interval = max(1.0, min(30.0, retention_seconds / 4))

    def cleanup_loop() -> None:
        while not stop.wait(interval):
            reap_uploads()

    thread = threading.Thread(
        target=cleanup_loop,
        daemon=True,
        name="formulawitness-upload-reaper",
    )
    thread.start()
    return stop, thread


def _trusted_host_header(value: str | None) -> bool:
    if not value:
        return False
    try:
        hostname = urlsplit(f"//{value}").hostname
    except ValueError:
        return False
    return hostname is not None and _is_loopback_host(hostname)


def _valid_approval_commit(run_dir: Path) -> bool:
    """Require the manifest-last marker to bind the repaired workbook and report."""

    approval_path = run_dir / "approval.json"
    repaired_path = run_dir / "repaired.xlsx"
    report_path = run_dir / "report.json"
    if not all(path.is_file() for path in (approval_path, repaired_path, report_path)):
        return False
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(approval, dict) or not isinstance(report, dict):
            return False
        approval_hash = approval.get("approval_hash")
        committed = {key: value for key, value in approval.items() if key != "approval_hash"}
        return bool(
            isinstance(approval_hash, str)
            and approval.get("decision") == "APPROVE"
            and hmac.compare_digest(object_hash(committed), approval_hash)
            and hmac.compare_digest(
                str(approval.get("repaired_sha256", "")), sha256_file(repaired_path)
            )
            and hmac.compare_digest(str(report.get("approval_hash", "")), approval_hash)
            and report.get("output_workbook") == "repaired.xlsx"
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _available_downloads(run_dir: Path, *, public: bool = False) -> list[str]:
    approval_committed = _valid_approval_commit(run_dir)
    return sorted(
        name
        for name in DOWNLOAD_ALLOWLIST
        if (run_dir / name).is_file()
        and (name not in APPROVAL_GATED_DOWNLOADS or approval_committed)
        and (not public or name not in PUBLIC_DOWNLOAD_BLOCKLIST)
    )


def _without_runtime_identity(value: Any) -> Any:
    """Remove provider/model routing metadata from an anonymous public response."""

    blocked = {"provider", "canonical_provider", "model", "model_id", "base_url"}
    if isinstance(value, dict):
        return {
            key: _without_runtime_identity(item)
            for key, item in value.items()
            if str(key).casefold() not in blocked
        }
    if isinstance(value, list):
        return [_without_runtime_identity(item) for item in value]
    return value


def _agent_review_payload(
    result: AuditResult,
    artifact_root: Path,
    *,
    provider: str,
    model_id: str,
    disclose_runtime_identity: bool = True,
) -> dict[str, Any]:
    """Load the persisted, reviewable agent evidence for one completed local run."""

    run_dir = artifact_root / result.run_id
    proposal = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    state = json.loads((run_dir / "agent-state.json").read_text(encoding="utf-8"))
    citations = state.get("citations", {})
    experiments = state.get("experiments", {})
    if not isinstance(citations, dict) or not isinstance(experiments, dict):
        raise TypeError("Agent state has invalid review evidence")
    payload = {
        "result": result.to_dict(),
        "state": state,
        "proposal_hash": object_hash(proposal),
        "citations": [citations[key] for key in sorted(citations)],
        "experiments": [experiments[key] for key in sorted(experiments)],
        "falsifier_verdict": state.get("falsifier_verdict"),
        "provider": provider,
        "model": model_id,
        "downloads": _available_downloads(run_dir, public=not disclose_runtime_identity),
    }
    if not disclose_runtime_identity:
        return cast(dict[str, Any], _without_runtime_identity(payload))
    return payload


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
    configured_private_root: Path | None = None,
) -> type[BaseHTTPRequestHandler]:
    sessions: dict[str, dict[str, str]] = {}
    jobs: dict[str, dict[str, Any]] = {}
    jobs_lock = threading.Lock()
    uploads: dict[str, StagedWorkbook | UploadedAuditInput] = {}
    upload_created_at: dict[str, float] = {}
    retained_uploads: dict[str, UploadedAuditInput] = {}
    retained_created_at: dict[str, float] = {}
    cleanup_pending_uploads: dict[str, StagedWorkbook | UploadedAuditInput | UploadResidue] = {}
    upload_processing: dict[str, bool] = {}
    uploads_lock = threading.Lock()
    pack_lock = threading.Lock()
    pack_cache = materialize_policy_pack(root)
    artifact_root = (configured_artifact_root or root / "artifacts/ui").resolve(strict=False)
    artifact_root.mkdir(parents=True, exist_ok=True)
    uploads_enabled = public_config is None or public_config.uploads_enabled
    private_runtime = None
    private_root: Path | None = None
    if uploads_enabled:
        if configured_private_root is None:
            private_runtime = TemporaryDirectory(prefix="formulawitness-private-")
            private_root = Path(private_runtime.name).resolve()
        else:
            private_root = configured_private_root.resolve(strict=False)
            private_root.mkdir(parents=True, exist_ok=True)
        (private_root / "uploads").mkdir(parents=True, exist_ok=True)
        (private_root / "runs").mkdir(parents=True, exist_ok=True)
    operation_lock = threading.Lock()
    audit_limiter = (
        None
        if public_config is None
        else SlidingWindowRateLimiter(
            global_limit=public_config.max_audits_per_hour,
            client_limit=public_config.max_audits_per_client_hour,
        )
    )
    verification_limiter = (
        None
        if public_config is None
        else SlidingWindowRateLimiter(
            global_limit=max(24, public_config.max_audits_per_hour * 4),
            client_limit=max(8, public_config.max_audits_per_client_hour * 4),
        )
    )
    upload_limiter = (
        SlidingWindowRateLimiter(
            global_limit=max(4, public_config.max_audits_per_hour * 2),
            client_limit=max(2, public_config.max_audits_per_client_hour * 2),
        )
        if public_config is not None and uploads_enabled
        else None
    )

    def approved_pack() -> MaterializedPolicyPack:
        with pack_lock:
            validate_materialized_policy_pack(pack_cache)
            return pack_cache

    def try_remove_upload(
        upload: StagedWorkbook | UploadedAuditInput | UploadResidue, *, context: str
    ) -> bool:
        for attempt in range(1, 3):
            try:
                remove_upload(upload)
                return True
            except Exception as exc:  # noqa: BLE001 - cleanup must reach a terminal state
                print(
                    f"[ui] {context} cleanup attempt {attempt} failed: {type(exc).__name__}: {exc}"
                )
        return False

    def queue_cleanup(
        key: str, upload: StagedWorkbook | UploadedAuditInput | UploadResidue
    ) -> None:
        with uploads_lock:
            cleanup_pending_uploads[key] = upload

    def reserve_upload_processing(*, new_workbook: bool) -> str | None:
        with uploads_lock:
            tracked = len(uploads) + len(retained_uploads) + len(cleanup_pending_uploads)
            if len(upload_processing) >= MAX_CONCURRENT_UPLOAD_PROCESSING:
                return None
            if new_workbook and tracked + len(upload_processing) >= MAX_UPLOADS_PER_SERVER:
                return None
            reservation = uuid.uuid4().hex
            upload_processing[reservation] = new_workbook
            return reservation

    def release_upload_processing(reservation: str) -> None:
        with uploads_lock:
            upload_processing.pop(reservation, None)

    def reap_expired_uploads() -> None:
        cutoff = time.monotonic() - UPLOAD_TTL_SECONDS
        with uploads_lock:
            for upload_id, created_at in tuple(upload_created_at.items()):
                if created_at > cutoff:
                    continue
                upload = uploads.pop(upload_id, None)
                upload_created_at.pop(upload_id, None)
                if upload is not None:
                    cleanup_pending_uploads[f"upload:{upload_id}"] = upload
            if not operation_lock.locked():
                for run_id, created_at in tuple(retained_created_at.items()):
                    if created_at > cutoff:
                        continue
                    upload = retained_uploads.pop(run_id, None)
                    retained_created_at.pop(run_id, None)
                    if upload is not None:
                        cleanup_pending_uploads[f"run:{run_id}"] = upload
            pending_cleanup = tuple(cleanup_pending_uploads.items())
        for cleanup_key, cleanup_upload in pending_cleanup:
            if not try_remove_upload(cleanup_upload, context=cleanup_key):
                continue
            with uploads_lock:
                if cleanup_pending_uploads.get(cleanup_key) is cleanup_upload:
                    cleanup_pending_uploads.pop(cleanup_key, None)

    class Handler(BaseHTTPRequestHandler):
        server_version = "ClauseGrid/0.4"
        _private_runtime = private_runtime
        _reap_expired_uploads = staticmethod(reap_expired_uploads)
        _uploads_enabled = uploads_enabled

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

        def _binary_body(self, *, expected_type: str, max_bytes: int) -> bytes | None:
            if self.headers.get("Transfer-Encoding"):
                self._json(
                    {"error": "Chunked upload bodies are not supported"},
                    HTTPStatus.LENGTH_REQUIRED,
                )
                return None
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].casefold()
            if content_type != expected_type:
                self._json(
                    {"error": f"Content-Type must be {expected_type}"},
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                )
                return None
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                self._json({"error": "Content-Length is required"}, HTTPStatus.LENGTH_REQUIRED)
                return None
            try:
                length = int(raw_length)
            except ValueError:
                self._json({"error": "Content-Length is invalid"}, HTTPStatus.BAD_REQUEST)
                return None
            if length < 1:
                self._json({"error": "Upload body is empty"}, HTTPStatus.BAD_REQUEST)
                return None
            if length > max_bytes:
                self._json(
                    {"error": f"Upload exceeds the {max_bytes // 1_000_000} MB limit"},
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                )
                return None
            content = self.rfile.read(length)
            if len(content) != length:
                self._json({"error": "Upload body was truncated"}, HTTPStatus.BAD_REQUEST)
                return None
            return content

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

        def _ready_pack(self) -> MaterializedPolicyPack | None:
            try:
                return approved_pack()
            except Exception as exc:  # noqa: BLE001 - readiness boundary fails closed
                print(f"[ui] approved pack unavailable: {type(exc).__name__}: {exc}")
                self._json(
                    {"error": "Approved Policy Pack is unavailable"},
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return None

        def _run_audit(
            self,
            job_id: str,
            workbook: Path,
            policy_pdf: Path,
            run_artifact_root: Path,
            input_kind: str,
            source_id: str,
            uploaded_input: UploadedAuditInput | None,
        ) -> None:
            retained_run_id: str | None = None
            try:
                with jobs_lock:
                    jobs[job_id] = {
                        "status": "running",
                        "progress": {"phase": "Starting safety checks"},
                        "activity": [
                            {
                                "sequence": 1,
                                "event": "run_started",
                                "actor": "controller",
                                "phase": "Safety checks",
                            }
                        ],
                    }

                def publish_progress(update: dict[str, object]) -> None:
                    budget = cast(dict[str, Any], update.get("budget", {}))
                    actor = str(update.get("actor", "audit-manager"))
                    manager = actor == "audit-manager"
                    progress = {
                        "phase": "Audit manager" if manager else "Independent falsifier",
                        "actor": actor,
                        "turn": budget.get(
                            "manager_turns_used" if manager else "falsifier_turns_used"
                        ),
                        "turn_limit": budget.get(
                            "manager_turn_limit" if manager else "falsifier_turn_limit"
                        ),
                        "elapsed_seconds": budget.get("elapsed_time_seconds"),
                        "last_tool": update.get("tool"),
                        "last_ok": update.get("ok"),
                    }
                    with jobs_lock:
                        current = jobs.get(job_id)
                        if current is not None and current.get("status") == "running":
                            current["progress"] = progress
                            activity = cast(list[dict[str, object]], current["activity"])
                            previous_sequence = activity[-1].get("sequence", 0) if activity else 0
                            next_sequence = (
                                previous_sequence + 1 if isinstance(previous_sequence, int) else 1
                            )
                            activity.append(_public_activity_event(update, sequence=next_sequence))
                            del activity[:-MAX_PUBLIC_ACTIVITY_EVENTS]

                if uploaded_input is not None and (
                    sha256_file(workbook) != uploaded_input.workbook_sha256
                    or sha256_file(policy_pdf) != uploaded_input.policy_sha256
                ):
                    raise ValueError("Uploaded input hash changed after compatibility preflight")
                result = run_agentic(
                    workbook,
                    policy_pdf,
                    run_artifact_root,
                    model=model,
                    model_id=model_id,
                    limits=DEMO_AGENT_LIMITS,
                    manager_max_context_chars=30_000,
                    falsifier_max_context_chars=24_000,
                    manager_experiment_after_turns=10,
                    falsifier_experiment_after_turns=1,
                    manager_experiment_attempt_limit=4,
                    falsifier_experiment_attempt_limit=6,
                    progress_callback=publish_progress,
                )
                if uploaded_input is not None and (
                    result.source_sha256 != uploaded_input.workbook_sha256
                    or result.rules_sha256 != uploaded_input.policy_sha256
                    or sha256_file(workbook) != uploaded_input.workbook_sha256
                    or sha256_file(policy_pdf) != uploaded_input.policy_sha256
                ):
                    raise ValueError("Agent result is not bound to the preflighted uploaded hashes")
                review = _agent_review_payload(
                    result,
                    run_artifact_root,
                    provider=provider,
                    model_id=model_id,
                    disclose_runtime_identity=public_config is None,
                )
                sessions[result.run_id] = {
                    "proposal_hash": str(review["proposal_hash"]),
                    "workbook": str(workbook),
                    "policy": str(policy_pdf),
                    "artifact_root": str(run_artifact_root),
                    "input_kind": input_kind,
                    "source_id": source_id,
                }
                if uploaded_input is not None:
                    if result.decision == "REPAIR":
                        with uploads_lock:
                            retained_uploads[result.run_id] = uploaded_input
                            retained_created_at[result.run_id] = time.monotonic()
                        retained_run_id = result.run_id
                    else:
                        if not try_remove_upload(
                            uploaded_input, context=f"completed audit {job_id}"
                        ):
                            queue_cleanup(f"job:{job_id}", uploaded_input)
                            review["cleanup_pending"] = True
                            review["cleanup_warning"] = (
                                "The audit completed, but temporary input deletion is queued for "
                                "retry. Stop the local server to force runtime cleanup."
                            )
                with jobs_lock:
                    current = jobs.get(job_id, {})
                    activity = list(current.get("activity", []))
                    jobs[job_id] = {
                        "status": "complete",
                        "result": review,
                        "activity": activity,
                    }
            except Exception as exc:  # noqa: BLE001 - async boundary must fail closed
                print(f"[ui] audit {job_id} failed closed: {type(exc).__name__}: {exc}")
                if uploaded_input is not None:
                    with uploads_lock:
                        if retained_run_id is not None:
                            retained_uploads.pop(retained_run_id, None)
                            retained_created_at.pop(retained_run_id, None)
                    if not try_remove_upload(uploaded_input, context=f"failed audit {job_id}"):
                        queue_cleanup(f"job:{job_id}", uploaded_input)
                with jobs_lock:
                    current = jobs.get(job_id, {})
                    activity = list(current.get("activity", []))
                    jobs[job_id] = {
                        "status": "failed",
                        "error": "Audit failed closed; consult the server log with this job ID.",
                        "job_id": job_id,
                        "activity": activity,
                    }
            finally:
                operation_lock.release()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                if self._ready_pack() is None:
                    return
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
                if self._ready_pack() is None:
                    return
                config_payload: dict[str, Any] = {
                    "runtime_label": (
                        f"{provider} · {model_id}"
                        if public_config is None
                        else "Managed private AI runtime"
                    ),
                    "local_only": public_config is None,
                    "public_demo": public_config is not None,
                    "browser_approval_enabled": public_config is None,
                    "uploads_enabled": uploads_enabled,
                    "approved_pack_available": True,
                    "deterministic_verification": {
                        "model_required": False,
                        "model_calls": 0,
                    },
                    "upload_limits": {
                        "workbook_bytes": MAX_WORKBOOK_BYTES,
                        "policy_bytes": MAX_POLICY_BYTES,
                        "retention_seconds": UPLOAD_TTL_SECONDS,
                    },
                    "demo_turn_limits": {
                        "manager": DEMO_AGENT_LIMITS.manager_turn_limit,
                        "falsifier": DEMO_AGENT_LIMITS.falsifier_turn_limit,
                    },
                }
                if public_config is None:
                    config_payload.update({"provider": provider, "model": model_id})
                self._json(config_payload)
                return
            if parsed.path == "/api/policy-pack":
                pack = self._ready_pack()
                if pack is not None:
                    self._json(pack.public_manifest())
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
                    job = deepcopy(jobs.get(job_id))
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
                session_artifact_root = Path(sessions[run_id]["artifact_root"])
                run_dir = session_artifact_root / run_id
                if public_config is not None and filename in PUBLIC_DOWNLOAD_BLOCKLIST:
                    self._json({"error": "Artifact not available"}, HTTPStatus.NOT_FOUND)
                    return
                target = run_dir / filename
                if filename not in DOWNLOAD_ALLOWLIST or not target.is_file():
                    self._json({"error": "Artifact not available"}, HTTPStatus.NOT_FOUND)
                    return
                if filename in APPROVAL_GATED_DOWNLOADS and not _valid_approval_commit(run_dir):
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
            if uploads_enabled:
                reap_expired_uploads()
            try:
                parsed_path = urlparse(self.path).path
                if parsed_path == "/api/uploads/workbook":
                    if not uploads_enabled or private_root is None:
                        self._json(
                            {"error": "Workbook uploads are disabled"},
                            HTTPStatus.FORBIDDEN,
                        )
                        return
                    if upload_limiter is not None:
                        allowed, retry_after = upload_limiter.allow(self._client_key())
                        if not allowed:
                            self._json(
                                {"error": "Public upload limit reached"},
                                HTTPStatus.TOO_MANY_REQUESTS,
                                headers={"Retry-After": str(retry_after)},
                            )
                            return
                    reservation = reserve_upload_processing(new_workbook=True)
                    if reservation is None:
                        self._json(
                            {"error": "Private upload processing capacity is currently full"},
                            HTTPStatus.TOO_MANY_REQUESTS,
                        )
                        return
                    try:
                        content = self._binary_body(
                            expected_type=(
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            ),
                            max_bytes=MAX_WORKBOOK_BYTES,
                        )
                        if content is None:
                            return
                        try:
                            staged = stage_workbook(private_root / "uploads", content)
                        except UploadCleanupRequired as exc:
                            queue_cleanup(f"upload:{exc.residue.upload_id}", exc.residue)
                            raise
                        with uploads_lock:
                            uploads[staged.upload_id] = staged
                            upload_created_at[staged.upload_id] = time.monotonic()
                        self._json(staged.public_manifest(), HTTPStatus.CREATED)
                    finally:
                        release_upload_processing(reservation)
                    return

                policy_match = re.fullmatch(
                    r"/api/uploads/(?P<upload_id>[0-9a-f]{32})/policy", parsed_path
                )
                if policy_match is not None:
                    if not uploads_enabled or private_root is None:
                        self._json(
                            {"error": "Policy uploads are disabled"},
                            HTTPStatus.FORBIDDEN,
                        )
                        return
                    reservation = reserve_upload_processing(new_workbook=False)
                    if reservation is None:
                        self._json(
                            {"error": "Private upload processing capacity is currently full"},
                            HTTPStatus.TOO_MANY_REQUESTS,
                        )
                        return
                    try:
                        content = self._binary_body(
                            expected_type="application/pdf", max_bytes=MAX_POLICY_BYTES
                        )
                        if content is None:
                            return
                        upload_id = policy_match.group("upload_id")
                        with uploads_lock:
                            candidate_upload = uploads.get(upload_id)
                            if isinstance(candidate_upload, StagedWorkbook):
                                pending_upload = uploads.pop(upload_id)
                                upload_created_at.pop(upload_id, None)
                            else:
                                pending_upload = None
                        if not isinstance(pending_upload, StagedWorkbook):
                            raise TypeError("Unknown upload or policy already attached")
                        try:
                            ready = stage_policy(pending_upload, content)
                        except Exception:
                            if not try_remove_upload(
                                pending_upload, context=f"rejected policy {upload_id}"
                            ):
                                queue_cleanup(f"upload:{upload_id}", pending_upload)
                            raise
                        with uploads_lock:
                            uploads[upload_id] = ready
                            upload_created_at[upload_id] = time.monotonic()
                        self._json(ready.public_manifest(), HTTPStatus.CREATED)
                    finally:
                        release_upload_processing(reservation)
                    return

                payload = self._body()
                if parsed_path not in {"/api/verify", "/api/audit", "/api/approve"}:
                    self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                    return
                if parsed_path == "/api/verify":
                    case_id = str(payload.get("case_id", "")).strip()
                    if case_id not in WORKBOOK_CASES:
                        raise ValueError("Unknown benchmark case")
                    if not operation_lock.acquire(blocking=False):
                        self._json(
                            {"error": "Another audit or approval is already running"},
                            HTTPStatus.CONFLICT,
                        )
                        return
                    try:
                        if public_config is not None:
                            assert verification_limiter is not None
                            allowed, retry_after = verification_limiter.allow(self._client_key())
                            if not allowed:
                                self._json(
                                    {"error": "Public demo audit limit reached"},
                                    HTTPStatus.TOO_MANY_REQUESTS,
                                    headers={"Retry-After": str(retry_after)},
                                )
                                return
                        pack = approved_pack()
                        verification = verify_with_policy_pack(root / WORKBOOK_CASES[case_id], pack)
                        failed_rules = set(verification["affected_rule_ids"])
                        citations = [
                            {
                                "rule_id": rule.rule_id,
                                "title": rule.title,
                                "page": rule.evidence.page,
                                "exact_quote": rule.evidence.exact_quote,
                            }
                            for rule in pack.rules
                            if rule.rule_id in failed_rules
                        ]
                        self._json(
                            {
                                "verification": verification,
                                "policy_pack": pack.public_manifest(),
                                "citations": citations,
                            }
                        )
                    finally:
                        operation_lock.release()
                    return
                if parsed_path == "/api/audit":
                    case_id = str(payload.get("case_id", "")).strip()
                    upload_id = str(payload.get("upload_id", "")).strip()
                    if bool(case_id) == bool(upload_id):
                        raise ValueError("Choose exactly one benchmark case or private upload")
                    if upload_id:
                        if not uploads_enabled or private_root is None:
                            raise ValueError("Uploads are disabled")
                        if UPLOAD_ID_RE.fullmatch(upload_id) is None:
                            raise ValueError("Upload identifier is invalid")
                        reap_expired_uploads()
                        with uploads_lock:
                            uploaded = uploads.get(upload_id)
                        if not isinstance(uploaded, UploadedAuditInput):
                            raise ValueError(
                                "Upload is unknown or still requires a matching policy PDF"
                            )
                        workbook = uploaded.workbook_path
                        policy_pdf = uploaded.policy_path
                        run_artifact_root = private_root / "runs"
                        input_kind = "upload"
                        source_id = upload_id
                        uploaded_input: UploadedAuditInput | None = uploaded
                    else:
                        if case_id not in WORKBOOK_CASES:
                            raise ValueError("Unknown benchmark case")
                        workbook = root / WORKBOOK_CASES[case_id]
                        policy_pdf = root / "policies/supplier_rebate_sla_policy.pdf"
                        run_artifact_root = artifact_root
                        input_kind = "benchmark"
                        source_id = case_id
                        uploaded_input = None
                    if not operation_lock.acquire(blocking=False):
                        self._json(
                            {"error": "Another audit or approval is already running"},
                            HTTPStatus.CONFLICT,
                        )
                        return
                    if public_config is not None:
                        assert audit_limiter is not None
                        allowed, retry_after = audit_limiter.allow(self._client_key())
                        if not allowed:
                            operation_lock.release()
                            self._json(
                                {"error": "Public demo audit limit reached"},
                                HTTPStatus.TOO_MANY_REQUESTS,
                                headers={"Retry-After": str(retry_after)},
                            )
                            return
                    if uploaded_input is not None:
                        with uploads_lock:
                            claimed_upload = uploads.pop(source_id, None)
                            upload_created_at.pop(source_id, None)
                        if claimed_upload is not uploaded_input:
                            operation_lock.release()
                            raise ValueError("Upload is unknown, expired, or already in use")
                    job_id = uuid.uuid4().hex
                    with jobs_lock:
                        if len(jobs) >= 100:
                            oldest = next(iter(jobs))
                            jobs.pop(oldest, None)
                        jobs[job_id] = {"status": "queued"}
                    worker = threading.Thread(
                        target=self._run_audit,
                        args=(
                            job_id,
                            workbook,
                            policy_pdf,
                            run_artifact_root,
                            input_kind,
                            source_id,
                            uploaded_input,
                        ),
                        daemon=True,
                        name=f"formulawitness-audit-{job_id[:8]}",
                    )
                    try:
                        worker.start()
                    except Exception:
                        with jobs_lock:
                            jobs.pop(job_id, None)
                        operation_lock.release()
                        if uploaded_input is not None and not try_remove_upload(
                            uploaded_input, context=f"unstarted audit {job_id}"
                        ):
                            queue_cleanup(f"job:{job_id}", uploaded_input)
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
                    workbook = Path(session["workbook"])
                    policy_pdf = Path(session["policy"])
                    session_artifact_root = Path(session["artifact_root"])
                    retained_upload: UploadedAuditInput | None = None
                    if session["input_kind"] == "upload":
                        with uploads_lock:
                            retained_upload = retained_uploads.get(run_id)
                        if retained_upload is None:
                            raise ValueError("Uploaded audit input is no longer available")
                    result = approve_agentic_proposal(
                        workbook,
                        policy_pdf,
                        session_artifact_root,
                        run_id,
                        reviewer=reviewer,
                        expected_proposal_hash=session["proposal_hash"],
                    )
                    response_payload = _agent_review_payload(
                        result,
                        session_artifact_root,
                        provider=provider,
                        model_id=model_id,
                    )
                    if retained_upload is not None:
                        cleanup_ok = try_remove_upload(
                            retained_upload, context=f"approved run {run_id}"
                        )
                        with uploads_lock:
                            retained_uploads.pop(run_id, None)
                            retained_created_at.pop(run_id, None)
                            if not cleanup_ok:
                                cleanup_pending_uploads[f"run:{run_id}"] = retained_upload
                        if not cleanup_ok:
                            response_payload["cleanup_pending"] = True
                            response_payload["cleanup_warning"] = (
                                "Approval succeeded, but temporary input deletion is queued for "
                                "retry. Stop the local server to force runtime cleanup."
                            )
                    self._json(response_payload)
                finally:
                    operation_lock.release()
            except UploadTooLarge as exc:
                self._json({"error": str(exc)}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            except (UploadRejected, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
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
    handler = make_handler(
        root,
        model=model,
        provider=provider,
        model_id=model_id,
        public_config=public_config,
        configured_artifact_root=artifact_root,
    )
    server = ThreadingHTTPServer((host, port), handler)
    cleanup_stop: threading.Event | None = None
    cleanup_thread: threading.Thread | None = None
    if public_config is None or public_config.uploads_enabled:
        reap_uploads = cast(Any, handler)._reap_expired_uploads
        cleanup_stop, cleanup_thread = _start_upload_reaper(reap_uploads, UPLOAD_TTL_SECONDS)
    display_url = (
        f"http://{host}:{port}" if public_config is None else public_config.origin.rstrip("/")
    )
    print(f"ClauseGrid review UI: {display_url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if cleanup_stop is not None:
            cleanup_stop.set()
        if cleanup_thread is not None:
            cleanup_thread.join(timeout=5)
        server.server_close()
        private_runtime = getattr(handler, "_private_runtime", None)
        if private_runtime is not None:
            private_runtime.cleanup()
