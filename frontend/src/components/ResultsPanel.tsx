import { AlertTriangle, CheckCircle2, MinusCircle, ShieldAlert, Sparkles, XCircle } from 'lucide-react';
import type { CaseResult, Evaluation, Finding, Trace } from '../types';
import { passRate } from '../lib';

export type Tab = 'trace' | 'audit' | 'evaluate' | 'tests';
type Props = {
  tab: Tab; setTab: (t: Tab) => void; traces: Trace[]; findings: Finding[] | null; evaluation: Evaluation | null;
  testResults: Record<string, CaseResult>; dirty: boolean;
  hasProposal: boolean; busy: boolean; onAudit: () => void; onEvaluate: () => void; onInspect: (id: string) => void;
};

const verdictText: Record<string, string> = {
  improved: 'Improved: fixes cases with no regressions.', regressed: 'Regressed: breaks cases that passed before.',
  mixed: 'Mixed: fixes some cases but breaks others.', no_change: 'No change on these test cases.',
};

export default function ResultsPanel(p: Props) {
  const tabBtn = (t: Tab, label: string, onClick = () => p.setTab(t)) => (
    <button onClick={onClick} className={`border-b-2 px-3 py-1.5 ${p.tab === t ? 'border-accent text-accent' : 'border-transparent text-slate-400'}`}>{label}</button>
  );
  return (
    <section className="h-72 shrink-0 overflow-auto border-t border-ink-700 bg-[#0e1829]">
      <nav className="sticky top-0 z-10 flex items-center gap-1 border-b border-ink-700 bg-[#0e1829] px-3 pt-1">
        {tabBtn('trace', 'Execution trace')}
        {tabBtn('audit', `Audit${p.findings ? ` (${p.findings.length})` : ''}`)}
        {tabBtn('tests', `Tests${Object.keys(p.testResults).length ? ` (${Object.values(p.testResults).filter((r) => r.passed).length}/${Object.keys(p.testResults).length})` : ''}`)}
        {tabBtn('evaluate', 'Evaluation', p.onEvaluate)}
        <button className="btn ml-auto !py-1 text-[#80e2d1]" disabled={p.busy} onClick={p.onAudit}><Sparkles size={13} /> Audit workflow</button>
      </nav>

      {p.tab === 'trace' && (
        <div className="flex gap-3 overflow-x-auto p-3">
          {p.traces.length === 0 && <p className="text-slate-500">Run the workflow to inspect each node's input, output and prompt version.</p>}
          {p.traces.map((t) => (
            <article key={t.node_id} className={`w-72 shrink-0 rounded-md border bg-[#101d31] p-3 ${t.status === 'error' ? 'border-red-500/50' : 'border-[#2a3d56]'}`}>
              <div className="flex items-center gap-1.5">
                {t.status === 'success' ? <CheckCircle2 size={15} className="text-emerald-400" /> : t.status === 'error' ? <XCircle size={15} className="text-red-400" /> : <MinusCircle size={15} className="text-slate-500" />}
                <b className="truncate">{t.label}</b>
                <span className="ml-auto font-mono text-[10px] text-slate-400" title={t.prompt_is_draft ? 'Unsaved prompt (not yet a stored version)' : 'Stored prompt version'}>
                  v{t.prompt_version}{t.prompt_is_draft ? ' draft' : ''}
                </span>
              </div>
              <p className="mb-0 mt-1 text-[10px] uppercase text-slate-500">{t.status}{t.status === 'success' ? ` · ${t.duration_ms}ms · ${t.cached ? 'cached output' : 'model output'}` : ''}</p>
              {t.error && <p className="mt-1.5 text-red-300">{t.error}</p>}
              {t.note && <p className="mt-1.5 text-amber-300">{t.note}</p>}
              {t.status !== 'skipped' && <>
                <p className="mb-0.5 mt-2 text-[10px] text-slate-500">INPUT</p>
                <p className="m-0 max-h-14 overflow-auto text-xs text-slate-400">{t.input}</p>
                <p className="mb-0.5 mt-2 text-[10px] text-slate-500">OUTPUT</p>
                <p className="m-0 max-h-20 overflow-auto text-xs text-slate-200">{t.output || '—'}</p>
              </>}
            </article>
          ))}
        </div>
      )}

      {p.tab === 'tests' && (
        <div className="flex flex-col gap-2 p-3">
          {Object.keys(p.testResults).length === 0 && <p className="text-slate-500">Use “Run all” in the sidebar (or the ▶ next to a case) to run the test suite on your current workflow, including unsaved edits.</p>}
          {Object.values(p.testResults).map((r) => (
            <article key={r.case_id} className={`rounded-md border bg-[#101d31] p-3 ${r.passed ? 'border-[#2a3d56]' : 'border-red-500/40'}`}>
              <div className="flex items-center gap-1.5">
                {r.passed ? <CheckCircle2 size={15} className="text-emerald-400" /> : <XCircle size={15} className="text-red-400" />}
                <b>{r.name}</b><span className="ml-auto text-[10px] uppercase text-slate-500">{r.passed ? 'passed' : 'failed'}</span>
              </div>
              {r.failed_assertions.map((f, i) => <p key={i} className="m-0 ml-5 mt-1 text-red-300">✗ {f}</p>)}
              <p className="m-0 ml-5 mt-1.5 text-xs text-slate-400">{r.output || '(no output)'}</p>
            </article>
          ))}
        </div>
      )}

      {p.tab === 'audit' && (
        <div className="flex flex-col gap-2 p-3">
          {p.findings === null && <p className="text-slate-500">Run an audit to find conflicting instructions, missing constraints and redundant prompts.</p>}
          {p.findings?.length === 0 && <p className="text-emerald-300">No issues found.</p>}
          {p.findings?.map((f, i) => (
            <article key={i} className="flex gap-2 rounded-md border border-[#2a3d56] bg-[#101d31] p-3">
              {f.severity === 'high' ? <ShieldAlert size={17} className="shrink-0 text-red-400" /> : <AlertTriangle size={17} className="shrink-0 text-amber-400" />}
              <div>
                <b>{f.title}</b> <em className="text-[10px] uppercase not-italic text-amber-300">{f.severity} · {f.category} · {f.source}</em>
                <p className="my-1 text-slate-400">{f.detail}</p>
                <button className="text-accent" onClick={() => p.onInspect(f.node_id)}>Inspect node →</button>
              </div>
            </article>
          ))}
        </div>
      )}

      {p.tab === 'evaluate' && (
        <div className="p-3">
          {!p.evaluation && <p className="text-slate-500">{p.hasProposal ? 'Click “Evaluate vs. original”, or the Evaluation tab, to compare.' : 'Runs every test case against the saved workflow and your current edits.'}</p>}
          {p.evaluation && (() => {
            const s = p.evaluation.summary;
            return <>
              <p className="mb-1 font-semibold">{verdictText[s.verdict]}</p>
              <p className="mt-0 text-[11px] text-slate-500">Judged by {p.evaluation.judged_by}. A rewrite is never counted as an improvement because the model says so.</p>
              <div className="flex flex-wrap gap-4">
                {(['baseline', 'revision'] as const).map((k) => (
                  <div key={k} className="min-w-72 flex-1 border-l-2 border-[#46637f] pl-3">
                    <b>{k === 'baseline' ? 'Original (saved)' : 'Candidate'}</b>{' '}
                    <span className="font-mono text-xs text-slate-400">{passRate(p.evaluation![k])}% pass</span>
                    {p.evaluation![k].map((r) => (
                      <div key={r.case_id} className="mt-1.5 text-xs">
                        <div className="flex items-center gap-1.5">
                          {r.passed ? <CheckCircle2 size={14} className="text-emerald-400" /> : <XCircle size={14} className="text-red-400" />}
                          {r.name}
                          {k === 'revision' && s.regressions.includes(r.case_id) && <span className="rounded bg-red-500/20 px-1 text-[10px] text-red-300">REGRESSION</span>}
                          {k === 'revision' && s.fixes.includes(r.case_id) && <span className="rounded bg-emerald-500/20 px-1 text-[10px] text-emerald-300">FIXED</span>}
                        </div>
                        {r.failed_assertions.map((f, i) => <div key={i} className="ml-5 text-red-300/90">✗ {f}</div>)}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </>;
          })()}
        </div>
      )}
    </section>
  );
}
