import { useCallback, useEffect, useMemo, useState } from 'react';
import { Play, Plus, Save } from 'lucide-react';
import { api } from './api';
import { uniqueId } from './lib';
import type { Case, CaseResult, Evaluation, Finding, LlmStatus, GuardrailSuggestions, Suggestion, Trace, WNode, Workflow } from './types';
import Sidebar from './components/Sidebar';
import Canvas from './components/Canvas';
import Inspector from './components/Inspector';
import GuardrailPanel from './components/GuardrailPanel';
import ResultsPanel, { type Tab } from './components/ResultsPanel';

type Notice = { kind: 'info' | 'error' | 'ok'; text: string };
type Loaded = { workflow: Workflow; cases: Case[] };

export default function App() {
  const [list, setList] = useState<{ id: string; name: string }[]>([]);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [savedJson, setSavedJson] = useState('');
  const [cases, setCases] = useState<Case[]>([]);
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [selected, setSelected] = useState('');
  const [input, setInput] = useState('');
  const [tab, setTab] = useState<Tab>('trace');
  const [traces, setTraces] = useState<Trace[]>([]);
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [testResults, setTestResults] = useState<Record<string, CaseResult>>({});
  const [proposals, setProposals] = useState<GuardrailSuggestions | null>(null);
  const [notice, setNotice] = useState<Notice>({ kind: 'info', text: 'Loading…' });
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [newName, setNewName] = useState('');

  const dirty = workflow !== null && JSON.stringify(workflow) !== savedJson;
  const current = useMemo(() => workflow?.nodes.find((n) => n.id === selected), [workflow, selected]);

  /** Runs an API action, surfacing any failure in the notice bar instead of swallowing it. */
  const guard = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e) { setNotice({ kind: 'error', text: (e as Error).message }); } finally { setBusy(false); }
  }, []);

  const load = useCallback((id: string) => guard(async () => {
    const d = await api<Loaded>(`/workflows/${id}`);
    setWorkflow(d.workflow); setSavedJson(JSON.stringify(d.workflow)); setCases(d.cases);
    setSelected(d.workflow.nodes[0]?.id ?? ''); setTraces([]); setFindings(null); setSuggestion(null); setEvaluation(null); setProposals(null); setTestResults({});
    setNotice({ kind: 'info', text: '' });
  }), [guard]);

  const refreshList = useCallback(async () => {
    const d = await api<{ workflows: { id: string; name: string }[]; llm: LlmStatus }>('/workflows');
    setList(d.workflows); setLlm(d.llm); return d.workflows;
  }, []);

  useEffect(() => { guard(async () => { const ws = await refreshList(); setNotice({ kind: 'info', text: '' }); if (ws.length) await load(ws[0].id); else setLoaded(true); }); }, [guard, refreshList, load]);

  const createWorkflow = (name: string) => guard(async () => { const w = await api<Workflow>('/workflows', { method: 'POST', body: { name } }); await refreshList(); await load(w.id); });
  if (!workflow) {
    return (
      <main className="flex h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <h1 className="m-0 text-xl font-bold"><span className="text-accent">✦</span> PromptGraph</h1>
          {!loaded ? <p className="text-slate-400">{notice.kind === 'error' ? notice.text : 'Loading…'}</p> : <>
            <p className="text-slate-400">No workflows yet. Name one to start; you write every prompt yourself.</p>
            <input className="field font-sans" autoFocus placeholder="Workflow name" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <button className="btn btn-primary mt-3" disabled={busy || !newName.trim()} onClick={() => createWorkflow(newName.trim())}>Create workflow</button>
          </>}
          {notice.kind === 'error' && loaded && <p className="text-red-300">{notice.text}</p>}
          <p className="mt-6 text-xs text-slate-500">{llm?.configured ? `Model: ${llm.model}` : 'No model configured: set LLM_BASE_URL and LLM_MODEL in .env.'}</p>
        </div>
      </main>
    );
  }
  const id = workflow.id;

  const patchNode = (patch: Partial<WNode>) => setWorkflow({ ...workflow, nodes: workflow.nodes.map((n) => (n.id === selected ? { ...n, ...patch } : n)) });
  const draftBody = { workflow };

  const save = () => guard(async () => {
    await api(`/workflows/${id}`, { method: 'PUT', body: workflow });
    setSavedJson(JSON.stringify(workflow)); await refreshList();
    setNotice({ kind: 'ok', text: 'Saved. Changed prompts were stored as new versions.' });
  });
  const run = () => guard(async () => {
    const d = await api<{ traces: Trace[] }>(`/workflows/${id}/run`, { method: 'POST', body: { input, workflow } });
    setTraces(d.traces); setTab('trace');
    const failed = d.traces.find((t) => t.status === 'error');
    setNotice(failed ? { kind: 'error', text: `${failed.label} failed: ${failed.error}` } : { kind: 'ok', text: 'Run complete.' });
  });
  const audit = () => guard(async () => {
    const d = await api<{ findings: Finding[]; llm_error: string | null }>(`/workflows/${id}/audit`, { method: 'POST', body: draftBody });
    setFindings(d.findings); setTab('audit');
    if (d.llm_error) setNotice({ kind: 'error', text: `Model audit unavailable (${d.llm_error}). Showing static checks only.` });
  });
  const suggest = () => guard(async () => setSuggestion(await api<Suggestion>(`/workflows/${id}/nodes/${selected}/suggest`, { method: 'POST', body: draftBody })));
  const runTests = (caseIds?: string[]) => guard(async () => {
    const d = await api<{ results: CaseResult[]; summary: { passed: number; total: number } }>(`/workflows/${id}/tests/run`, { method: 'POST', body: { workflow, case_ids: caseIds ?? null } });
    setTestResults((prev) => ({ ...(caseIds ? prev : {}), ...Object.fromEntries(d.results.map((r) => [r.case_id, r])) }));
    setTab('tests');
    const { passed, total } = d.summary;
    setNotice({ kind: passed === total ? 'ok' : 'error', text: `${passed} of ${total} test${total === 1 ? '' : 's'} passed.` });
  });
  const suggestGuardrails = () => guard(async () => setProposals(await api<GuardrailSuggestions>(`/workflows/${id}/guardrails/suggest`, { method: 'POST', body: draftBody })));
  const evaluate = () => guard(async () => {
    const overrides = suggestion ? { [suggestion.node_id]: suggestion.revised } : {};
    setEvaluation(await api<Evaluation>(`/workflows/${id}/evaluate`, { method: 'POST', body: { workflow, prompt_overrides: overrides } }));
    setTab('evaluate');
  });
  const saveCases = (next: Case[]) => guard(async () => { setCases(await api<Case[]>(`/workflows/${id}/cases`, { method: 'PUT', body: next })); });

  const addNode = () => {
    const nid = uniqueId('node', workflow.nodes.map((n) => n.id));
    const parent = current;
    const node: WNode = { id: nid, label: 'New node', purpose: '', prompt: '', input_schema: '{}', output_schema: '{}', inherit_global: true,
      position: parent ? { x: parent.position.x + 260, y: parent.position.y + 90 } : { x: 400, y: 400 } };
    const edges = parent ? [...workflow.edges, { id: uniqueId('edge', workflow.edges.map((e) => e.id)), source: parent.id, target: nid, condition: 'always' }] : workflow.edges;
    setWorkflow({ ...workflow, nodes: [...workflow.nodes, node], edges }); setSelected(nid);
  };
  const removeNode = () => {
    setWorkflow({ ...workflow, nodes: workflow.nodes.filter((n) => n.id !== selected), edges: workflow.edges.filter((e) => e.source !== selected && e.target !== selected) });
    setSelected('');
  };
  const noticeColor = { info: 'text-slate-400', ok: 'text-emerald-300', error: 'text-red-300' }[notice.kind];

  return (
    <main className="flex h-screen overflow-hidden">
      <Sidebar workflows={list} activeId={id} llm={llm} cases={cases} currentInput={input}
        onSelect={(wid) => { if (!dirty || window.confirm?.('Discard unsaved changes?') !== false) load(wid); }}
        onCreate={createWorkflow}
        onDeleteWorkflow={() => { if (window.confirm?.(`Delete "${workflow.name}" and its test cases?`) === false) return; guard(async () => { await api(`/workflows/${id}`, { method: 'DELETE' }); const ws = await refreshList(); if (ws.length) await load(ws[0].id); else { setWorkflow(null); setLoaded(true); } }); }}
        onUseCase={(c) => setInput(c.input)} onSaveCases={saveCases}
        results={testResults} busy={busy} onRunTests={runTests} />
      <section className="flex min-w-0 flex-1 flex-col bg-[#0d1524]">
        <header className="flex flex-wrap items-center gap-3 border-b border-ink-700 px-4 py-2.5">
          <div className="mr-auto">
            <span className="text-[11px] text-slate-500">WORKFLOW / </span><strong>{workflow.name}</strong>
            <span className={`ml-3 text-[11px] ${dirty ? 'text-amber-300' : 'text-emerald-300'}`}>● {dirty ? 'Unsaved changes' : 'Saved'}</span>
          </div>
          <input className="field !mt-0 w-72 font-sans" aria-label="Test input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Customer message to run" />
          <button className="btn" onClick={addNode}><Plus size={15} /> Node</button>
          <button className="btn" disabled={busy || !dirty} onClick={save}><Save size={15} /> Save</button>
          <button className="btn btn-primary" disabled={busy} onClick={run}><Play size={15} /> Run</button>
        </header>
        <div className={`truncate bg-ink-800 px-4 py-1.5 text-[11px] ${noticeColor}`} role="status">{notice.text}</div>
        <Canvas workflow={workflow} selected={selected} traces={traces} onChange={setWorkflow} onSelect={setSelected} />
        <ResultsPanel tab={tab} setTab={setTab} traces={traces} findings={findings} evaluation={evaluation} testResults={testResults} dirty={dirty} hasProposal={!!suggestion}
          busy={busy} onAudit={audit} onEvaluate={evaluate} onInspect={(nid) => setSelected(nid)} />
      </section>
      <Inspector top={<GuardrailPanel workflow={workflow} proposals={proposals} busy={busy} onChange={(p) => setWorkflow({ ...workflow, ...p })} onSuggest={suggestGuardrails} onClearProposals={() => setProposals(null)} />}
        workflow={workflow} node={current} suggestion={suggestion} busy={busy}
        onUpdate={patchNode} onGlobal={(t) => setWorkflow({ ...workflow, instructions: t })}
        onEdgeCondition={(eid, c) => setWorkflow({ ...workflow, edges: workflow.edges.map((e) => (e.id === eid ? { ...e, condition: c } : e)) })}
        onRemove={removeNode} onSuggest={suggest} onEvaluate={evaluate}
        onApply={() => { if (suggestion) { patchNode({ prompt: suggestion.revised }); setSuggestion(null); setNotice({ kind: 'info', text: 'Revision applied to the draft. Evaluate, then Save to store it as a new version.' }); } }}
        onDismiss={() => setSuggestion(null)} />
    </main>
  );
}
