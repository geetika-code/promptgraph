"""Workflow audit (deterministic lint + optional LLM) and prompt revision suggestions."""
import json
import re
from typing import Dict, List, Optional

from . import guardrails as guard, llm, prompts
from .engine import FALLBACK_LABELS, routing_labels
from .models import Workflow

STOP = set("a an the to of and or for in on with by at from as be is are it its this that your their any all "
           "always never do not don't dont must should make sure customer user ensure only if when then than "
           "can will would also so such into out up".split())
NEG = re.compile(r"\b(never|do not|don't|must not|should not|avoid|cannot|can't)\b", re.I)
POS = re.compile(r"\b(always|must|make sure|ensure)\b", re.I)


def sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def key_tokens(s: str) -> set:
    toks = re.findall(r"[a-z]+", s.lower())
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in STOP and len(t) > 2}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def heuristic_audit(w: Workflow) -> List[dict]:
    findings: List[dict] = []
    sources = ([("(global)", "Global rules", w.instructions)]
               + [("(global)", "Guardrails", g.rule) for g in w.guardrails]
               + [(n.id, n.label, n.prompt) for n in w.nodes])
    negatives = [(sid, lbl, s, key_tokens(s)) for sid, lbl, text in sources for s in sentences(text)
                 if NEG.search(s)]
    for n in w.nodes:
        for s in sentences(n.prompt):
            if NEG.search(s) or not POS.search(s):
                continue
            toks = key_tokens(s)
            clashes = [(lbl, neg) for sid, lbl, neg, nt in negatives if sid != n.id and toks & nt]
            if clashes:
                where = "; ".join(f'{lbl}: "{neg}"' for lbl, neg in clashes[:3])
                findings.append({"node_id": n.id, "severity": "high", "category": "conflict",
                                 "title": "Contradicts other instructions", "sentence": s,
                                 "detail": f'"{s}" conflicts with {where}.', "source": "heuristic"})
        if not n.purpose.strip():
            findings.append({"node_id": n.id, "severity": "low", "category": "responsibility",
                             "title": "No stated purpose", "detail": "Add a one-line purpose so responsibilities are clear.",
                             "source": "heuristic"})
        if len(n.prompt.split()) < 6:
            findings.append({"node_id": n.id, "severity": "medium", "category": "constraints",
                             "title": "Prompt is very short", "detail": "Add explicit constraints and expected output.",
                             "source": "heuristic"})
        labels = routing_labels(w, n.id)
        if labels and not any(l in FALLBACK_LABELS for l in labels):
            findings.append({"node_id": n.id, "severity": "high", "category": "constraints",
                             "title": "Router has no fallback route",
                             "detail": f"Routes are only {', '.join(labels)}. A request that fits none of them is forced into the closest label "
                                       "and mishandled. Add an 'other' / 'escalate' route.", "source": "heuristic"})
        missing = [l for l in labels if l not in n.prompt.lower()]
        if labels and missing:
            findings.append({"node_id": n.id, "severity": "medium", "category": "constraints",
                             "title": "Router prompt omits routing labels",
                             "detail": f"Outgoing routes use {', '.join(labels)} but the prompt never mentions: {', '.join(missing)}.",
                             "source": "heuristic"})
    if not w.guardrails:
        findings.append({"node_id": w.nodes[0].id, "severity": "medium", "category": "guardrails",
                         "title": "No guardrails defined",
                         "detail": "Nothing stops this workflow from breaking domain rules (e.g. advice it should not give). Use Suggest guardrails.",
                         "source": "heuristic"})
    for i, a in enumerate(w.nodes):
        for b in w.nodes[i + 1:]:
            if jaccard(key_tokens(a.prompt), key_tokens(b.prompt)) > 0.7:
                findings.append({"node_id": b.id, "severity": "low", "category": "redundancy",
                                 "title": "Near-duplicate prompt", "detail": f"Prompt is almost identical to {a.label}.",
                                 "source": "heuristic"})
    return findings


def llm_audit(w: Workflow) -> List[dict]:
    raw = llm.complete(prompts.render("audit_system"), w.model_dump_json(exclude={"nodes": {"__all__": {"position"}}}), json_mode=True)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        items = json.loads(raw)["findings"]
    except (ValueError, KeyError, TypeError):
        raise llm.LLMError("Model returned an audit that could not be parsed as JSON.")
    ids = {n.id for n in w.nodes}
    out = []
    for f in items:
        if isinstance(f, dict) and f.get("node_id") in ids and f.get("title"):
            out.append({"node_id": f["node_id"], "severity": f.get("severity", "medium"), "category": f.get("category", "constraints"),
                        "title": str(f["title"]), "detail": str(f.get("detail", "")), "source": "llm"})
    return out


def audit(w: Workflow) -> dict:
    """Static checks always run (plain code, no model). The model audit is added when a model is reachable."""
    findings = heuristic_audit(w)
    llm_error = None
    try:
        findings += llm_audit(w)
    except llm.LLMError as exc:
        llm_error = str(exc)
    return {"findings": findings, "llm_error": llm_error}


def suggest(w: Workflow, node_id: str) -> dict:
    node = next(n for n in w.nodes if n.id == node_id)
    findings = [f for f in heuristic_audit(w) if f["node_id"] == node_id]
    user = json.dumps({"global_rules": w.instructions, "guardrails": [g.rule for g in w.guardrails],
                       "node": {"label": node.label, "purpose": node.purpose, "prompt": node.prompt},
                       "known_findings": [f["detail"] for f in findings]})
    raw = re.sub(r"^```(?:json)?|```$", "", llm.complete(prompts.render("suggest_system"), user, json_mode=True).strip(), flags=re.M).strip()
    try:
        data = json.loads(raw)
        revised, rationale = str(data["revised"]), str(data.get("rationale", ""))
    except (ValueError, KeyError, TypeError):
        raise llm.LLMError("Model returned a revision that could not be parsed as JSON.")
    return {"node_id": node_id, "original": node.prompt, "revised": revised, "rationale": rationale}
