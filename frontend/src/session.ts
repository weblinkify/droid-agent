import { findCommand, riskOf, stripCommand, type Scenario } from './agent';

export type Line =
  | { kind: 'user'; text: string }
  | { kind: 'agent'; text: string }
  | { kind: 'prompt'; command: string; risk: string | null }
  | { kind: 'output'; text: string; exit: number }
  | { kind: 'info'; text: string };

export interface Session {
  scenario: Scenario;
  step: number;
  lines: Line[];
  pending: string | null;
  done: boolean;
}

/** Shows steps until one asks for a command or the scenario ends. */
function advance(s: Session): Session {
  const step = s.scenario.steps[s.step];
  if (!step) return { ...s, pending: null, done: true };
  const command = findCommand(step.reply);
  const lines: Line[] = [...s.lines, { kind: 'agent', text: stripCommand(step.reply) }];
  if (!command) return { ...s, lines, pending: null, done: true };
  return { ...s, lines: [...lines, { kind: 'prompt', command, risk: riskOf(command) }], pending: command };
}

export function start(scenario: Scenario): Session {
  return advance({ scenario, step: 0, lines: [{ kind: 'user', text: scenario.prompt }], pending: null, done: false });
}

export function answer(s: Session, approve: boolean): Session {
  if (!s.pending || s.done) return s;
  const step = s.scenario.steps[s.step];
  if (approve) {
    const lines: Line[] = [...s.lines, { kind: 'info', text: 'y' }, { kind: 'output', text: step.output ?? '', exit: step.exit ?? 0 }];
    return advance({ ...s, step: s.step + 1, lines, pending: null });
  }
  const lines: Line[] = [...s.lines, { kind: 'info', text: 'n · declined' }];
  if (step.onDecline) {
    return { ...s, lines: [...lines, { kind: 'agent', text: step.onDecline }], pending: null, done: true };
  }
  return advance({ ...s, step: s.step + 1, lines, pending: null });
}
