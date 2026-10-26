/** TS mirror of agent.py's parsing helpers plus scripted demo sessions (no API calls). */

const CMD_RE = /<cmd>([\s\S]*?)<\/cmd>/i;

export function findCommand(text: string): string | null {
  const m = text.match(CMD_RE);
  if (!m) return null;
  const cmd = m[1].trim().replace(/^```[a-zA-Z]*\n?|\n?```$/g, '').trim();
  return cmd || null;
}

export const stripCommand = (text: string) => text.replace(/<cmd>[\s\S]*?<\/cmd>/gi, '').trim();

const RISKY: [RegExp, string][] = [
  [/\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+((\/|~|\$HOME)\/?\*?|\*)(\s|$)/, 'recursive delete of a top-level folder'],
  [/\brm\s+-[a-zA-Z]*r/, 'recursive delete'],
  [/\bmkfs|\bdd\s+if=/, 'disk write'],
  [/\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b/, 'pipes a download into a shell'],
  [/\bchmod\s+-R\s+777\b/, 'opens permissions recursively'],
];

export function riskOf(command: string): string | null {
  return RISKY.find(([re]) => re.test(command))?.[1] ?? null;
}

export interface Step {
  /** What the model says; may contain one <cmd>. */
  reply: string;
  /** Output shown if the user approves the command. */
  output?: string;
  exit?: number;
  /** Reply used instead of the next step when the user declines. */
  onDecline?: string;
}

export interface Scenario {
  id: string;
  prompt: string;
  steps: Step[];
}

export const SCENARIOS: Scenario[] = [
  {
    id: 'battery',
    prompt: 'Create a Python script named monitor.py that checks battery status and prints the result.',
    steps: [
      { reply: "I'll check that the Termux:API tool is installed first.\n<cmd>command -v termux-battery-status || pkg install -y termux-api</cmd>",
        output: '/data/data/com.termux/files/usr/bin/termux-battery-status', exit: 0 },
      { reply: "It's installed. Now I'll write monitor.py.\n<cmd>cat > monitor.py <<'EOF'\nimport json, subprocess\nraw = subprocess.run(['termux-battery-status'], capture_output=True, text=True).stdout\nb = json.loads(raw)\nprint(f\"Battery {b['percentage']}% · {b['status'].lower()} · {b['temperature']:.1f}°C\")\nEOF</cmd>",
        output: '', exit: 0 },
      { reply: 'Saved. Running it:\n<cmd>python3 monitor.py</cmd>', output: 'Battery 76% · discharging · 31.4°C', exit: 0 },
      { reply: 'Done. monitor.py prints the charge level, charging state and temperature. Run it any time with `python3 monitor.py`.' },
    ],
  },
  {
    id: 'storage',
    prompt: 'Check available storage space and RAM, and tell me if the phone is running low.',
    steps: [
      { reply: 'Checking storage and memory.\n<cmd>df -h $HOME | tail -1; free -m | head -2</cmd>',
        output: '/dev/block/dm-8   24G   21G  2.9G  88% /data\n              total        used        free      shared  buff/cache   available\nMem:           1862        1214         98          11         549         590',
        exit: 0 },
      { reply: 'Storage is 88% full (2.9 GB free) and about 590 MB of RAM is available. Storage is getting low; I can find the largest folders in your home directory.\n<cmd>du -sh $HOME/* 2>/dev/null | sort -rh | head -5</cmd>',
        output: '1.6G\t/data/data/com.termux/files/home/downloads\n412M\t/data/data/com.termux/files/home/projects\n38M\t/data/data/com.termux/files/home/.cache',
        exit: 0 },
      { reply: '`downloads` uses 1.6 GB. Clearing old files there would free the most space. RAM is fine for terminal work.' },
    ],
  },
  {
    id: 'debug',
    prompt: 'Look at the error in script.py, explain what is broken, patch it, and test-run it.',
    steps: [
      { reply: 'Running it to see the error.\n<cmd>python3 script.py</cmd>',
        output: 'Traceback (most recent call last):\n  File "script.py", line 4, in <module>\n    print("Total: " + total)\nTypeError: can only concatenate str (not "int") to str', exit: 1 },
      { reply: 'Line 4 adds a number to a string. I\'ll use an f-string instead.\n<cmd>sed -i \'s/print("Total: " + total)/print(f"Total: {total}")/\' script.py && python3 script.py</cmd>',
        output: 'Total: 42', exit: 0,
        onDecline: 'No problem. The fix is to change line 4 to `print(f"Total: {total}")`, which turns the number into text.' },
      { reply: 'Fixed: `total` is an int, so it can\'t be joined to a string with `+`. The f-string converts it, and the script now prints `Total: 42`.' },
    ],
  },
  {
    id: 'danger',
    prompt: 'Free up space fast, delete everything in my home folder.',
    steps: [
      { reply: 'That would remove all your files, projects and settings in Termux. Here is the command. Only approve it if you are sure.\n<cmd>rm -rf ~/*</cmd>',
        output: '', exit: 0,
        onDecline: "Good call. A safer start is clearing caches: `rm -rf ~/.cache/*` and `pkg clean` usually free a few hundred MB." },
      { reply: 'Your home folder is now empty.' },
    ],
  },
];
