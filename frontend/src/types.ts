export type WNode = {
  id: string; label: string; purpose: string; prompt: string;
  input_schema: string; output_schema: string; inherit_global: boolean;
  position: { x: number; y: number };
};
export type WEdge = { id: string; source: string; target: string; condition: string };
export type Guardrail = {
  id: string; rule: string; forbid?: string | null; probe?: string | null; probe_require?: string | null;
  fallback?: string | null; enforce: boolean; source: string;
};
export type Workflow = { id: string; name: string; instructions: string; domain: string; guardrails: Guardrail[]; nodes: WNode[]; edges: WEdge[] };
export type GuardrailSuggestions = { guardrails: Guardrail[]; note: string };
export type Assertion = { type: 'contains' | 'not_contains' | 'regex' | 'not_regex'; value: string };
export type Case = { id: string; name: string; input: string; assertions: Assertion[] };
export type Trace = {
  node_id: string; label: string; status: 'success' | 'error' | 'skipped';
  input: string; output: string; prompt_version: number; prompt_is_draft: boolean;
  error: string | null; note?: string | null; cached: boolean; duration_ms: number;
};
export type LlmStatus = { configured: boolean; model: string | null; base_url: string | null };
export type Finding = {
  node_id: string; severity: 'high' | 'medium' | 'low'; category: string; title: string; detail: string; source: string;
};
export type Suggestion = { node_id: string; original: string; revised: string; rationale: string; note: string };
export type CaseResult = { case_id: string; name: string; passed: boolean; failed_assertions: string[]; output: string };
export type Evaluation = {
  baseline: CaseResult[]; revision: CaseResult[]; judged_by: string;
  summary: { baseline_pass_rate: number; candidate_pass_rate: number; regressions: string[]; fixes: string[]; verdict: string };
};
