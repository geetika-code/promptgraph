import type { ReactNode } from 'react';
import { Sparkles, Trash2 } from 'lucide-react';
import type { Suggestion, Workflow, WNode } from '../types';
import { wordDiff } from '../lib';

type Props = {
  workflow: Workflow; node: WNode | undefined; suggestion: Suggestion | null; busy: boolean;
  onUpdate: (patch: Partial<WNode>) => void; onGlobal: (text: string) => void; onEdgeCondition: (id: string, c: string) => void;
  top?: ReactNode; onRemove: () => void; onSuggest: () => void; onApply: () => void; onDismiss: () => void; onEvaluate: () => void;
};

export default function Inspector({ workflow, node, suggestion, busy, ...a }: Props) {
  const outgoing = node ? workflow.edges.filter((e) => e.source === node.id) : [];
  const showing = suggestion && node && suggestion.node_id === node.id;
  return (
    <aside className="hidden w-[360px] shrink-0 overflow-y-auto border-l border-ink-700 bg-ink-900 p-4 lg:block">
      {a.top}
      <label className="label !mt-0">Global instructions (shared by all nodes)
        <textarea className="field min-h-14" value={workflow.instructions} onChange={(e) => a.onGlobal(e.target.value)} />
      </label>
      <div className="mt-5 flex items-center justify-between border-t border-ink-700 pt-4">
        <div>
          <p className="text-[10px] tracking-[0.1em] text-slate-500">NODE INSPECTOR</p>
          <h2 className="m-0 text-[15px] font-semibold">{node?.label ?? 'No node selected'}</h2>
        </div>
        {node && <button className="btn !p-1.5 text-red-300" title="Delete node" onClick={a.onRemove}><Trash2 size={15} /></button>}
      </div>
      {node && (
        <>
          <label className="label">Name<input className="field font-sans" value={node.label} onChange={(e) => a.onUpdate({ label: e.target.value })} /></label>
          <label className="label">Purpose<input className="field font-sans" placeholder="What is this node responsible for?" value={node.purpose} onChange={(e) => a.onUpdate({ purpose: e.target.value })} /></label>
          <label className="label">Prompt
            <textarea className="field min-h-28" placeholder="Write this node's instructions…" value={node.prompt} onChange={(e) => a.onUpdate({ prompt: e.target.value })} />
          </label>
          <div className="flex gap-2">
            <label className="label w-1/2">Input schema<textarea className="field min-h-14" value={node.input_schema} onChange={(e) => a.onUpdate({ input_schema: e.target.value })} /></label>
            <label className="label w-1/2">Output schema<textarea className="field min-h-14" value={node.output_schema} onChange={(e) => a.onUpdate({ output_schema: e.target.value })} /></label>
          </div>
          <label className="label flex items-center gap-2">
            <input type="checkbox" checked={node.inherit_global} onChange={(e) => a.onUpdate({ inherit_global: e.target.checked })} /> Inherit global instructions
          </label>
          {outgoing.length > 0 && (
            <div className="mt-2">
              <p className="label !mt-0">Outgoing routes <span className="text-slate-500">(“always”, or a label this node must output)</span></p>
              {outgoing.map((e) => (
                <div key={e.id} className="mt-1 flex items-center gap-2 text-xs text-slate-400">
                  <span className="w-24 truncate">→ {workflow.nodes.find((n) => n.id === e.target)?.label}</span>
                  <input className="field !mt-0 font-sans" value={e.condition} onChange={(ev) => a.onEdgeCondition(e.id, ev.target.value)} />
                </div>
              ))}
            </div>
          )}
          <button className="btn mt-4 w-full justify-center border-[#2c7475] bg-[#17394a] text-[#84e5d3]" disabled={busy} onClick={a.onSuggest}>
            <Sparkles size={15} /> Suggest improved prompt
          </button>
          {showing && (
            <div className="mt-3 rounded-md border border-[#3b6270] bg-[#102238] p-3">
              <b>Proposed revision</b>
              <p className="my-1.5 text-slate-400">{suggestion.rationale}</p>
              <pre className="m-0 max-h-52 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed">
                {wordDiff(suggestion.original, suggestion.revised).map((p, i) =>
                  p.kind === 'same' ? <span key={i}>{p.text}</span>
                    : p.kind === 'del' ? <del key={i} className="bg-red-500/15 text-red-300">{p.text}</del>
                    : <ins key={i} className="bg-emerald-500/15 text-emerald-300 no-underline">{p.text}</ins>)}
              </pre>
              <p className="my-2 text-[11px] text-amber-300/80">{suggestion.note}</p>
              <div className="flex gap-1.5">
                <button className="btn btn-primary" disabled={busy} onClick={a.onEvaluate}>Evaluate vs. original</button>
                <button className="btn" onClick={a.onApply}>Apply</button>
                <button className="btn" onClick={a.onDismiss}>Dismiss</button>
              </div>
            </div>
          )}
        </>
      )}
    </aside>
  );
}
