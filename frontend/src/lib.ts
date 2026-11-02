import type { Assertion } from './types';

export type DiffPart = { kind: 'same' | 'add' | 'del'; text: string };

/** Word-level diff (LCS) used to show original vs revised prompts. */
export function wordDiff(a: string, b: string): DiffPart[] {
  const x = a.split(/(\s+)/).filter(Boolean);
  const y = b.split(/(\s+)/).filter(Boolean);
  const dp: number[][] = Array.from({ length: x.length + 1 }, () => new Array(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i--)
    for (let j = y.length - 1; j >= 0; j--)
      dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: DiffPart[] = [];
  const push = (kind: DiffPart['kind'], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  let i = 0, j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) { push('same', x[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) push('del', x[i++]);
    else push('add', y[j++]);
  }
  while (i < x.length) push('del', x[i++]);
  while (j < y.length) push('add', y[j++]);
  return out;
}

export function parseAssertions(text: string): Assertion[] {
  const out: Assertion[] = [];
  for (const raw of text.split('\n')) {
    const m = raw.trim().match(/^(contains|not_contains|regex|not_regex)\s*:\s*(.+)$/i);
    if (m) out.push({ type: m[1].toLowerCase() as Assertion['type'], value: m[2].trim() });
  }
  return out;
}

export const formatAssertions = (a: Assertion[]) => a.map((x) => `${x.type}: ${x.value}`).join('\n');
export const passRate = (r: { passed: boolean }[]) => (r.length ? Math.round((100 * r.filter((x) => x.passed).length) / r.length) : 0);

export function uniqueId(prefix: string, taken: string[]): string {
  let n = taken.length + 1;
  while (taken.includes(`${prefix}-${n}`)) n++;
  return `${prefix}-${n}`;
}
