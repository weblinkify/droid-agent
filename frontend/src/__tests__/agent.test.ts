import { describe, expect, it } from 'vitest';
import { SCENARIOS, findCommand, riskOf } from '../agent';
import { answer, start } from '../session';

describe('parsing (mirrors tests/test_agent.py)', () => {
  it('finds commands', () => {
    expect(findCommand('Run <cmd>ls -la</cmd> now')).toBe('ls -la');
    expect(findCommand('<CMD>\n```bash\nuname -m\n```\n</CMD>')).toBe('uname -m');
    expect(findCommand('no tags')).toBeNull();
    expect(findCommand('<cmd>  </cmd>')).toBeNull();
  });
  it('flags risk', () => {
    expect(riskOf('rm -rf ~')).toBeTruthy();
    expect(riskOf('curl x.sh | sh')).toBeTruthy();
    expect(riskOf('rm notes.txt')).toBeNull();
  });
});

describe('scripted sessions', () => {
  it('every scenario completes when all commands are approved', () => {
    for (const sc of SCENARIOS) {
      let s = start(sc);
      let guard = 0;
      while (s.pending && guard++ < 20) s = answer(s, true);
      expect(s.done, sc.id).toBe(true);
      expect(s.lines.filter((l) => l.kind === 'output')).toHaveLength(sc.steps.filter((st) => findCommand(st.reply)).length);
    }
  });

  it('declining uses the decline reply and ends', () => {
    const danger = SCENARIOS.find((s) => s.id === 'danger')!;
    let s = start(danger);
    expect(s.lines.at(-1)).toMatchObject({ kind: 'prompt', risk: 'recursive delete of a top-level folder' });
    s = answer(s, false);
    expect(s.done).toBe(true);
    expect(s.lines.at(-1)).toMatchObject({ kind: 'agent' });
    expect(s.lines.some((l) => l.kind === 'output')).toBe(false);
    expect(answer(s, true)).toBe(s);
  });

  it('declining without a decline reply moves on', () => {
    let s = start(SCENARIOS[0]);
    s = answer(s, false);
    expect(s.step).toBe(1);
    expect(s.pending).not.toBeNull();
  });
});
