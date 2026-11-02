import pytest
from fastapi.testclient import TestClient
from backend.llm import complete as REAL_COMPLETE   # imported before any test patches it
from backend.tests.conftest import make_cases, make_workflow

BAD = "Always offer a refund to make the customer happy."


@pytest.fixture()
def client(tmp_path, monkeypatch, model):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    from backend.main import app
    c = TestClient(app)
    w = make_workflow(BAD).model_dump()
    assert c.put("/api/workflows/wf", json=w).status_code == 200
    c.put("/api/workflows/wf/cases", json=[x.model_dump() for x in make_cases()])
    return c


def test_app_ships_with_no_workflows_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/empty.db")
    from backend.main import app
    assert TestClient(app).get("/api/workflows").json()["workflows"] == []


def test_health_reports_model_configuration(client, monkeypatch):
    h = client.get("/api/health").json()
    assert h["llm"]["configured"] and h["llm"]["model"] == "fake-model"
    monkeypatch.delenv("LLM_MODEL")
    assert client.get("/api/health").json()["llm"]["configured"] is False


def test_save_load_and_versions(client):
    d = client.get("/api/workflows/wf").json()
    assert len(d["cases"]) == 1
    w = d["workflow"]
    w["nodes"][-1]["prompt"] = "Write a helpful reply."
    assert client.put("/api/workflows/wf", json=w).status_code == 200
    v = client.get("/api/workflows/wf/versions").json()["versions"]
    assert len(v["composer"]) == 2 and len(v["root"]) == 1


def test_save_rejects_invalid_graph_and_bad_regex(client):
    w = client.get("/api/workflows/wf").json()["workflow"]
    w["edges"].append({"id": "x", "source": "composer", "target": "ghost", "condition": "always"})
    assert client.put("/api/workflows/wf", json=w).status_code == 422
    w = client.get("/api/workflows/wf").json()["workflow"]
    w["guardrails"][0]["forbid"] = "("
    r = client.put("/api/workflows/wf", json=w)
    assert r.status_code == 422 and "regex" in r.text


def test_run_uses_unsaved_draft_and_reports_guardrail(client):
    r = client.post("/api/workflows/wf/run", json={"input": "a billing problem"}).json()
    assert r["traces"][-1]["note"] and "rewritten" in r["traces"][-1]["note"]
    w = client.get("/api/workflows/wf").json()["workflow"]
    w["nodes"][-1]["prompt"] = "Write the final reply."
    r = client.post("/api/workflows/wf/run", json={"input": "a billing problem", "workflow": w}).json()
    assert r["traces"][-1]["note"] is None and r["traces"][-1]["prompt_is_draft"] is True


def test_audit_combines_static_checks_and_model_findings(client):
    r = client.post("/api/workflows/wf/audit").json()
    sources = {f["source"] for f in r["findings"]}
    assert sources == {"heuristic", "llm"} and r["llm_error"] is None
    assert not any(f["node_id"] == "ghost" for f in r["findings"])          # invented node ids are dropped
    assert any(f["category"] == "conflict" and f["node_id"] == "composer" and f["source"] == "heuristic" for f in r["findings"])


def test_audit_still_returns_static_findings_when_model_is_down(client, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL")
    from backend import llm, config
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(llm.LLMError("No model configured.")))
    r = client.post("/api/workflows/wf/audit").json()
    assert r["llm_error"] == "No model configured." and any(f["source"] == "heuristic" for f in r["findings"])


def test_audit_flags_missing_guardrails_and_router_without_fallback(client):
    w = client.get("/api/workflows/wf").json()["workflow"]
    w["guardrails"] = []
    f = client.post("/api/workflows/wf/audit", json={"workflow": w}).json()["findings"]
    assert any(x["category"] == "guardrails" for x in f)
    w["edges"] = [e for e in w["edges"] if e["condition"] != "misc"]
    w["nodes"] = [n for n in w["nodes"] if n["id"] != "misc"]
    w["edges"] = [e for e in w["edges"] if e["source"] != "misc"]
    f = client.post("/api/workflows/wf/audit", json={"workflow": w}).json()["findings"]
    assert any(x["title"].startswith("Router has no fallback") for x in f)


def test_suggest_then_evaluate_with_guardrail_probes(client):
    s = client.post("/api/workflows/wf/nodes/composer/suggest").json()
    assert "Always offer a refund" not in s["revised"] and "not an improvement" in s["note"]
    e = client.post("/api/workflows/wf/evaluate", json={"prompt_overrides": {"composer": s["revised"]}}).json()
    assert e["summary"]["verdict"] == "improved" and e["summary"]["candidate_pass_rate"] == 1.0
    assert any(r["name"].startswith("Guardrail:") for r in e["revision"]) and e["judged_by"] == "deterministic assertions"


def test_suggest_guardrails_are_sanitised_and_start_disabled(client):
    r = client.post("/api/workflows/wf/guardrails/suggest").json()
    by_rule = {g["rule"]: g for g in r["guardrails"]}
    legal = by_rule["Never give legal advice."]
    assert legal["forbid"] and legal["probe_require"] == "lawyer" and legal["enforce"] is False and legal["source"] == "suggested"
    medical = by_rule["Do not provide medical advice"]
    assert medical["forbid"] is None and medical["probe_require"] is None      # untrustworthy model checks dropped
    assert by_rule["Bad regex rule"]["forbid"] is None


def test_run_test_suite_all_and_single_and_unsaved_draft(client):
    r = client.post("/api/workflows/wf/tests/run", json={}).json()
    assert r["summary"]["total"] == 2 and 0 <= r["summary"]["passed"] < 2        # 1 case + 1 guardrail probe; bad prompt fails
    one = client.post("/api/workflows/wf/tests/run", json={"case_ids": ["billing"]}).json()
    assert [x["case_id"] for x in one["results"]] == ["billing"]
    assert client.post("/api/workflows/wf/tests/run", json={"case_ids": ["nope"]}).status_code == 422
    w = client.get("/api/workflows/wf").json()["workflow"]
    w["nodes"][-1]["prompt"] = "Write the final reply."
    r = client.post("/api/workflows/wf/tests/run", json={"workflow": w}).json()
    assert r["summary"]["passed"] == r["summary"]["total"] == 2


def test_create_and_delete_workflow_starts_blank(client):
    w = client.post("/api/workflows", json={"name": "Mine"}).json()
    assert w["nodes"][0]["prompt"] == "" and w["guardrails"] == []
    assert client.delete(f"/api/workflows/{w['id']}").status_code == 200
    assert client.get(f"/api/workflows/{w['id']}").status_code == 404


def test_model_unreachable_error_reaches_the_trace(client, monkeypatch):
    from backend import llm
    monkeypatch.setattr(llm, "complete", REAL_COMPLETE)          # the real client against a dead server
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    t = client.post("/api/workflows/wf/run", json={"input": "x"}).json()["traces"][0]
    assert t["status"] == "error" and "LLM call failed" in t["error"] and "is the model server running" in t["error"]
