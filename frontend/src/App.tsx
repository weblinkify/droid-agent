import { Check, Github, RotateCcw, ShieldAlert, Smartphone, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { SCENARIOS } from './agent';
import { answer, start, type Line, type Session } from './session';

function TerminalLine({ line }: { line: Line }) {
  switch (line.kind) {
    case 'user':
      return <p><span className="text-emerald-400">You&gt;</span> {line.text}</p>;
    case 'agent':
      return <p className="whitespace-pre-wrap text-sky-200"><span className="text-violet-400">Agent:</span> {line.text}</p>;
    case 'prompt':
      return (
        <div>
          {line.risk && <p className="text-amber-400">!! WARNING: this command looks dangerous ({line.risk}).</p>}
          <p className="whitespace-pre-wrap text-yellow-200">[Agent wants to run: {line.command}] Allow? (y/n)</p>
        </div>
      );
    case 'output':
      return (
        <div className="whitespace-pre-wrap text-slate-300">
          <span className={line.exit === 0 ? 'text-slate-500' : 'text-rose-400'}>[exit {line.exit}]</span>
          {line.text ? `\n${line.text}` : ''}
        </div>
      );
    case 'info':
      return <p className="text-slate-500">{line.text}</p>;
  }
}

export default function App() {
  const [session, setSession] = useState<Session>(() => start(SCENARIOS[0]));
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [session.lines.length]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-white/10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand"><Smartphone size={20} /></div>
            <div>
              <h1 className="text-lg font-bold leading-tight">droid-agent</h1>
              <p className="text-xs text-slate-400">Gemini terminal agent for Android · Termux · Python standard library only</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="chip bg-amber-400/15 text-amber-300">Demo · scripted replies</span>
            <a className="btn border border-white/15 text-slate-200 hover:bg-white/5" href="https://github.com/weblinkify/droid-agent" target="_blank" rel="noreferrer">
              <Github size={16} /> Source
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-4 py-6 lg:grid-cols-[1fr_380px]">
        <section aria-label="Demo tasks" className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Pick a task</h2>
          {SCENARIOS.map((sc) => (
            <button key={sc.id} type="button" onClick={() => setSession(start(sc))} aria-pressed={session.scenario.id === sc.id}
              className={`w-full rounded-xl border p-4 text-left transition ${session.scenario.id === sc.id ? 'border-brand bg-brand/10' : 'border-white/10 hover:bg-white/5'}`}>
              <p className="text-sm">“{sc.prompt}”</p>
            </button>
          ))}
          <div className="rounded-xl border border-white/10 p-4 text-sm text-slate-300">
            <p className="mb-2 font-semibold text-slate-100">How it works</p>
            <ol className="list-decimal space-y-1 pl-5">
              <li>You describe a task in plain language.</li>
              <li>Gemini answers and puts any shell command inside <code className="text-violet-300">&lt;cmd&gt;…&lt;/cmd&gt;</code>.</li>
              <li>You approve (y) or decline (n). Risky commands get an extra warning.</li>
              <li>The output goes back to Gemini, which continues until the task is done.</li>
            </ol>
            <p className="mt-3 text-slate-400">Runs on Android 7+ in Termux, including old 32-bit (armv7l) phones, in under 50 MB of RAM.</p>
          </div>
        </section>

        <section aria-label="Phone terminal" className="mx-auto w-full max-w-[380px]">
          <div className="rounded-[2.2rem] border-[10px] border-slate-800 bg-black shadow-2xl">
            <div className="flex items-center justify-between px-5 pt-3 text-[11px] text-slate-400">
              <span>Termux</span><span>76% ▮</span>
            </div>
            <div className="h-[460px] overflow-y-auto px-4 py-3 font-mono text-[12px] leading-relaxed" aria-live="polite">
              <p className="text-slate-500">droid-agent 1.0.0 · model gemini-flash-latest</p>
              <div className="mt-2 space-y-2">
                {session.lines.map((line, i) => <TerminalLine key={i} line={line} />)}
              </div>
              <div ref={endRef} />
            </div>
            <div className="flex gap-2 border-t border-white/10 p-3">
              {session.pending ? (
                <>
                  <button type="button" className="btn flex-1 bg-emerald-600 text-white hover:bg-emerald-500" onClick={() => setSession((s) => answer(s, true))}>
                    <Check size={15} /> y · run
                  </button>
                  <button type="button" className="btn flex-1 bg-slate-700 text-white hover:bg-slate-600" onClick={() => setSession((s) => answer(s, false))}>
                    <X size={15} /> n · decline
                  </button>
                </>
              ) : (
                <button type="button" className="btn flex-1 bg-brand text-white hover:bg-brand-dark" onClick={() => setSession(start(session.scenario))}>
                  <RotateCcw size={15} /> Replay task
                </button>
              )}
            </div>
          </div>
          {session.lines.some((l) => l.kind === 'prompt' && l.risk) && (
            <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-amber-300"><ShieldAlert size={14} /> Dangerous commands are flagged before you answer.</p>
          )}
        </section>
      </main>
      <footer className="pb-8 text-center text-xs text-slate-500">Demo replies are scripted; nothing runs. The real agent talks to the Gemini API from your phone.</footer>
    </div>
  );
}
