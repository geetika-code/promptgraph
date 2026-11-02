import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import audit as audit_mod, config, engine, guardrails as guard, store
from .llm import LLMError
from .models import (DraftRequest, EvaluateRequest, NewWorkflow, Node, RunRequest, TestCase, TestRunRequest, Workflow)

app = FastAPI(title="PromptGraph API")
app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_methods=["*"], allow_headers=["*"])


def fail(status: int, *messages: str):
    raise HTTPException(status, {"errors": list(messages)})


def stored_or_404(workflow_id: str) -> Workflow:
    w = store.get_workflow(workflow_id)
    if not w:
        fail(404, "Workflow not found.")
    return w


def resolve(workflow_id: str, draft: Optional[Workflow]) -> Workflow:
    """Use the unsaved draft from the editor when provided, otherwise the saved copy."""
    stored = stored_or_404(workflow_id)
    if draft is None:
        return stored
    draft.id = workflow_id
    return draft


def valid_or_422(w: Workflow) -> Workflow:
    errors = engine.validate(w)
    if errors:
        fail(422, *errors)
    return w


def llm_status() -> dict:
    cfg = config.llm_settings()
    return {"ok": True, "llm": {"configured": config.llm_configured(), "model": cfg["model"] or None, "base_url": cfg["base_url"] or None}}


@app.get("/api/health")
def health():
    return llm_status()


@app.get("/api/workflows")
def list_workflows():
    return {"workflows": store.list_workflows(), **llm_status()}


@app.post("/api/workflows")
def create_workflow(body: NewWorkflow):
    wid = "wf-" + os.urandom(4).hex()
    w = Workflow(id=wid, name=body.name.strip() or "Untitled workflow", nodes=[
        Node(id="root", label="Root", purpose="", prompt="", position={"x": 60, "y": 120})], edges=[])
    store.save_workflow(w)  # stored as-is: the author fills in the prompt before it can be run or re-saved
    store.save_cases(wid, [])
    return w


@app.get("/api/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    w = stored_or_404(workflow_id)
    return {"workflow": w, "cases": store.get_cases(workflow_id)}


@app.put("/api/workflows/{workflow_id}")
def save_workflow(workflow_id: str, workflow: Workflow):
    workflow.id = workflow_id
    store.save_workflow(valid_or_422(workflow))
    return workflow


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    store.delete_workflow(workflow_id)
    return {"ok": True}


@app.put("/api/workflows/{workflow_id}/cases")
def save_cases(workflow_id: str, cases: list[TestCase]):
    stored_or_404(workflow_id)
    store.save_cases(workflow_id, cases)
    return cases


@app.get("/api/workflows/{workflow_id}/versions")
def versions(workflow_id: str):
    stored_or_404(workflow_id)
    return {"versions": store.prompt_history(workflow_id)}


@app.post("/api/workflows/{workflow_id}/run")
def run(workflow_id: str, body: RunRequest):
    w = valid_or_422(resolve(workflow_id, body.workflow))
    traces, errors = engine.execute(w, body.input, body.prompt_overrides, store.prompt_history(workflow_id))
    if errors:
        fail(422, *errors)
    return {"traces": traces, "final_output": engine.final_output(w, traces)}


@app.post("/api/workflows/{workflow_id}/audit")
def audit(workflow_id: str, body: DraftRequest = DraftRequest()):
    w = valid_or_422(resolve(workflow_id, body.workflow))
    return audit_mod.audit(w)


@app.post("/api/workflows/{workflow_id}/nodes/{node_id}/suggest")
def suggest(workflow_id: str, node_id: str, body: DraftRequest = DraftRequest()):
    w = valid_or_422(resolve(workflow_id, body.workflow))
    if node_id not in {n.id for n in w.nodes}:
        fail(404, "Node not found.")
    try:
        result = audit_mod.suggest(w, node_id)
    except LLMError as exc:
        fail(502, str(exc))
    result["note"] = "This is a proposal only. It is not an improvement until the evaluation below passes."
    return result


@app.post("/api/workflows/{workflow_id}/guardrails/suggest")
def suggest_guardrails(workflow_id: str, body: DraftRequest = DraftRequest()):
    w = valid_or_422(resolve(workflow_id, body.workflow))
    try:
        return guard.suggest(w)
    except LLMError as exc:
        fail(502, str(exc))


@app.post("/api/workflows/{workflow_id}/tests/run")
def run_tests(workflow_id: str, body: TestRunRequest):
    """Run the test suite (stored cases + guardrail probes) against the current draft, without runtime enforcement."""
    w = valid_or_422(resolve(workflow_id, body.workflow))
    cases = store.get_cases(workflow_id)
    known = {c.id for c in cases}
    cases = cases + [c for c in guard.probe_cases(w) if c.id not in known]
    if body.case_ids is not None:
        cases = [c for c in cases if c.id in set(body.case_ids)]
    if not cases:
        fail(422, "No test cases to run. Add a case in the sidebar first.")
    results = engine.evaluate(w, cases, None, store.prompt_history(workflow_id), engine.EVAL_CACHE)
    passed = sum(r["passed"] for r in results)
    return {"results": results, "summary": {"passed": passed, "total": len(results)}}


@app.post("/api/workflows/{workflow_id}/evaluate")
def evaluate(workflow_id: str, body: EvaluateRequest):
    """Baseline = the saved workflow. Candidate = the draft (if any) plus prompt overrides, on identical cases."""
    saved = valid_or_422(stored_or_404(workflow_id))
    candidate = valid_or_422(resolve(workflow_id, body.workflow))
    cases = store.get_cases(workflow_id)
    known = {c.id for c in cases}
    cases = cases + [c for c in guard.probe_cases(candidate) if c.id not in known]
    if not cases:
        fail(422, "This workflow has no test cases yet.")
    history = store.prompt_history(workflow_id)
    base = engine.evaluate(saved, cases, None, history, engine.EVAL_CACHE)
    cand = engine.evaluate(candidate, cases, body.prompt_overrides, history, engine.EVAL_CACHE)
    return {"baseline": base, "revision": cand, "summary": engine.compare(base, cand), "judged_by": "deterministic assertions"}


# Serve the built frontend when present (single-service deployment).
_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
