"""Domain guardrails: propose them (model), inject them into prompts, enforce them on the final reply, turn them into tests."""
import json
import re
from typing import List

from . import llm, prompts
from .models import Assertion, Guardrail, TestCase, Workflow

MAX_GUARDRAILS = 12


def _slug(rule: str) -> str:
    return "g-" + re.sub(r"[^a-z0-9]+", "-", rule.lower())[:24].strip("-")


def llm_suggestions(w: Workflow) -> List[dict]:
    brief = {"domain": w.domain or w.name, "global_rules": w.instructions,
             "nodes": [{"label": n.label, "purpose": n.purpose, "prompt": n.prompt} for n in w.nodes]}
    raw = re.sub(r"^```(?:json)?|```$", "", llm.complete(prompts.render("guardrails_system"), json.dumps(brief), json_mode=True).strip(), flags=re.M).strip()
    try:
        items = json.loads(raw)["guardrails"]
    except (ValueError, KeyError, TypeError):
        raise llm.LLMError("Model returned guardrails that could not be parsed as JSON.")
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and str(it.get("rule", "")).strip():
            out.append(dict(rule=str(it["rule"]).strip(), **{k: (it.get(k) or None) for k in ("forbid", "probe", "probe_require", "fallback")}))
    return out


META = re.compile(r"[\\|\[\](){}?+^$]")


def _literal(rx: str) -> str:
    """The plain text of a regex that is just a phrase (e.g. '.*medical advice.*'), else ''."""
    core = re.sub(r"^(\.\*)+|(\.\*)+$", "", rx.strip())
    return "" if META.search(core) else core.lower()


def sanitize_model_checks(g: dict) -> dict:
    """Model-written regexes are untrusted. Drop the ones that would punish compliant replies or can never match."""
    forbid, need, fallback = g.get("forbid"), g.get("probe_require"), g.get("fallback") or ""
    if forbid:
        lit = _literal(forbid)
        # A bare topic phrase also matches a good reply such as "I can't give medical advice", so it is not a violation test.
        if lit and (lit in g["rule"].lower() or len(lit.split()) <= 2) or (fallback and re.search(forbid, fallback, re.I)):
            g["forbid"] = None
    if need:
        # A whole sentence used as a regex never matches a real reply; a usable one must match the model's own safe fallback.
        if (not META.search(need) and len(need) > 40) or not fallback or not re.search(need, fallback, re.I):
            g["probe_require"] = None
    return g


def suggest(w: Workflow) -> dict:
    if not (w.domain.strip() or w.name.strip()):
        raise llm.LLMError("Describe what the workflow is for first.")
    have = {g.rule for g in w.guardrails}
    proposals: List[Guardrail] = []
    for g in llm_suggestions(w)[:MAX_GUARDRAILS]:
        if g["rule"] in have:
            continue
        for key in ("forbid", "probe_require"):
            if g.get(key):
                try:
                    re.compile(g[key])
                except re.error:
                    g[key] = None  # never hand the user a regex that cannot run
        g = sanitize_model_checks(g)
        # Model-written checks start switched off: the user reviews the regex before it can block replies.
        proposals.append(Guardrail(id=_slug(g["rule"]), source="suggested", enforce=False, **g))
    return {"guardrails": proposals,
            "note": "Proposed by the model for this domain. Review before accepting. Automatic checks are off until you enable them."}


def validate(w: Workflow) -> List[str]:
    errors, ids = [], [g.id for g in w.guardrails]
    if len(set(ids)) != len(ids):
        errors.append("Guardrail IDs must be unique.")
    for g in w.guardrails:
        if not g.rule.strip():
            errors.append("A guardrail has an empty rule.")
        for label, rx in (("forbid", g.forbid), ("probe_require", g.probe_require)):
            if rx:
                try:
                    re.compile(rx)
                except re.error:
                    errors.append(f"Guardrail '{g.rule[:30]}': {label} is not a valid regex.")
    return errors


def prompt_section(w: Workflow) -> str:
    rules = [g.rule.strip() for g in w.guardrails if g.rule.strip()]
    if not rules:
        return ""
    return prompts.render("guardrails_heading", rules="\n".join("- " + r for r in rules))


def violations(w: Workflow, text: str) -> List[Guardrail]:
    bad = []
    for g in w.guardrails:
        if g.enforce and g.forbid:
            try:
                if re.search(g.forbid, text, re.IGNORECASE):
                    bad.append(g)
            except re.error:
                pass
    return bad


def probe_cases(w: Workflow) -> List[TestCase]:
    cases = []
    for g in w.guardrails:
        if not g.probe:
            continue
        assertions = []
        if g.forbid:
            assertions.append(Assertion(type="not_regex", value=g.forbid))
        if g.probe_require:
            assertions.append(Assertion(type="regex", value=g.probe_require))
        if assertions:
            cases.append(TestCase(id="guardrail:" + g.id, name="Guardrail: " + g.rule[:48] + ("…" if len(g.rule) > 48 else ""),
                                  input=g.probe, assertions=assertions))
    return cases
