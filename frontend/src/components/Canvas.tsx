import { useMemo, useState } from 'react';
import ReactFlow, { Position, Background, Controls, MiniMap, applyNodeChanges, type Connection, type EdgeChange, type NodeChange } from 'reactflow';
import 'reactflow/dist/style.css';
import type { Trace, Workflow } from '../types';
import { uniqueId } from '../lib';

type Props = {
  workflow: Workflow; selected: string; traces: Trace[];
  onChange: (w: Workflow) => void; onSelect: (id: string) => void;
};

export default function Canvas({ workflow, selected, traces, onChange, onSelect }: Props) {
  // React Flow hides a node until its measured size is reported back, so keep measurements in state.
  const [dims, setDims] = useState<Record<string, { width: number; height: number }>>({});
  const status = useMemo(() => Object.fromEntries(traces.map((t) => [t.node_id, t.status])), [traces]);

  const nodes = useMemo(() => workflow.nodes.map((n) => ({
    id: n.id, position: n.position, sourcePosition: Position.Right, targetPosition: Position.Left, ...dims[n.id],
    className: [selected === n.id ? 'selected-node' : '', status[n.id] ? 'status-' + status[n.id] : ''].join(' '),
    data: { label: <div><b>{n.label}</b><small className="mt-1 block text-[10px] text-slate-400">{n.purpose}</small></div> },
  })), [workflow.nodes, selected, status, dims]);

  const edges = useMemo(() => workflow.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, label: e.condition === 'always' ? '' : e.condition,
    labelStyle: { fill: '#9fe8da', fontSize: 11 }, labelBgStyle: { fill: '#0d1626', stroke: '#2c3c53' }, labelBgPadding: [6, 3] as [number, number],
  })), [workflow.edges]);

  const onNodesChange = (changes: NodeChange[]) => {
    const measured = changes.filter((c) => c.type === 'dimensions' && c.dimensions);
    if (measured.length) {
      setDims((d) => {
        const next = { ...d };
        for (const c of measured) if (c.type === 'dimensions' && c.dimensions) next[c.id] = c.dimensions;
        return next;
      });
    }
    // Positions and deletions are written back to the workflow so they are saved and never reset.
    const moved = applyNodeChanges(changes.filter((c) => c.type === 'position'), nodes);
    const removed = changes.filter((c) => c.type === 'remove').map((c) => (c as { id: string }).id);
    onChange({
      ...workflow,
      nodes: workflow.nodes.filter((n) => !removed.includes(n.id)).map((n) => ({ ...n, position: moved.find((m) => m.id === n.id)?.position ?? n.position })),
      edges: workflow.edges.filter((e) => !removed.includes(e.source) && !removed.includes(e.target)),
    });
  };
  const onEdgesChange = (changes: EdgeChange[]) => {
    const removed = changes.filter((c) => c.type === 'remove').map((c) => (c as { id: string }).id);
    if (removed.length) onChange({ ...workflow, edges: workflow.edges.filter((e) => !removed.includes(e.id)) });
  };
  const onConnect = (c: Connection) => {
    if (!c.source || !c.target) return;
    const id = uniqueId('edge', workflow.edges.map((e) => e.id));
    onChange({ ...workflow, edges: [...workflow.edges, { id, source: c.source, target: c.target, condition: 'always' }] });
  };

  return (
    <div className="min-h-0 flex-1">
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        onConnect={onConnect} onNodeClick={(_, n) => onSelect(n.id)} fitView deleteKeyCode={['Backspace', 'Delete']}>
        <Background color="#24324a" gap={22} />
        <Controls />
        <MiniMap pannable zoomable style={{ background: '#0d1626' }} maskColor="#0b122099" nodeColor="#36506c" />
      </ReactFlow>
    </div>
  );
}
