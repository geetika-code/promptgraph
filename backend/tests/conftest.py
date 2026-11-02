"""Test doubles. The app itself contains no canned model output; tests script a fake model instead."""
import json
import re
import pytest
from backend import engine, llm
from backend.models import Assertion, Edge, Guardrail, Node, TestCase, Workflow

LABELS = re.compile(r"one of these labels and nothing else: (.+)")


class FakeModel:
    """A scripted stand-in for the LLM. Router nodes pick the label whose name appears in the request;
    other nodes echo the text 'REPLY[<node instructions>]' plus any directive found in the prompt."""

    def __init__(self):
        self.calls = []
        self.stubborn = False

    def __call__(self, system, user, temperature=0.0, json_mode=False):
        self.calls.append((system, user))
        if json_mode:
            return self.json_reply(system, user)
        m = LABELS.search(system)
        if m:
            labels = [x.strip() for x in m.group(1).split(",")]
            request = user.split("Original request:")[1].split("Input from upstream")[0].lower()
            return next((l for l in labels if l in request), labels[-1])
        if "broke these guardrails" in user:
            return "stubborn offer a full refund" if self.stubborn else "Sorry about that, we will look into it."
        return "We will offer a full refund." if "offer a refund" in system.lower() else "Sorry, we will look into it."


    def json_reply(self, system, user):
        if "audit multi-node" in system:
            return json.dumps({"findings": [{"node_id": "composer", "severity": "high", "category": "conflict", "title": "Model finding", "detail": "d"},
                                            {"node_id": "ghost", "severity": "low", "category": "x", "title": "Invented node", "detail": "d"}]})
        if "Rewrite one workflow-node prompt" in system:
            return json.dumps({"revised": "Write the final reply. Follow the global rules.", "rationale": "removes the conflict"})
        if "design safety guardrails" in system:
            return json.dumps({"guardrails": [
                {"rule": "Never give legal advice.", "forbid": r"\byou should sue\b", "probe": "Should I sue?", "probe_require": "lawyer",
                 "fallback": "Please ask a lawyer."},
                {"rule": "Do not provide medical advice", "forbid": ".*medical advice.*", "probe": "p",
                 "probe_require": "Of course, I will keep your information confidential. How can I assist you today?", "fallback": "f"},
                {"rule": "Bad regex rule", "forbid": "(", "probe": None, "probe_require": None, "fallback": None}]})
        return "{}"


@pytest.fixture()
def model(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://fake")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    fake = FakeModel()
    monkeypatch.setattr(llm, "complete", fake)
    engine.EVAL_CACHE.clear()
    return fake


def refund_guardrail():
    return Guardrail(id="g-refund", rule="Never offer refunds outside policy.", forbid=r"\boffer\b[^.]{0,30}\brefund",
                     probe="please refund me", probe_require="sorry|look into", fallback="Refunds go through review.")


def make_workflow(composer="Write the final reply.", guardrails=True) -> Workflow:
    return Workflow(
        id="wf", name="Support", instructions="Be truthful.", domain="customer support",
        guardrails=[refund_guardrail()] if guardrails else [],
        nodes=[
            Node(id="root", label="Root", purpose="entry", prompt="Pass the request on to the router."),
            Node(id="router", label="Router", purpose="route", prompt="Return one intent: billing, trip or misc."),
            Node(id="billing", label="Billing", purpose="payments", prompt="Explain billing problems clearly."),
            Node(id="trip", label="Trip", purpose="trips", prompt="Investigate trip problems clearly."),
            Node(id="misc", label="Misc", purpose="other", prompt="Handle anything else politely."),
            Node(id="composer", label="Composer", purpose="reply", prompt=composer),
        ],
        edges=[Edge(id="e0", source="root", target="router")]
        + [Edge(id=f"r-{t}", source="router", target=t, condition=t) for t in ("billing", "trip", "misc")]
        + [Edge(id=f"c-{t}", source=t, target="composer") for t in ("billing", "trip", "misc")],
    )


def make_cases():
    return [TestCase(id="billing", name="Billing", input="a billing problem",
                     assertions=[Assertion(type="regex", value="look into"), Assertion(type="not_regex", value=r"\boffer\b[^.]{0,30}\brefund")])]
