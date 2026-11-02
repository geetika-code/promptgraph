import { describe, expect, it } from 'vitest';
import { formatAssertions, parseAssertions, passRate, uniqueId, wordDiff } from './lib';

describe('wordDiff', () => {
  it('marks removed and added words', () => {
    const d = wordDiff('Always offer a refund.', 'Never promise a refund.');
    expect(d.filter((p) => p.kind === 'del').map((p) => p.text.trim()).join(' ')).toContain('Always');
    expect(d.filter((p) => p.kind === 'add').map((p) => p.text.trim()).join(' ')).toContain('Never');
    expect(d.some((p) => p.kind === 'same' && p.text.includes('refund'))).toBe(true);
  });
  it('is all-same for identical text', () => {
    expect(wordDiff('a b', 'a b')).toEqual([{ kind: 'same', text: 'a b' }]);
  });
});

describe('assertions', () => {
  it('round-trips and ignores junk lines', () => {
    const a = parseAssertions('contains: spam\nnonsense\nnot_contains: offer a refund');
    expect(a).toHaveLength(2);
    expect(parseAssertions(formatAssertions(a))).toEqual(a);
  });
});

describe('helpers', () => {
  it('computes pass rate', () => {
    expect(passRate([{ passed: true }, { passed: false }, { passed: true }, { passed: true }])).toBe(75);
    expect(passRate([])).toBe(0);
  });
  it('generates unused ids', () => {
    expect(uniqueId('node', ['node-1', 'node-2'])).toBe('node-3');
  });
});
