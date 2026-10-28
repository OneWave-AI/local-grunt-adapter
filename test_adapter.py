import asyncio
import json
from pathlib import Path
import pytest
from adapter import Adapter, create_server


@pytest.fixture(autouse=True)
def quiet_panel(monkeypatch):
    monkeypatch.setenv("LOCAL_GRUNT_PANEL", "0")


@pytest.fixture
def worker(tmp_path):
    a = Adapter(state=tmp_path / "state", roots=[tmp_path / "project"])
    (tmp_path / "project").mkdir()
    a.calls = []
    def request(path, payload=None):
        a.calls.append((path, payload))
        if path == "/api/tags": return {"models": [{"name": "granite4.2:3b", "digest": "one"}]}
        if path == "/api/show": return {"capabilities": ["completion", "thinking"]}
        return {"message": {"content": '{"name":"Ada"}'}, "done_reason": "stop", "eval_count": 8}
    a.request = request
    return a


def test_loopback_only(tmp_path):
    for host in ["https://evil.com", "http://127.0.0.1.evil.com", "http://user@localhost", "http://localhost/path"]:
        with pytest.raises(ValueError): Adapter(host=host, state=tmp_path)


def test_paths_and_symlink_escape(worker, tmp_path):
    p = tmp_path / "project"
    (p / "ok.txt").write_text("hello")
    (tmp_path / "outside.txt").write_text("private")
    (p / "escape").symlink_to(tmp_path / "outside.txt")
    assert "1: hello" in worker.source("", str(p), ["ok.txt"], 100)
    for name in ["../outside.txt", "escape"]:
        with pytest.raises(ValueError): worker.source("", str(p), [name], 100)
    with pytest.raises(ValueError): worker.source("", str(tmp_path), ["outside.txt"], 100)


def test_schema_cache_and_model_digest(worker):
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    result = worker.run("extract", "Extract name", text="Ada", schema=schema)
    assert result["result"] == {"name": "Ada"}
    assert not result["cached"]
    assert worker.run("extract", "Extract name", text="Ada", schema=schema)["cached"]
    assert len([p for p, _ in worker.calls if p == "/api/chat"]) == 1
    payload = [v for p, v in worker.calls if p == "/api/chat"][0]
    assert payload["think"] is False
    assert payload["stream"] is False


def test_invalid_output_not_cached(worker):
    schema = {"type": "object", "required": ["missing"]}
    with pytest.raises(Exception): worker.run("extract", "Extract", schema=schema)
    with worker.connect() as c: assert c.execute("SELECT count(*) FROM cache").fetchone()[0] == 0


def test_bounds_missing_and_external_refs(worker):
    with pytest.raises(ValueError): worker.run("rewrite", "x", text="a" * 18001)
    with pytest.raises(ValueError): worker.run("code", "x", max_output_tokens=9999)
    with pytest.raises(ValueError): worker.run("rewrite", "x", model="missing")
    with pytest.raises(ValueError): worker.run("extract", "x", schema={"$ref": "http://example.com/schema"})


def test_truncation_and_empty_output(worker):
    original = worker.request
    for content, reason in [("partial", "length"), ("", "stop")]:
        worker.request = lambda path, payload=None: ({"message": {"content": content}, "done_reason": reason} if path == "/api/chat" else original(path, payload))
        with pytest.raises(ValueError): worker.run("rewrite", "x", cache=False)


def test_cloud_alias_rejected(worker):
    original = worker.request
    worker.request = lambda path, payload=None: ({"remote_host": "https://cloud.example"} if path == "/api/show" else original(path, payload))
    with pytest.raises(ValueError): worker.run("rewrite", "x")


def test_mcp_catalog(worker):
    tools = asyncio.run(create_server(worker).list_tools())
    assert {t.name for t in tools} == {"local_models", "local_run", "local_digest_log", "local_outcome", "local_stats", "local_cloud_usage"}


def test_mlx_schema_is_validated_without_unsupported_format(worker):
    original = worker.request
    worker.request = lambda path, payload=None: ({"capabilities": ["completion"], "details": {"runner": "mlx"}} if path == "/api/show" else original(path, payload))
    result = worker.run("extract", "name", schema={"type": "object"})
    assert result["schema_mode"] == "prompt_and_validation"
    assert "format" not in [v for p, v in worker.calls if p == "/api/chat"][0]


def test_cross_client_busy(worker):
    import fcntl
    with (worker.state / "worker.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="busy"):
            worker.run("rewrite", "x", cache=False)


def test_unicode_context_budget(worker):
    with pytest.raises(ValueError, match="UTF-8"):
        worker.run("rewrite", "x", text="😀" * 7000)


def test_cache_has_zero_new_tokens_and_separate_review_ids(worker):
    first = worker.run("extract", "name")
    second = worker.run("extract", "name")
    assert first["call_id"] != second["call_id"]
    assert second["cached"]
    assert second["local_input_tokens"] == second["local_output_tokens"] == 0
    worker.ledger.outcome(first["call_id"], "accepted")
    worker.ledger.outcome(second["call_id"], "rejected")
    stats = worker.ledger.summary()
    assert stats["local_output_tokens"] == 8
    assert stats["reviewed"] == 2 and stats["accepted"] == 1
    assert stats["acceptance_rate"] == 0.5
    assert stats["measured_cloud_tokens_saved"] is None


def test_outcomes_unknown_and_failed_calls(worker):
    with pytest.raises(ValueError): worker.ledger.outcome("missing", "accepted")
    with pytest.raises(ValueError): worker.ledger.outcome("missing", "great")
    with pytest.raises(ValueError): worker.run("extract", "name", schema={"type": "array"})
    stats = worker.ledger.summary()
    assert stats["failed"] == 1 and stats["reviewed"] == 0
    assert stats["local_output_tokens"] == 8  # failed validation still consumed inference
    with worker.ledger.connect() as c: call_id = c.execute("SELECT id FROM calls").fetchone()[0]
    with pytest.raises(ValueError): worker.ledger.outcome(call_id, "accepted")


def test_memory_guard_blocks_before_inference(worker, monkeypatch):
    monkeypatch.setattr("runtime.memory_snapshot", lambda: {"total_gib": 16, "available_gib": 0.5})
    with pytest.raises(RuntimeError, match="Memory guard"): worker.run("rewrite", "x")
    assert not any(p == "/api/chat" for p, _ in worker.calls)


def test_context_adapts_and_respects_model_limit(worker):
    from runtime import context_size
    assert context_size(500, 512) == 4096
    assert context_size(8000, 512) == 16384
    assert worker.run("rewrite", "x")["context_tokens"] == 4096
    original = worker.request
    worker.request = lambda p, payload=None: ({"model_info": {"small.context_length": 2048}} if p == "/api/show" else original(p, payload))
    with pytest.raises(ValueError, match="context window"): worker.run("rewrite", "other")


def test_auto_routes_code_to_quality(worker):
    original = worker.request
    worker.request = lambda p, payload=None: ({"models": [{"name": "granite4.2:3b", "digest": "one"}, {"name": "qwen3.5:9b", "digest": "two"}]} if p == "/api/tags" else original(p, payload))
    assert worker.run("code", "draft a function")["model"] == "qwen3.5:9b"
    assert worker.run("rewrite", "fix wording")["model"] == "granite4.2:3b"


def test_artifact_is_private_and_never_overwrites_source(worker, tmp_path):
    source = tmp_path / "project" / "data.txt"
    source.write_text("original")
    r = worker.run("rewrite", "rewrite", project_path=str(source.parent), files=[source.name], output_mode="artifact")
    artifact = Path(r["artifact"]["path"])
    assert artifact.is_relative_to(worker.state / "drafts")
    assert artifact.stat().st_mode & 0o777 == 0o600
    assert source.read_text() == "original" and "result" not in r
    again = worker.run("rewrite", "rewrite", project_path=str(source.parent), files=[source.name], output_mode="artifact")
    assert again["artifact"]["path"] != str(artifact)
    assert again["cached"] and artifact.exists()


def test_log_sampling_labels_omissions_and_preserves_tail(worker, tmp_path):
    path = tmp_path / "project" / "build.log"
    path.write_text("\x1b[32mBuild started\x1b[0m\n" + "normal intermediate output\n" * 3000 + "ERROR: dependency missing\nexit code 1\n")
    r = worker.digest_log(str(path.parent), path.name)
    assert r["log_coverage"]["sampled"] and r["log_coverage"]["omitted_lines"] > 0
    payload = [v for p, v in worker.calls if p == "/api/chat"][0]
    prompt = payload["messages"][1]["content"]
    assert "ERROR: dependency missing" in prompt and "Build started" in prompt
    assert "OMITTED" in prompt and "\x1b[32m" not in prompt
    assert r["source_mode"] == "files"


def test_json_fences_only_are_normalized(worker):
    original = worker.request
    worker.request = lambda p, payload=None: ({"message": {"content": '```json\n{"name":"Ada"}\n```'}} if p == "/api/chat" else original(p, payload))
    assert worker.run("extract", "name", schema={"type": "object"})["result"] == {"name": "Ada"}


def test_quality_memory_fallback_is_explicit_and_opt_in_by_auto(worker, monkeypatch):
    original = worker.request
    worker.request = lambda p, payload=None: ({"models": [{"name": "granite4.2:3b", "digest": "one"}, {"name": "qwen3.5:9b", "digest": "two"}]} if p == "/api/tags" else original(p, payload))
    def guard(model, *args):
        if model == "qwen3.5:9b": raise RuntimeError("Memory guard: insufficient RAM")
    monkeypatch.setattr("adapter.admit_model", guard)
    with pytest.raises(RuntimeError, match="Memory guard"):
        worker.run("code", "draft")
    result = worker.run("code", "draft", allow_smaller_model=True)
    assert result["model"] == "granite4.2:3b" and "memory guard" in result["routing_note"]
    with pytest.raises(RuntimeError, match="Memory guard"):
        worker.run("code", "draft", model="qwen3.5:9b", cache=False)


def test_loaded_model_context_growth_does_not_double_count_weights(monkeypatch):
    from runtime import admit_model, GIB
    monkeypatch.setattr("runtime.memory_snapshot", lambda: {"total_gib": 16, "available_gib": 3})
    assert admit_model("m", [{"name": "m", "size": 7*GIB}], [{"name": "m", "context_length": 4096}], 8192)


def test_log_diagnostics_preserve_a_middle_failure(worker, tmp_path):
    path = tmp_path / "project" / "middle.log"
    path.write_text("Starting\n" + "routine output\n" * 4000 + "ERROR: middle-only failure\n" + "routine output\n" * 4000 + "Completed with errors\n")
    worker.digest_log(str(path.parent), path.name)
    payload = [v for p, v in worker.calls if p == "/api/chat"][0]
    assert "4002: ERROR: middle-only failure" in payload["messages"][1]["content"]


def test_quality_cache_does_not_require_model_memory(worker, monkeypatch):
    original = worker.request
    worker.request = lambda p, payload=None: ({"models": [{"name": "qwen3.5:9b", "digest": "two"}]} if p == "/api/tags" else original(p, payload))
    worker.run("review", "review")
    monkeypatch.setattr("runtime.memory_snapshot", lambda: {"total_gib": 16, "available_gib": 0.1})
    result = worker.run("review", "review")
    assert result["cached"] and result["local_output_tokens"] == 0


def test_missing_quality_model_is_not_silently_replaced(worker):
    with pytest.raises(ValueError, match="No configured local model"):
        worker.run("review", "review")


def test_smart_gate_skips_small_tasks_without_model_calls(worker):
    r = worker.dispatch("extract", "name", text="Ada")
    assert r["decision"] == "keep_with_caller" and not r["local_inference_used"]
    assert worker.calls == []


def test_smart_gate_honors_override_and_large_file(worker, tmp_path):
    assert worker.dispatch("extract", "name", text="Ada", force_local=True)["result"]
    p = tmp_path / "project" / "large.txt"
    p.write_text("a" * 12500)
    assert worker.dispatch("summarize", "summarize", project_path=str(p.parent), files=[p.name])["decision"] == "local"


def test_feedback_blocks_poorly_performing_task(worker, tmp_path):
    p = tmp_path / "project" / "large.txt"
    p.write_text("a" * 12500)
    for _ in range(5):
        r = worker.run("summarize", "summary")
        worker.ledger.outcome(r["call_id"], "rejected")
    result = worker.dispatch("summarize", "summary", project_path=str(p.parent), files=[p.name])
    assert result["decision"] == "keep_with_caller" and "acceptance" in result["reason"]


def test_job_lifecycle_and_no_prompt_content(worker):
    result = worker.run("extract", "SECRET instruction", text="PRIVATE source", label="Extract account fields")
    job = worker.jobs.snapshot()[0]
    assert job["id"] == result["call_id"] and job["phase"] == "complete"
    assert job["label"] == "Extract account fields"
    assert "SECRET" not in json.dumps(job) and "PRIVATE" not in json.dumps(job)


def test_code_stays_with_caller_by_default(worker):
    assert worker.dispatch("code", "draft a helper")["decision"] == "keep_with_caller"


def test_panel_server_auth_and_frame(tmp_path):
    import threading
    import urllib.request
    import urllib.error
    from dashboard import create_server
    server = create_server(tmp_path, token="test-secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with pytest.raises(urllib.error.HTTPError): opener.open(base + "/panel?token=wrong")
        with opener.open(base + "/panel?token=test-secret") as r: assert b"<iframe" in r.read()
        request = urllib.request.Request(base + "/panel?token=test-secret", headers={"Origin": "https://example.test"})
        with pytest.raises(urllib.error.HTTPError): opener.open(request)
    finally: server.shutdown(); server.server_close()


def test_pii_small_file_stays_local_without_content_return(worker):
    (worker.roots[0]/'private.txt').write_text('Contact person@example.com; SSN 123-45-6789')
    result=worker.dispatch('extract','Return name',project_path=str(worker.roots[0]),files=['private.txt'])
    assert result['decision']=='local'
    assert result['privacy']['cloud_fallback_allowed'] is False
    assert 'result' not in result
    assert 'preview' not in result['artifact']
    assert 'person@example.com' not in json.dumps(result)
    assert result['cached'] is False


def test_explicit_sensitive_overrides_gate(worker):
    result=worker.dispatch('extract','Return name',text='Jane lives on Main Street',sensitive=True)
    assert result['privacy']['result_retained_locally']
    assert 'preview' not in result['artifact']


def test_private_failure_does_not_echo_source(worker):
    worker.request=lambda *args: (_ for _ in ()).throw(RuntimeError('private person@example.com'))
    with pytest.raises(RuntimeError, match='must stay local') as exc:
        worker.dispatch('extract','Return name',text='person@example.com')
    assert 'person@example.com' not in str(exc.value)


def test_pii_screen():
    from privacy import screen
    assert screen('a@example.com 123-45-6789 (212) 555-1234') == ['email','phone','us_ssn']
    assert not screen('Deployment finished successfully')


def test_sensitive_generated_output_is_not_cached(worker):
    original = worker.request
    worker.request = lambda path, payload=None: ({"message": {"content": "Contact person@example.com"}, "done_reason": "stop"} if path == "/api/chat" else original(path, payload))
    result = worker.run("rewrite", "Return a contact", text="sample")
    assert result['privacy']['result_retained_locally']
    assert 'result' not in result and 'preview' not in result['artifact']
    with worker.connect() as c:
        assert c.execute('SELECT count(*) FROM cache').fetchone()[0] == 0


def test_private_artifact_permissions_and_existing_state(worker):
    import stat
    assert stat.S_IMODE(worker.state.stat().st_mode) == 0o700
    result = worker.dispatch('rewrite', 'Return sample', text='sample', sensitive=True)
    assert stat.S_IMODE(Path(result['artifact']['path']).stat().st_mode) == 0o600


def test_dashboard_backend_refuses_redirects(tmp_path):
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from dashboard import create_server
    touched = []
    class Backend(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            touched.append(self.path)
            self.send_response(302)
            self.send_header('Location', '/redirect-target')
            self.end_headers()
    backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
    panel = create_server(tmp_path, host=f'http://127.0.0.1:{backend.server_port}')
    for srv in (backend, panel):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{panel.server_port}/api/state?token={panel.panel_token}') as response:
            data = json.load(response)
        assert data['backend_available'] is False
        assert touched == ['/api/ps']
    finally:
        for srv in (backend, panel):
            srv.shutdown(); srv.server_close()


def test_sensitive_invalid_model_output_has_generic_error(worker):
    original = worker.request
    worker.request = lambda path, payload=None: ({"message": {"content": '{"person@example.com": 1}'}, "done_reason": "stop"} if path == "/api/chat" else original(path, payload))
    with pytest.raises(RuntimeError, match="must stay local") as exc:
        worker.run('extract', 'Extract result', schema={'type': 'array'})
    assert 'person@example.com' not in str(exc.value)
    with worker.connect() as c:
        assert c.execute('SELECT count(*) FROM cache').fetchone()[0] == 0
