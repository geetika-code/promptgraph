import { useState } from 'react';
import { CheckCircle2, Play, Plus, Trash2, XCircle } from 'lucide-react';
import type { Case, CaseResult, LlmStatus } from '../types';
import { formatAssertions, parseAssertions } from '../lib';

type Props = {
  workflows: { id: string; name: string }[]; activeId: string; llm: LlmStatus | null; cases: Case[];
  onSelect: (id: string) => void; onCreate: (name: string) => void; onDeleteWorkflow: () => void;
  onUseCase: (c: Case) => void; onSaveCases: (cases: Case[]) => void; currentInput: string;
  results: Record<string, CaseResult>; busy: boolean; onRunTests: (ids?: string[]) => void;
};

export default function Sidebar(p: Props) {
  const [editing, setEditing] = useState<Case | null>(null);
  const [text, setText] = useState('');

  const startNew = () => {
    setEditing({ id: 'case-' + Date.now(), name: 'New case', input: p.currentInput, assertions: [] });
    setText('contains: ');
  };
  const commit = () => {
    if (!editing) return;
    const input = editing.input.trim();
    const named = editing.name.trim() === 'New case' && input ? (input.length > 28 ? input.slice(0, 28) + '…' : input) : editing.name;
    const next: Case = { ...editing, name: named, input, assertions: parseAssertions(text) };
    const exists = p.cases.some((c) => c.id === next.id);
    p.onSaveCases(exists ? p.cases.map((c) => (c.id === next.id ? next : c)) : [...p.cases, next]);
    setEditing(null);
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col overflow-y-auto border-r border-ink-700 bg-ink-900 p-3">
      <div className="px-2.5 pb-6 pt-1 text-lg font-bold"><span className="text-accent">✦</span> PromptGraph</div>
      <p className="caption">WORKFLOWS</p>
      {p.workflows.map((w) => (
        <button key={w.id} onClick={() => p.onSelect(w.id)}
          className={`w-full truncate rounded-md px-2.5 py-1.5 text-left ${w.id === p.activeId ? 'bg-[#173047] text-[#8de5d8]' : 'text-slate-400 hover:bg-ink-800'}`}>
          {w.name}
        </button>
      ))}
      <button className="mt-1 flex items-center gap-1.5 px-2.5 py-1.5 text-slate-400 hover:text-slate-200"
        onClick={() => { const n = window.prompt?.('Workflow name'); if (n) p.onCreate(n); }}>
        <Plus size={14} /> New workflow
      </button>
      <div className="flex gap-1 px-2.5 text-[11px] text-slate-500">
        <button className="flex items-center gap-1 hover:text-red-300" onClick={p.onDeleteWorkflow}><Trash2 size={12} /> Delete workflow</button>
      </div>

      <div className="flex items-center justify-between">
        <p className="caption">TEST SUITE</p>
        <button className="btn mr-1 mt-2 !px-2 !py-0.5 text-[11px] text-[#80e2d1]" disabled={p.busy} onClick={() => p.onRunTests()} title="Run every case, plus one test per guardrail">
          <Play size={11} /> Run all
        </button>
      </div>
      {p.cases.length === 0 && <p className="px-2.5 text-slate-500">No cases yet.</p>}
      {p.cases.map((c) => (
        <div key={c.id} className="group flex items-center rounded-md hover:bg-ink-800">
          <span className="pl-2">{p.results[c.id] ? (p.results[c.id].passed ? <CheckCircle2 size={13} className="text-emerald-400" /> : <XCircle size={13} className="text-red-400" />) : <span className="text-slate-600">□</span>}</span>
          <button className="flex-1 truncate px-2 py-1.5 text-left text-slate-300" title={c.input} onClick={() => p.onUseCase(c)}>{c.name}</button>
          <button className="px-1 text-slate-500 hover:text-[#80e2d1]" disabled={p.busy} title="Run this test" onClick={() => p.onRunTests([c.id])}><Play size={11} /></button>
          <button className="px-1 text-[10px] text-slate-500 opacity-0 hover:text-slate-200 group-hover:opacity-100" onClick={() => { setEditing(c); setText(formatAssertions(c.assertions)); }}>edit</button>
          <button className="px-1 text-slate-500 opacity-0 hover:text-red-300 group-hover:opacity-100" onClick={() => p.onSaveCases(p.cases.filter((x) => x.id !== c.id))}>×</button>
        </div>
      ))}
      <button className="mt-1 flex items-center gap-1.5 px-2.5 py-1.5 text-slate-400 hover:text-slate-200" onClick={startNew}><Plus size={14} /> Add case</button>
      {Object.values(p.results).some((r) => r.case_id.startsWith('guardrail:')) && <>
        <p className="caption">GUARDRAIL TESTS</p>
        {Object.values(p.results).filter((r) => r.case_id.startsWith('guardrail:')).map((r) => (
          <div key={r.case_id} className="flex items-start gap-1.5 px-2.5 py-1 text-xs text-slate-300" title={r.name}>
            {r.passed ? <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald-400" /> : <XCircle size={13} className="mt-0.5 shrink-0 text-red-400" />}
            <span className="line-clamp-2">{r.name.replace('Guardrail: ', '')}</span>
          </div>
        ))}
      </>}

      {editing && (
        <div className="mt-2 rounded-md border border-ink-600 bg-ink-800 p-2">
          <input className="field !mt-0 font-sans" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
          <textarea className="field min-h-14" placeholder="Customer input" value={editing.input} onChange={(e) => setEditing({ ...editing, input: e.target.value })} />
          <textarea className="field min-h-14" placeholder={'contains: text\nnot_contains: text\nregex: pattern\nnot_regex: pattern'} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex gap-1.5">
            <button className="btn btn-primary" onClick={commit}>Save case</button>
            <button className="btn" onClick={() => setEditing(null)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="mt-auto flex items-center gap-2 px-2.5 pt-4 text-slate-400">
        <span className={`h-2 w-2 shrink-0 rounded-full ${p.llm?.configured ? 'bg-emerald-400' : 'bg-red-400'}`} />
        <span className="truncate" title={p.llm?.base_url ?? ''}>{p.llm?.configured ? p.llm.model : 'No model configured'}</span>
      </div>
    </aside>
  );
}
