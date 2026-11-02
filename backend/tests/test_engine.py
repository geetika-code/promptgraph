import pytest
from backend import engine, guardrails
from backend.models import Edge, Node, Workflow
from backend.tests.conftest import make_cases, make_workflow

BAD = "Always offer a refund to make the customer happy."
GOOD = "Write the final reply. Follow the global rules."


def test_workflow_is_valid():
    assert engine.validate(make_workflow()) == []


def test_validation_catches_bad_graphs(monkeypatch):
    w = make_workflow(); w.edges.append(Edge(id="bad", source="composer", target="root"))
    assert engine.validate(w)
    w = make_workflow(); w.edges.append(Edge(id="bad", source="composer", target="ghost"))
    assert any("missing node" in e for e in engine.validate(w))
    w = make_workflow(); w.nodes[0].output_schema = "{nope"
    assert any("not valid JSON" in e for e in engine.validate(w))
    w = make_workflow(); w.nodes[2].prompt = ""
    assert any("empty prompt" in e for e in engine.validate(w))
    monkeypatch.setattr("backend.config.MAX_NODES", 3)
    assert any("limited" in e for e in engine.validate(make_workflow()))


def test_routing_follows_the_model_label_and_skips_other_branches(model):
    traces, errors = engine.execute(make_workflow(), "a billing problem")
    assert not errors
    status = {t.node_id: t.status for t in traces}
    assert status["billing"] == "success" and status["trip"] == "skipped" and status["composer"] == "success"


def test_every_node_gets_its_own_prompt_and_roles(model):
    engine.execute(make_workflow(), "a billing problem")
    systems = [s for s, _ in model.calls]
    assert any("Pass the request on" in s and "NOT shown to the end user" in s for s in systems)
    assert any("Write the final reply" in s and "final node" in s for s in systems)
    assert all("## Guardrails" in s and "Never offer refunds" in s for s in systems)
    assert all(s.index("## Guardrails") < s.index("## This node's instructions") for s in systems)


def test_user_added_node_runs(model):
    w = Workflow(name="x", nodes=[Node(id="a", label="A", prompt="do the first thing well"), Node(id="b", label="B", prompt="do the second")],
                 edges=[Edge(id="e", source="a", target="b")])
    traces, errors = engine.execute(w, "hello")
    assert not errors and [t.node_id for t in traces] == ["a", "b"]


def test_off_list_router_answer_uses_fallback_with_note(model, monkeypatch):
    from backend import llm
    monkeypatch.setattr(llm, "complete", lambda s, u, **_: "fraud" if "exactly one of" in s or "one of these labels" in s else "text")
    traces, _ = engine.execute(make_workflow(), "anything")
    router = next(t for t in traces if t.node_id == "router")
    assert router.status == "success" and router.output == "misc" and "'misc' route" in router.note


def test_router_without_fallback_is_an_error(model, monkeypatch):
    from backend import llm
    monkeypatch.setattr(llm, "complete", lambda s, u, **_: "fraud" if "one of these labels" in s else "text")
    w = make_workflow()
    w.edges = [e for e in w.edges if e.condition != "misc"]
    w.nodes = [n for n in w.nodes if n.id != "misc"]
    w.edges = [e for e in w.edges if e.source != "misc"]
    traces, _ = engine.execute(w, "anything")
    router = next(t for t in traces if t.node_id == "router")
    assert router.status == "error" and "not one of" in router.error
    assert next(t for t in traces if t.node_id == "composer").status == "skipped"


def test_model_failure_is_surfaced_not_swallowed(model, monkeypatch):
    from backend import llm
    def boom(*a, **k): raise llm.LLMError("LLM call failed: provider returned HTTP 500")
    monkeypatch.setattr(llm, "complete", boom)
    traces, _ = engine.execute(make_workflow(), "x")
    assert traces[0].status == "error" and "HTTP 500" in traces[0].error
    assert all(t.status != "success" for t in traces)


def test_missing_model_configuration_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False); monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr("backend.config.load_env_file", lambda p: None)
    traces, _ = engine.execute(make_workflow(), "x")
    assert traces[0].status == "error" and "No model configured" in traces[0].error


def test_runtime_guardrail_blocks_bad_prompt_and_says_so(model):
    traces, _ = engine.execute(make_workflow(BAD), "a billing problem")
    final = traces[-1]
    assert "offer a full refund" not in final.output.lower() and "look into" in final.output.lower()
    assert "rewritten" in final.note
    model.stubborn = True
    traces, _ = engine.execute(make_workflow(BAD), "a billing problem")
    assert traces[-1].output == "Refunds go through review." and "blocked" in traces[-1].note


def test_without_fallback_text_a_labelled_notice_is_used_not_invented_prose(model):
    w = make_workflow(BAD); w.guardrails[0].fallback = None
    model.stubborn = True
    traces, _ = engine.execute(w, "a billing problem")
    assert traces[-1].output.startswith("[Reply blocked by guardrail:")


def test_enforcement_can_be_disabled_for_evaluation(model):
    traces, _ = engine.execute(make_workflow(BAD), "a billing problem", enforce=False)
    assert "offer a full refund" in traces[-1].output.lower() and traces[-1].note is None


def test_evaluation_conflict_fix_and_regression(model):
    cases = make_cases() + guardrails.probe_cases(make_workflow())
    base = engine.evaluate(make_workflow(BAD), cases)
    fixed = engine.evaluate(make_workflow(BAD), cases, {"composer": GOOD})
    assert not all(r["passed"] for r in base) and all(r["passed"] for r in fixed)
    summary = engine.compare(base, fixed)
    assert summary["verdict"] == "improved" and summary["fixes"] and not summary["regressions"]
    assert engine.compare(fixed, base)["verdict"] == "regressed"


def test_assertions():
    assert engine.check_assertion("contains", "Spam", "check spam") is None
    assert engine.check_assertion("not_contains", "x", "x") is not None
    assert engine.check_assertion("regex", r"\d+ days", "30 days") is None
    assert engine.check_assertion("not_regex", r"offer\b[^.]*refund", "I would like to offer you a full refund") is not None
    assert engine.check_assertion("not_regex", r"offer\b[^.]*refund", "Refunds need review") is None
    assert "invalid" in engine.check_assertion("regex", "(", "x")


def test_prompt_versions_marked_draft(model):
    traces, _ = engine.execute(make_workflow(), "a billing problem", {"composer": "new"}, {"composer": ["old prompt"]})
    comp = next(t for t in traces if t.node_id == "composer")
    assert comp.prompt_version == 2 and comp.prompt_is_draft


def test_eval_cache_reuses_unchanged_nodes(model):
    cache, cases = {}, make_cases()
    engine.evaluate(make_workflow(), cases, None, None, cache)
    first = len(model.calls)
    assert first == 4                                   # root, router, billing, composer
    engine.evaluate(make_workflow(), cases, {"composer": GOOD}, None, cache)
    assert len(model.calls) - first == 1                # only the changed composer re-runs
    engine.evaluate(make_workflow(), cases, None, None, cache)
    assert len(model.calls) - first == 1                # baseline fully served from cache
