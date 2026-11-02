"""Graph validation, execution, and deterministic evaluation."""
import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from . import config, guardrails as guard, llm, prompts
from .models import Node, Trace, TestCase, Workflow

ALWAYS = "always"
FALLBACK_LABELS = {"other", "misc", "miscellaneous", "general", "unknown", "escalate", "fallback", "default", "unclear"}

# Shared across evaluations. Keys contain the full prompts, so any edit changes the key and nothing goes stale.
EVAL_CACHE: Dict[tuple, str] = {}
EVAL_CACHE_MAX = 500


def label_of(condition: str) -> str:
    return condition.strip().lower()


def routing_labels(workflow: Workflow, node_id: str) -> List[str]:
    labels = []
    for e in workflow.edges:
        if e.source == node_id and label_of(e.condition) != ALWAYS and label_of(e.condition) not in labels:
            labels.append(label_of(e.condition))
    return labels


def validate(workflow: Workflow) -> List[str]:
    errors: List[str] = []
    ids = [n.id for n in workflow.nodes]
    if not ids:
        return ["Workflow needs at least one node."]
    if len(ids) > config.MAX_NODES:
        errors.append(f"Workflows are limited to {config.MAX_NODES} nodes.")
    if len(set(ids)) != len(ids) or any(not i.strip() for i in ids):
        errors.append("Node IDs must be unique and non-empty.")
    edge_ids = [e.id for e in workflow.edges]
    if len(set(edge_ids)) != len(edge_ids):
        errors.append("Edge IDs must be unique.")
    known = set(ids)
    for e in workflow.edges:
        if e.source not in known or e.target not in known:
            errors.append(f"Edge {e.id} references a missing node.")
        elif e.source == e.target:
            errors.append(f"Edge {e.id} connects a node to itself.")
        if not e.condition.strip():
            errors.append(f"Edge {e.id} has an empty condition (use 'always' or a routing label).")
    for n in workflow.nodes:
        if not n.prompt.strip():
            errors.append(f"{n.label} has an empty prompt.")
        for name, raw in (("input", n.input_schema), ("output", n.output_schema)):
            try:
                if not isinstance(json.loads(raw or "{}"), dict):
                    errors.append(f"{n.label}: {name} schema must be a JSON object.")
            except json.JSONDecodeError:
                errors.append(f"{n.label}: {name} schema is not valid JSON.")
    errors += guard.validate(workflow)
    if errors:
        return errors

    graph: Dict[str, List[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in workflow.edges:
        graph[e.source].append(e.target)
        indeg[e.target] += 1
    roots = [i for i in ids if indeg[i] == 0]
    if len(roots) != 1:
        errors.append(f"Workflow needs exactly one root node (found {len(roots)} nodes with no incoming edge).")
    order = topo_order(ids, graph, dict(indeg))
    if len(order) != len(ids):
        errors.append("Cycles are not supported.")
        return errors
    depth = {i: 1 for i in ids}
    for i in order:
        for t in graph[i]:
            depth[t] = max(depth[t], depth[i] + 1)
    if max(depth.values()) > config.MAX_DEPTH:
        errors.append(f"Graph depth exceeds the limit of {config.MAX_DEPTH}.")
    return errors


def topo_order(ids: List[str], graph: Dict[str, List[str]], indeg: Dict[str, int]) -> List[str]:
    queue = [i for i in ids if indeg[i] == 0]
    order: List[str] = []
    while queue:
        cur = queue.pop(0)
        order.append(cur)
        for t in graph[cur]:
            indeg[t] -= 1
            if indeg[t] == 0:
                queue.append(t)
    return order


def compose_prompt(workflow: Workflow, node: Node, prompt: str, labels: List[str], is_final: bool = False) -> str:
    """Explicit inheritance: global rules, guardrails and node instructions stay in separate labelled sections."""
    parts = [prompts.render("node_role_final" if is_final else "node_role_internal")]
    if node.inherit_global and workflow.instructions.strip():
        parts.append(prompts.render("global_rules_heading", rules=workflow.instructions.strip()))
    section = guard.prompt_section(workflow)  # guardrails apply to every node, whether or not it inherits global rules
    if section:
        parts.append(section)
    parts.append(prompts.render("node_instructions_heading", prompt=prompt.strip()))
    if labels:
        parts.append(prompts.render("output_labels", labels=", ".join(labels)))
    else:
        try:
            schema = json.loads(node.output_schema or "{}")
        except json.JSONDecodeError:
            schema = {}
        if schema:
            parts.append(prompts.render("output_json", schema=json.dumps(schema)))
        else:
            parts.append(prompts.render("output_length", words=config.llm_settings()["max_words"]))
    return "\n\n".join(parts)


def check_output_schema(node: Node, output: str) -> Optional[str]:
    try:
        schema = json.loads(node.output_schema or "{}")
    except json.JSONDecodeError:
        return None
    required = schema.get("required") or []
    if not schema.get("properties") and not required:
        return None
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return "Output is not valid JSON but the node declares an output schema."
    if not isinstance(data, dict):
        return "Output must be a JSON object."
    missing = [k for k in required if k not in data]
    return f"Output is missing required fields: {', '.join(missing)}" if missing else None


def normalize_route(output: str, labels: List[str]) -> Optional[str]:
    cleaned = re.sub(r"[^a-z0-9_ -]", "", output.lower()).strip()
    if cleaned in labels:
        return cleaned
    hits = [l for l in labels if re.search(r"\b" + re.escape(l) + r"\b", cleaned)]
    return hits[0] if len(hits) == 1 else None


def history_version(history: Dict[str, List[str]], node_id: str, prompt: str) -> Tuple[int, bool]:
    prompts = history.get(node_id, [])
    if prompt in prompts:
        return prompts.index(prompt) + 1, False
    return len(prompts) + 1, True


def execute(
    workflow: Workflow,
    user_input: str,
    overrides: Optional[Dict[str, str]] = None,
    history: Optional[Dict[str, List[str]]] = None,
    cache: Optional[Dict[tuple, str]] = None,
    enforce: bool = True,
) -> Tuple[List[Trace], List[str]]:
    errors = validate(workflow)
    if errors:
        return [], errors
    overrides, history = overrides or {}, history or {}
    by_id = {n.id: n for n in workflow.nodes}
    ids = list(by_id)
    graph: Dict[str, List[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in workflow.edges:
        graph[e.source].append(e.target)
        indeg[e.target] += 1
    order = topo_order(ids, graph, dict(indeg))
    outputs: Dict[str, str] = {}
    chosen: Dict[str, Optional[str]] = {}
    failed: Dict[str, str] = {}
    traces: List[Trace] = []
    started = time.monotonic()

    for nid in order:
        node = by_id[nid]
        prompt = overrides.get(nid, node.prompt)
        version, draft = history_version(history, nid, prompt)
        incoming = [e for e in workflow.edges if e.target == nid]
        base = dict(node_id=nid, label=node.label, prompt_version=version, prompt_is_draft=draft)

        if incoming:
            active = [
                e for e in incoming
                if e.source in outputs and (label_of(e.condition) == ALWAYS or label_of(e.condition) == chosen.get(e.source))
            ]
            upstream_failed = [e.source for e in incoming if e.source in failed]
            if not active:
                reason = "upstream node failed" if upstream_failed else "no active route reaches this node"
                traces.append(Trace(status="skipped", error=reason, **base))
                if upstream_failed:
                    failed[nid] = reason
                continue
            node_input = outputs[active[0].source] if len(active) == 1 else "\n---\n".join(outputs[e.source] for e in active)
        else:
            node_input = user_input

        t0 = time.monotonic()
        labels = routing_labels(workflow, nid)
        error: Optional[str] = None
        output = ""
        hit = False
        note: Optional[str] = None
        system = user_msg = ""
        if t0 - started > config.MAX_RUN_SECONDS:
            error = f"Run exceeded {config.MAX_RUN_SECONDS}s limit."
        else:
            system = compose_prompt(workflow, node, prompt, labels, is_final=not graph[nid])
            user_msg = prompts.render("node_user_message", request=user_input, upstream=node_input)
            key = (config.llm_settings()["model"], system, user_msg)
            try:
                if cache is not None and key in cache:
                    output, hit = cache[key], True
                else:
                    output = llm.complete(system, user_msg)
                    if cache is not None and len(cache) < EVAL_CACHE_MAX:
                        cache[key] = output
                if not labels:
                    error = check_output_schema(node, output)
            except llm.LLMError as exc:
                error = str(exc)
        if not error and not labels and not graph[nid] and enforce and workflow.guardrails:
            output, note = enforce_guardrails(workflow, output, system, user_msg)
        if not error and labels:
            route = normalize_route(output, labels)
            fallback = next((l for l in labels if l in FALLBACK_LABELS), None)
            if route is None and fallback:
                note = f"Router replied '{output[:60]}', which is not a valid label; used the '{fallback}' route."
                route = fallback
            if route is None:
                error = f"Router returned '{output[:60]}', which is not one of: {', '.join(labels)}"
            else:
                output = route
                chosen[nid] = route
        ms = int((time.monotonic() - t0) * 1000)
        base["cached"] = hit
        if error:
            failed[nid] = error
            traces.append(Trace(status="error", input=node_input, output=output, error=error, duration_ms=ms, **base))
        else:
            outputs[nid] = output
            traces.append(Trace(status="success", input=node_input, output=output, note=note, duration_ms=ms, **base))
    return traces, []


def enforce_guardrails(workflow: Workflow, output: str, system: str, user_msg: str) -> Tuple[str, Optional[str]]:
    """Check the user-facing reply. One rewrite attempt by the model, then a clearly labelled block notice."""
    bad = guard.violations(workflow, output)
    if not bad:
        return output, None
    names = "; ".join(g.rule[:60] for g in bad)
    try:
        retry = llm.complete(system, user_msg + prompts.render("guardrail_retry", violations=names))
        if not guard.violations(workflow, retry):
            return retry, f"Guardrail triggered ({names}). The reply was rewritten once to comply."
    except llm.LLMError:
        pass
    # No canned apology is invented here: use the guardrail's own fallback if the author wrote one, else a system notice.
    fallback = bad[0].fallback or f"[Reply blocked by guardrail: {bad[0].rule}]"
    return fallback, f"Guardrail blocked the reply ({names}). Original: {output[:140]}"


def final_output(workflow: Workflow, traces: List[Trace]) -> Optional[str]:
    sinks = {n.id for n in workflow.nodes if not any(e.source == n.id for e in workflow.edges)}
    done = [t for t in traces if t.status == "success" and t.node_id in sinks]
    return done[-1].output if done else None


def check_assertion(kind: str, value: str, text: str) -> Optional[str]:
    """Returns a failure message, or None when the assertion holds."""
    if kind == "contains":
        return None if value.lower() in text.lower() else f'expected output to contain "{value}"'
    if kind == "not_contains":
        return None if value.lower() not in text.lower() else f'output must not contain "{value}"'
    try:
        found = re.search(value, text, re.IGNORECASE)
    except re.error:
        return f"invalid regex /{value}/"
    if kind == "not_regex":
        return f"output must not match /{value}/" if found else None
    return None if found else f"output did not match /{value}/"


def evaluate(workflow: Workflow, cases: List[TestCase], overrides=None, history=None, cache=None) -> List[dict]:
    """Runs WITHOUT runtime enforcement so the score measures the prompts themselves, not the safety net."""
    results = []
    for case in cases:
        traces, errors = execute(workflow, case.input, overrides, history, cache, enforce=False)
        failures: List[str] = list(errors)
        output = final_output(workflow, traces) if traces else None
        for t in traces:
            if t.status == "error":
                failures.append(f"{t.label} failed: {t.error}")
        if output is None and not failures:
            failures.append("workflow produced no final output")
        for a in case.assertions:
            msg = check_assertion(a.type, a.value, output or "")
            if msg and output is not None:
                failures.append(msg)
        results.append({
            "case_id": case.id, "name": case.name, "passed": not failures,
            "failed_assertions": failures, "output": output or "",
        })
    return results


def compare(baseline: List[dict], candidate: List[dict]) -> dict:
    base = {r["case_id"]: r for r in baseline}
    regressions = [r["case_id"] for r in candidate if base.get(r["case_id"], {}).get("passed") and not r["passed"]]
    fixes = [r["case_id"] for r in candidate if base.get(r["case_id"]) and not base[r["case_id"]]["passed"] and r["passed"]]
    n = max(len(candidate), 1)
    b_rate = sum(r["passed"] for r in baseline) / max(len(baseline), 1)
    c_rate = sum(r["passed"] for r in candidate) / n
    if regressions:
        verdict = "regressed" if not fixes else "mixed"
    elif fixes:
        verdict = "improved"
    else:
        verdict = "no_change"
    return {"baseline_pass_rate": b_rate, "candidate_pass_rate": c_rate,
            "regressions": regressions, "fixes": fixes, "verdict": verdict}
