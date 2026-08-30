import hashlib
import inspect
import json
import shutil
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

import formulawitness.ui as ui_module
from formulawitness.agent_types import ModelRequest, ModelTurn, ModelUsage, ToolCall
from formulawitness.cli import build_parser
from formulawitness.models import AuditResult
from formulawitness.trace import object_hash
from formulawitness.ui import (
    HTML,
    PublicServerConfig,
    SlidingWindowRateLimiter,
    _agent_review_payload,
    _is_loopback_host,
    _start_upload_reaper,
    _summary_payload,
    make_handler,
    serve,
)
from tests.integration.test_agentic_runtime import InvestigatorFalsifierScript

ROOT = Path(__file__).resolve().parents[2]


class AbstainingUiModel:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: ModelRequest) -> ModelTurn:
        self.calls += 1
        assert request.tool_choice == "required"
        return ModelTurn(
            model="scripted-ui-agent",
            tool_calls=(
                ToolCall(
                    call_id="ui-request-human",
                    name="request_human",
                    arguments={
                        "reason": "The scripted UI run requests qualified human judgment.",
                        "evidence_ids": [],
                    },
                ),
            ),
            finish_reason="tool_calls",
            usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            elapsed_ms=1,
        )


def test_submission_summary_is_backed_by_committed_evidence() -> None:
    summary = _summary_payload(ROOT)
    report = (ROOT / "docs/SUBMISSION_REPORT.md").read_text(encoding="utf-8")

    assert summary["workbook_count"] == 16
    assert summary["hidden_cases_per_workbook"] == 48
    assert summary["baseline_e2e_srr"] == 33.333333333333336
    assert summary["advanced_e2e_srr"] == 100
    assert summary["improvement_pp"] == 66.66666666666666
    assert summary["advanced_clean_preservation"] == 100
    assert summary["advanced_hard_rate"] == 100
    assert summary["human_time_status"] == "not_measured"
    assert summary["model_api_cost_usd_per_task"] == {"baseline": 0.0, "advanced": 0.0}
    assert f"{summary['baseline_runtime_seconds']:.3f} s" in report
    assert f"{summary['advanced_runtime_seconds']:.3f} s" in report
    assert "Human time per task | Not measured | Not measured | No claim" in report


def test_agent_ui_exposes_persisted_review_evidence(tmp_path: Path) -> None:
    run_id = "agent-ui-test"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    proposal = {"schema_version": 1, "run_id": run_id, "decision": {"decision": "ABSTAIN"}}
    state = {
        "decision": {"decision": "ABSTAIN", "explanation": "Human judgment is required."},
        "citations": {
            "citation-b": {"citation_id": "citation-b", "exact_quote": "second"},
            "citation-a": {"citation_id": "citation-a", "exact_quote": "first"},
        },
        "experiments": {
            "experiment-1": {
                "experiment_id": "experiment-1",
                "actor": "audit-manager",
                "request": {"purpose": "Check a boundary."},
                "observation": {"observations": {"P6": 0.75}},
            }
        },
        "falsifier_verdict": None,
    }
    (run_dir / "proposal.json").write_text(json.dumps(proposal), encoding="utf-8")
    (run_dir / "agent-state.json").write_text(json.dumps(state), encoding="utf-8")
    result = AuditResult(
        run_id=run_id,
        method="formulawitness-agentic-manager-falsifier-v1",
        source_workbook="source.xlsx",
        source_sha256="a" * 64,
        rules_sha256="b" * 64,
        decision="ABSTAIN",
    )

    payload = _agent_review_payload(
        result,
        tmp_path,
        provider="opencode",
        model_id="big-pickle",
    )

    assert payload["proposal_hash"] == object_hash(proposal)
    assert [item["citation_id"] for item in payload["citations"]] == [
        "citation-a",
        "citation-b",
    ]
    assert payload["experiments"][0]["experiment_id"] == "experiment-1"
    assert payload["provider"] == "opencode"
    assert payload["model"] == "big-pickle"
    assert payload["downloads"] == ["agent-state.json", "proposal.json"]


def test_review_server_requires_explicit_model_and_loopback_binding() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["serve"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["demo"])
    args = build_parser().parse_args(["serve", "--provider", "opencode", "--model", "big-pickle"])
    assert args.model == "big-pickle"
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert not _is_loopback_host("0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        serve(
            ROOT,
            "0.0.0.0",
            8765,
            model=object(),  # type: ignore[arg-type]
            provider="opencode",
            model_id="big-pickle",
        )


def test_background_upload_reaper_runs_without_an_incoming_request() -> None:
    called = threading.Event()
    stop, thread = _start_upload_reaper(called.set, retention_seconds=0)
    try:
        assert called.wait(timeout=2)
    finally:
        stop.set()
        thread.join(timeout=5)


def test_server_shutdown_cleans_the_private_temporary_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_called = False
    server_closed = False

    class Runtime:
        def cleanup(self) -> None:
            nonlocal cleanup_called
            cleanup_called = True

    class Handler:
        _private_runtime = Runtime()
        _reap_expired_uploads = staticmethod(lambda: None)

    class Server:
        def __init__(self, _address: object, _handler: object):
            pass

        def serve_forever(self) -> None:
            return

        def server_close(self) -> None:
            nonlocal server_closed
            server_closed = True

    monkeypatch.setattr(ui_module, "make_handler", lambda *_args, **_kwargs: Handler)
    monkeypatch.setattr(ui_module, "ThreadingHTTPServer", Server)

    serve(
        ROOT,
        "127.0.0.1",
        8765,
        model=object(),  # type: ignore[arg-type]
        provider="scripted-provider",
        model_id="scripted-model",
    )

    assert server_closed is True
    assert cleanup_called is True


def test_public_config_and_rate_limiter_fail_closed() -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        PublicServerConfig(origin="http://demo.example")
    config = PublicServerConfig(
        origin="https://demo.example",
        max_audits_per_hour=2,
        max_audits_per_client_hour=1,
    )
    assert config.hostname == "demo.example"
    limiter = SlidingWindowRateLimiter(global_limit=2, client_limit=1, window_seconds=60)
    assert limiter.allow("client-a", now=0) == (True, 0)
    allowed, retry_after = limiter.allow("client-a", now=1)
    assert allowed is False
    assert retry_after == 59
    assert limiter.allow("client-a", now=61) == (True, 0)

    mixed_limiter = SlidingWindowRateLimiter(global_limit=3, client_limit=2, window_seconds=60)
    assert mixed_limiter.allow("client-a", now=0) == (True, 0)
    assert mixed_limiter.allow("client-b", now=20) == (True, 0)
    assert mixed_limiter.allow("client-b", now=30) == (True, 0)
    allowed, retry_after = mixed_limiter.allow("client-b", now=31)
    assert allowed is False
    assert retry_after == 49


def test_public_audit_is_same_origin_asynchronous_and_disables_browser_approval(
    tmp_path: Path,
) -> None:
    workbook_relative = Path("workbooks/mutants/M10_supplier_rebate.xlsx")
    policy_relative = Path("policies/supplier_rebate_sla_policy.pdf")
    (tmp_path / workbook_relative).parent.mkdir(parents=True)
    (tmp_path / policy_relative).parent.mkdir(parents=True)
    shutil.copy2(ROOT / workbook_relative, tmp_path / workbook_relative)
    shutil.copy2(ROOT / policy_relative, tmp_path / policy_relative)
    shutil.copytree(ROOT / "policy_packs", tmp_path / "policy_packs")
    handler = make_handler(
        tmp_path,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        public_config=PublicServerConfig(
            origin="https://demo.example",
            max_audits_per_hour=1,
            max_audits_per_client_hour=1,
        ),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def request(
        path: str, *, method: str = "GET", body: dict[str, str] | None = None
    ) -> dict[str, Any]:
        headers = {"Host": "demo.example"}
        data = None
        if body is not None:
            headers |= {"Content-Type": "application/json", "Origin": "https://demo.example"}
            data = json.dumps(body).encode("utf-8")
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers=headers,
                method=method,
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        assert request("/healthz") == {"status": "ok"}
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}/",
                headers={"Host": "demo.example"},
            ),
            timeout=10,
        ) as response:
            assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
        config = request("/api/config")
        assert config["public_demo"] is True
        assert config["browser_approval_enabled"] is False
        assert config["uploads_enabled"] is False
        assert config["runtime_label"] == "Managed private AI runtime"
        assert "provider" not in config
        assert "model" not in config
        verification = request("/api/verify", method="POST", body={"case_id": "M10"})
        assert verification["verification"]["decision"] == "FAIL"
        assert verification["verification"]["model_calls"] == 0
        queued = request("/api/audit", method="POST", body={"case_id": "M10"})
        assert queued["status"] == "queued"
        for _ in range(100):
            job = request(queued["status_url"])
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Public audit job did not finish")
        assert job["result"]["result"]["decision"] == "ABSTAIN"
        assert "scripted-provider" not in json.dumps(job)
        assert "scripted-ui-agent" not in json.dumps(job)
        assert "trajectory.jsonl" not in job["result"]["downloads"]
        run_id = job["result"]["result"]["run_id"]
        for hidden_name in ("proposal.json", "report.json", "trajectory.jsonl"):
            with pytest.raises(HTTPError) as hidden_download:
                urlopen(
                    Request(
                        f"http://127.0.0.1:{port}/download/{run_id}/{hidden_name}",
                        headers={"Host": "demo.example"},
                    ),
                    timeout=10,
                )
            assert hidden_download.value.code == 404

        bad_origin = Request(
            f"http://127.0.0.1:{port}/api/audit",
            data=json.dumps({"case_id": "M10"}).encode(),
            headers={
                "Host": "demo.example",
                "Origin": "https://evil.example",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(bad_origin, timeout=10)
        assert captured.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ui_copy_separates_agent_run_from_legacy_scorecard() -> None:
    handler_source = inspect.getsource(make_handler)
    assert "run_agentic(" in handler_source
    assert "approve_agentic_proposal(" in handler_source
    assert "run_advanced(" not in handler_source
    assert "Run AI investigation" in HTML
    assert "Run deterministic verification" in HTML
    assert "Recurring audit · 0 AI calls" in HTML
    assert "Policy Pack hash" in HTML
    assert "Test-suite hash" in HTML
    assert "Workbook-mapping hash" in HTML
    assert "Approval means an authorized interpretation" in HTML
    assert "successor version" in HTML
    assert "Independent falsifier verdict" in HTML
    assert "Legacy deterministic regression evidence" in HTML
    assert "It is not model-agent performance" in HTML
    assert HTML.index("Why ClauseGrid exists") < HTML.index("Run deterministic verification")
    assert "Review real behavior" in HTML
    assert "Publish an immutable pack" in HTML
    assert "Both reviewers attest one release hash" in HTML
    assert "this public demo is read-only" in HTML
    assert "if(v.failed_count)" in HTML
    assert "v.decision==='INCONCLUSIVE'" in HTML
    assert "Some checks could not run so no pass or fail was issued" in HTML
    assert "Audit without an LLM" in HTML
    assert "Keep every defect class" in HTML
    assert "Upload workbook + policy" in HTML
    assert "matching policy .pdf" in HTML
    assert "public, synthetic, or approved data" in HTML
    assert "Supported profile: calculation-focused .xlsx only" in HTML
    assert "Why not just use Claude?" in HTML
    assert "Claude can help once. ClauseGrid remembers the approved answer." in HTML
    assert "Yes—Claude or another model can read a policy" in HTML
    assert "AI helps draft. People own policy meaning." in HTML
    assert HTML.index("Why not just use Claude?") < HTML.index("Run deterministic verification")
    assert 'role="tab"' in HTML
    assert 'role="progressbar"' in HTML
    assert 'aria-live="polite"' in HTML
    assert "The hosted runtime is waking up. Retrying automatically" in HTML
    assert "await api('/healthz')" in HTML
    assert "const text=await response.text()" in HTML
    assert "const j=await r.json()" not in HTML


def test_agent_result_ui_is_state_aware_and_full_width() -> None:
    assert "No workbook patch has been authorized." not in HTML
    assert "The investigation stopped at a safety limit" in HTML
    assert "The proposed repair did not pass independent checks" in HTML
    assert "REPAIR REJECTED" in HTML

    assert 'class="panel approval hidden" id="approvalPanel"' in HTML
    assert "showApproval=browserApproval&&result.decision==='REPAIR'&&survived" in HTML
    assert "$('approvalPanel').classList.toggle('hidden',!showApproval)" in HTML

    assert "main{width:100%;max-width:none" in HTML
    assert ".results-grid{display:grid;grid-template-columns:1fr" in HTML
    assert ".decision-panel{position:static" in HTML
    assert ".decision-panel{position:sticky" not in HTML


def test_policy_pack_api_and_recurring_verification_never_call_model() -> None:
    class NeverCalledModel:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _request: ModelRequest) -> ModelTurn:
            self.calls += 1
            raise AssertionError("deterministic Policy Pack verification called the model")

    model = NeverCalledModel()
    handler = make_handler(
        ROOT,
        model=cast(Any, model),
        provider="must-remain-unused",
        model_id="must-remain-unused",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path: str, *, body: dict[str, object] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode()
        headers = {} if body is None else {"Content-Type": "application/json"}
        response = urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers=headers,
                method="GET" if body is None else "POST",
            ),
            timeout=15,
        )
        return cast(dict[str, Any], json.loads(response.read()))

    try:
        pack = request("/api/policy-pack")
        assert pack["state"] == "ACTIVE_DEMO"
        assert pack["model_calls_for_recurring_audit"] == 0
        assert pack["approval_scope"] == "SYNTHETIC_DEMO"

        verification = request("/api/verify", body={"case_id": "M10"})
        assert verification["verification"]["decision"] == "FAIL"
        assert verification["verification"]["model_calls"] == 0
        assert verification["verification"]["model_required"] is False
        assert verification["verification"]["policy_pack_hash"] == pack["pack_hash"]
        assert model.calls == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_stale_pack_at_startup(tmp_path: Path) -> None:
    demo_root = tmp_path / "stale-pack-root"
    shutil.copytree(ROOT / "policy_packs", demo_root / "policy_packs")
    shutil.copytree(ROOT / "policies", demo_root / "policies")
    config = demo_root / "policy_packs/supplier-rebate-sla/v1.json"
    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["approved_release_hash"] = "0" * 64
    config.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="release hash does not match"):
        make_handler(
            demo_root,
            model=cast(Any, AbstainingUiModel()),
            provider="unused",
            model_id="unused",
        )


def test_health_and_pack_endpoint_fail_closed_if_cached_pack_becomes_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = make_handler(
        ROOT,
        model=cast(Any, AbstainingUiModel()),
        provider="unused",
        model_id="unused",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def reject_pack(_pack: object) -> None:
        raise ValueError("stale pack")

    monkeypatch.setattr(ui_module, "validate_materialized_policy_pack", reject_pack)
    try:
        for path in ("/healthz", "/api/policy-pack"):
            with pytest.raises(HTTPError) as captured:
                urlopen(f"http://127.0.0.1:{port}{path}", timeout=10)
            assert captured.value.code == 503
            body = json.loads(captured.value.read())
            assert body == {"error": "Approved Policy Pack is unavailable"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_audit_endpoint_runs_model_agent_and_returns_review_pack(tmp_path: Path) -> None:
    workbook_relative = Path("workbooks/mutants/M10_supplier_rebate.xlsx")
    policy_relative = Path("policies/supplier_rebate_sla_policy.pdf")
    (tmp_path / workbook_relative).parent.mkdir(parents=True)
    (tmp_path / policy_relative).parent.mkdir(parents=True)
    shutil.copy2(ROOT / workbook_relative, tmp_path / workbook_relative)
    shutil.copy2(ROOT / policy_relative, tmp_path / policy_relative)
    shutil.copytree(ROOT / "policy_packs", tmp_path / "policy_packs")
    handler = make_handler(
        tmp_path,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    request = Request(
        f"http://127.0.0.1:{port}/api/audit",
        data=json.dumps({"case_id": "M10"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            queued = json.loads(response.read())
        assert queued["status"] == "queued"
        for _ in range(100):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                payload = job["result"]
                break
            time.sleep(0.01)
        else:
            pytest.fail("Local audit job did not finish")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["result"]["method"] == "formulawitness-agentic-manager-falsifier-v1"
    assert payload["result"]["decision"] == "ABSTAIN"
    assert payload["provider"] == "scripted-provider"
    assert payload["model"] == "scripted-ui-agent"
    assert payload["proposal_hash"]
    assert "trajectory.jsonl" in payload["downloads"]
    assert "proposal.json" in payload["downloads"]


def test_private_upload_pair_runs_against_exact_workbook_and_policy_hashes(
    tmp_path: Path,
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def raw_upload(path: str, content: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=content,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = raw_upload(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        assert staged["ready"] is False
        assert staged["workbook_sha256"] == hashlib.sha256(workbook.read_bytes()).hexdigest()

        ready = raw_upload(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        assert ready["ready"] is True
        assert ready["policy_sha256"] == hashlib.sha256(policy.read_bytes()).hexdigest()

        conflicting_request = Request(
            f"http://127.0.0.1:{port}/api/audit",
            data=json.dumps({"case_id": "M10", "upload_id": staged["upload_id"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(conflicting_request, timeout=10)
        assert captured.value.code == 400

        audit_request = Request(
            f"http://127.0.0.1:{port}/api/audit",
            data=json.dumps({"upload_id": staged["upload_id"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(audit_request, timeout=10) as response:
            queued = json.loads(response.read())
        for _ in range(100):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Uploaded audit job did not finish")

        assert job["result"]["result"]["source_sha256"] == ready["workbook_sha256"]
        assert job["result"]["result"]["rules_sha256"] == ready["policy_sha256"]
        assert list((private_root / "uploads").iterdir()) == []
        assert any((private_root / "runs").iterdir())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_duplicate_policy_attachment_cannot_untrack_a_ready_upload(tmp_path: Path) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        policy_path = f"/api/uploads/{staged['upload_id']}/policy"
        post(policy_path, policy.read_bytes(), "application/pdf")
        with pytest.raises(HTTPError) as duplicate:
            post(policy_path, policy.read_bytes(), "application/pdf")
        assert duplicate.value.code == 400

        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        assert queued["job_id"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_uncommitted_repaired_workbook_is_not_downloadable(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=artifact_root,
        configured_private_root=tmp_path / "private",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}/api/audit",
                data=json.dumps({"case_id": "M10"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        ) as response:
            queued = json.loads(response.read())
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Audit did not finish")

        run_id = job["result"]["result"]["run_id"]
        run_dir = artifact_root / run_id
        (run_dir / "repaired.xlsx").write_bytes(b"uncommitted")
        (run_dir / "report.json").write_text(
            json.dumps({"approval_hash": "0" * 64, "output_workbook": "repaired.xlsx"}),
            encoding="utf-8",
        )
        with pytest.raises(HTTPError) as download:
            urlopen(f"http://127.0.0.1:{port}/download/{run_id}/repaired.xlsx", timeout=10)
        assert download.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("tampered_file", ["workbook.xlsx", "policy.pdf"])
def test_private_upload_hash_swap_fails_before_the_model_is_called(
    tmp_path: Path, tampered_file: str
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    model = AbstainingUiModel()
    handler = make_handler(
        ROOT,
        model=model,
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        target = private_root / "uploads" / staged["upload_id"] / tampered_file
        if tampered_file == "workbook.xlsx":
            target.write_bytes((ROOT / "workbooks/mutants/M09_supplier_rebate.xlsx").read_bytes())
        else:
            target.write_bytes(b"%PDF-1.7\nchanged after preflight")

        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Hash-swapped upload did not fail closed")

        assert model.calls == 0
        assert list((private_root / "uploads").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_public_mode_rejects_private_workbook_uploads(tmp_path: Path) -> None:
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        public_config=PublicServerConfig(origin="https://demo.example"),
        configured_artifact_root=tmp_path / "artifacts",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    request = Request(
        f"http://127.0.0.1:{port}/api/uploads/workbook",
        data=b"not-used",
        headers={
            "Host": "demo.example",
            "Origin": "https://demo.example",
            "Content-Type": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        },
        method="POST",
    )
    try:
        with pytest.raises(HTTPError) as captured:
            urlopen(request, timeout=10)
        assert captured.value.code == 403
        error = json.loads(captured.value.read())
        assert error["error"] == "Workbook uploads are disabled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_public_mode_can_enable_guarded_uploads_without_disclosing_runtime_identity(
    tmp_path: Path,
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "public-uploads"
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="secret-provider",
        model_id="secret-model",
        public_config=PublicServerConfig(
            origin="https://demo.example",
            uploads_enabled=True,
        ),
        configured_artifact_root=tmp_path / "artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={
                    "Host": "demo.example",
                    "Origin": "https://demo.example",
                    "Content-Type": content_type,
                },
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    def get(path: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"Host": "demo.example"},
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        config = get("/api/config")
        assert config["uploads_enabled"] is True
        assert "provider" not in config
        assert "model" not in config
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        ready = post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        assert ready["ready"] is True
        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(100):
            job = get(queued["status_url"])
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Public uploaded audit did not finish")
        encoded = json.dumps(job)
        assert "secret-provider" not in encoded
        assert "secret-model" not in encoded
        assert "trajectory.jsonl" not in job["result"]["downloads"]
        assert list((private_root / "uploads").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_malformed_uploaded_policy_fails_as_bad_request_and_discards_workbook(
    tmp_path: Path,
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}/api/uploads/workbook",
                data=workbook.read_bytes(),
                headers={
                    "Content-Type": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                },
                method="POST",
            ),
            timeout=10,
        ) as response:
            staged = json.loads(response.read())

        malformed = Request(
            f"http://127.0.0.1:{port}/api/uploads/{staged['upload_id']}/policy",
            data=b"%PDF-1.7\nnot a valid PDF",
            headers={"Content-Type": "application/pdf"},
            method="POST",
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(malformed, timeout=10)
        assert captured.value.code == 400
        assert json.loads(captured.value.read())["error"] == (
            "Policy PDF could not be parsed safely"
        )
        assert list((private_root / "uploads").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_abandoned_pending_uploads_expire_before_capacity_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    private_root = tmp_path / "private"
    monkeypatch.setattr(ui_module, "UPLOAD_TTL_SECONDS", 0)
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def upload_workbook() -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}/api/uploads/workbook",
                data=workbook.read_bytes(),
                headers={
                    "Content-Type": (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                },
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        first = upload_workbook()
        second = upload_workbook()

        assert first["upload_id"] != second["upload_id"]
        assert {path.name for path in (private_root / "uploads").iterdir()} == {second["upload_id"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_private_upload_repair_is_retained_until_approval_then_downloadable(
    tmp_path: Path,
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=InvestigatorFalsifierScript(),
        provider="scripted-provider",
        model_id="scripted-repair-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        ready = post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Uploaded repair audit did not finish")

        review = job["result"]
        assert review["result"]["decision"] == "REPAIR"
        assert review["result"]["source_sha256"] == ready["workbook_sha256"]
        assert len(list((private_root / "uploads").iterdir())) == 1

        replay = Request(
            f"http://127.0.0.1:{port}/api/audit",
            data=json.dumps({"upload_id": staged["upload_id"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(replay, timeout=10)
        assert captured.value.code == 400
        assert "unknown or still requires" in json.loads(captured.value.read())["error"]

        approved = post(
            "/api/approve",
            json.dumps({"run_id": review["result"]["run_id"], "reviewer": "ui-reviewer"}).encode(),
            "application/json",
        )
        assert approved["result"]["approval_hash"]
        assert "repaired.xlsx" in approved["downloads"]
        assert list((private_root / "uploads").iterdir()) == []

        with urlopen(
            f"http://127.0.0.1:{port}/download/{review['result']['run_id']}/repaired.xlsx",
            timeout=10,
        ) as response:
            repaired = response.read()
        assert repaired.startswith(b"PK")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cleanup_failure_does_not_leave_uploaded_audit_job_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"

    def fail_cleanup(_upload: object) -> None:
        raise OSError("simulated locked upload")

    monkeypatch.setattr(ui_module, "remove_upload", fail_cleanup)
    handler = make_handler(
        ROOT,
        model=AbstainingUiModel(),
        provider="scripted-provider",
        model_id="scripted-ui-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] != "running" and job["status"] != "queued":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Uploaded audit remained non-terminal after cleanup failed")

        assert job["status"] == "complete"
        assert job["result"]["result"]["decision"] == "ABSTAIN"
        assert job["result"]["cleanup_pending"] is True
        assert "deletion is queued for retry" in job["result"]["cleanup_warning"]
        assert len(list((private_root / "uploads").iterdir())) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_reports_and_tracks_a_temporary_input_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=InvestigatorFalsifierScript(),
        provider="scripted-provider",
        model_id="scripted-repair-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Uploaded repair audit did not finish")
        review = job["result"]
        assert review["result"]["decision"] == "REPAIR"

        def fail_cleanup(_upload: object) -> None:
            raise OSError("simulated locked upload")

        monkeypatch.setattr(ui_module, "remove_upload", fail_cleanup)
        approved = post(
            "/api/approve",
            json.dumps({"run_id": review["result"]["run_id"], "reviewer": "ui-reviewer"}).encode(),
            "application/json",
        )

        assert approved["result"]["approval_hash"]
        assert approved["cleanup_pending"] is True
        assert "deletion is queued for retry" in approved["cleanup_warning"]
        assert len(list((private_root / "uploads").iterdir())) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_retained_uploaded_repair_expires_before_human_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workbook = ROOT / "workbooks/mutants/M10_supplier_rebate.xlsx"
    policy = ROOT / "policies/supplier_rebate_sla_policy.pdf"
    private_root = tmp_path / "private"
    handler = make_handler(
        ROOT,
        model=InvestigatorFalsifierScript(),
        provider="scripted-provider",
        model_id="scripted-repair-agent",
        configured_artifact_root=tmp_path / "benchmark-artifacts",
        configured_private_root=private_root,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])

    def post(path: str, data: bytes, content_type: str) -> dict[str, Any]:
        with urlopen(
            Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": content_type},
                method="POST",
            ),
            timeout=10,
        ) as response:
            return cast(dict[str, Any], json.loads(response.read()))

    try:
        staged = post(
            "/api/uploads/workbook",
            workbook.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        post(
            f"/api/uploads/{staged['upload_id']}/policy",
            policy.read_bytes(),
            "application/pdf",
        )
        queued = post(
            "/api/audit",
            json.dumps({"upload_id": staged["upload_id"]}).encode(),
            "application/json",
        )
        for _ in range(200):
            with urlopen(f"http://127.0.0.1:{port}{queued['status_url']}", timeout=10) as response:
                job = json.loads(response.read())
            if job["status"] == "complete":
                break
            time.sleep(0.01)
        else:
            pytest.fail("Uploaded repair audit did not finish")

        review = job["result"]
        assert review["result"]["decision"] == "REPAIR"
        assert len(list((private_root / "uploads").iterdir())) == 1

        monkeypatch.setattr(ui_module, "UPLOAD_TTL_SECONDS", 0)
        approval = Request(
            f"http://127.0.0.1:{port}/api/approve",
            data=json.dumps(
                {"run_id": review["result"]["run_id"], "reviewer": "ui-reviewer"}
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as captured:
            urlopen(approval, timeout=10)
        assert captured.value.code == 400
        assert json.loads(captured.value.read())["error"] == (
            "Uploaded audit input is no longer available"
        )
        assert list((private_root / "uploads").iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
