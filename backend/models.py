from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    label: str
    purpose: str = ""
    prompt: str
    input_schema: str = "{}"
    output_schema: str = "{}"
    inherit_global: bool = True
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})


class Edge(BaseModel):
    id: str
    source: str
    target: str
    # "always" always follows the edge; any other value is a routing label that
    # must equal the output of the source (router) node.
    condition: str = "always"


class Guardrail(BaseModel):
    id: str
    rule: str                        # plain-language rule, injected into every node's prompt
    forbid: Optional[str] = None     # regex the final reply must NOT match (deterministic runtime check)
    probe: Optional[str] = None      # an input designed to tempt the workflow into breaking the rule
    probe_require: Optional[str] = None  # regex the reply to the probe must match
    fallback: Optional[str] = None   # safe reply shown when the rule is violated and cannot be fixed
    enforce: bool = True
    source: str = "user"             # "user" | "suggested"


class Workflow(BaseModel):
    id: str = "workflow"
    name: str
    instructions: str = "Respond accurately, safely, and concisely."
    domain: str = ""
    guardrails: List[Guardrail] = []
    nodes: List[Node]
    edges: List[Edge]


class Assertion(BaseModel):
    type: Literal["contains", "not_contains", "regex", "not_regex"]
    value: str


class TestCase(BaseModel):
    __test__ = False  # not a pytest class
    id: str
    name: str
    input: str
    assertions: List[Assertion] = []


class Trace(BaseModel):
    node_id: str
    label: str
    status: Literal["success", "error", "skipped"]
    input: str = ""
    output: str = ""
    prompt_version: int = 1
    prompt_is_draft: bool = False
    error: Optional[str] = None
    note: Optional[str] = None
    cached: bool = False
    duration_ms: int = 0


class RunRequest(BaseModel):
    input: str
    workflow: Optional[Workflow] = None
    prompt_overrides: Dict[str, str] = {}


class DraftRequest(BaseModel):
    workflow: Optional[Workflow] = None


class EvaluateRequest(BaseModel):
    workflow: Optional[Workflow] = None
    prompt_overrides: Dict[str, str] = {}


class TestRunRequest(BaseModel):
    __test__ = False
    workflow: Optional[Workflow] = None
    case_ids: Optional[List[str]] = None   # None = every case, including guardrail probes


class NewWorkflow(BaseModel):
    name: str
