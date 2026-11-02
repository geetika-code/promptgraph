import { ShieldCheck, Sparkles, X } from 'lucide-react';
import type { Guardrail, GuardrailSuggestions, Workflow } from '../types';

type Props = {
  workflow: Workflow; proposals: GuardrailSuggestions | null; busy: boolean;
  onChange: (patch: Partial<Workflow>) => void; onSuggest: () => void; onClearProposals: () => void;
};

export default function GuardrailPanel({ workflow, proposals, busy, onChange, onSuggest, onClearProposals }: Props) {
  const set = (id: string, patch: Partial<Guardrail>) =>
    onChange({ guardrails: workflow.guardrails.map((g) => (g.id === id ? { ...g, ...patch } : g)) });
  const have = new Set(workflow.guardrails.map((g) => g.rule));
  const pending = (proposals?.guardrails ?? []).filter((g) => !have.has(g.rule));
  const add = (gs: Guardrail[]) => {
    const taken = new Set(workflow.guardrails.map((g) => g.id));
    onChange({ guardrails: [...workflow.guardrails, ...gs.filter((g) => !taken.has(g.id))] });
  };

  return (
    <details open className="mb-5 border-b border-ink-700 pb-4">
      <summary className="flex cursor-pointer items-center gap-1.5 text-[10px] tracking-[0.1em] text-slate-400">
        <ShieldCheck size={13} className="text-accent" /> GUARDRAILS ({workflow.guardrails.length})
      </summary>
      <label className="label">What is this workflow for? (guardrails are chosen from this)
        <input className="field font-sans" placeholder="e.g. loan advisor for a bank" value={workflow.domain} onChange={(e) => onChange({ domain: e.target.value })} />
      </label>
      <button className="btn mt-2 w-full justify-center border-[#2c7475] bg-[#17394a] text-[#84e5d3]" disabled={busy} onClick={onSuggest}>
        <Sparkles size={14} /> Suggest guardrails for this domain
      </button>

      {proposals && (
        <div className="mt-2 rounded-md border border-[#3b6270] bg-[#102238] p-2.5">
          <p className="m-0 text-[11px] text-amber-300/90">{proposals.note}</p>
          {pending.length === 0 && <p className="mb-0 mt-2 text-slate-400">Nothing new to add.</p>}
          {pending.map((g) => (
            <div key={g.id} className="mt-2 flex items-start gap-2 border-t border-ink-600 pt-2">
              <p className="m-0 flex-1 text-xs text-slate-200">{g.rule}</p>
              <button className="btn !px-2 !py-1 text-[11px]" onClick={() => add([g])}>Add</button>
            </div>
          ))}
          <div className="mt-2 flex gap-1.5">
            {pending.length > 1 && <button className="btn btn-primary !py-1" onClick={() => add(pending)}>Add all</button>}
            <button className="btn !py-1" onClick={onClearProposals}>Close</button>
          </div>
        </div>
      )}

      {workflow.guardrails.length === 0 && <p className="mb-0 mt-3 text-slate-500">No guardrails yet. Nothing stops this workflow from breaking domain rules.</p>}
      {workflow.guardrails.map((g) => (
        <div key={g.id} className="mt-2 rounded-md border border-ink-600 bg-ink-800 p-2">
          <div className="flex items-start gap-1">
            <textarea className="field !mt-0 min-h-24 font-sans" value={g.rule} onChange={(e) => set(g.id, { rule: e.target.value })} />
            <button className="btn !p-1" title="Remove guardrail" onClick={() => onChange({ guardrails: workflow.guardrails.filter((x) => x.id !== g.id) })}><X size={13} /></button>
          </div>
          {g.forbid && <p className="mb-0 mt-1.5 break-all font-mono text-[10px] text-slate-500">blocks: /{g.forbid}/</p>}
          <label className="mt-1.5 flex items-center gap-1.5 text-[11px] text-slate-400" title={g.forbid ? `Blocks replies matching /${g.forbid}/` : 'This rule has no automatic check; it is only given to the model and tested by its probe.'}>
            <input type="checkbox" checked={g.enforce && !!g.forbid} disabled={!g.forbid} onChange={(e) => set(g.id, { enforce: e.target.checked })} />
            {g.forbid ? 'Enforce on the final reply' : 'Prompt-only (no automatic check)'}
            {g.probe && <span className="ml-auto text-slate-500">+ test</span>}
          </label>
        </div>
      ))}
    </details>
  );
}
