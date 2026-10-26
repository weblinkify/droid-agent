# droid-agent

**Live demo:** https://droid-agent.vercel.app (scripted replies, nothing runs) · deploys automatically on every push to `main`

An autonomous AI terminal agent for Android. It runs inside **Termux** and turns a spare or old phone
into a coding assistant. You describe a task; Gemini writes code, proposes shell commands, reads the
results and keeps going until the job is done. You approve every command with **y/n** first.

- **Python standard library only:** no `pip install`. It works on legacy 32-bit (armv7l) phones and on
  modern 64-bit ones, in under 50 MB of RAM.
- **Free:** uses the Gemini API free tier from Google AI Studio.
- **Safe by default:**
  - every command needs your approval;
  - dangerous patterns (`rm -rf ~`, `curl … | sh`, `dd`, `mkfs` …) get an extra warning;
  - commands time out (120 s by default);
  - long output is trimmed before it goes back to the model.
- **Remembers the session:** the full conversation is sent on every request, so follow-ups such as
  "now add a log file" work. Type `reset` to start over.

---

## Quick start

### 1. Install Termux

Get it from [F-Droid](https://f-droid.org/packages/com.termux/) or
[GitHub releases](https://github.com/termux/termux-app/releases). The Play Store build is outdated.

- **64-bit phones:** `arm64-v8a` APK
- **Old 32-bit phones (Android 7+):** `armeabi-v7a` APK

### 2. Set up

```bash
pkg update -y && pkg install -y git python
git clone https://github.com/weblinkify/droid-agent
cd droid-agent
```

### 3. Get a free Gemini API key

1. Open [Google AI Studio → API keys](https://aistudio.google.com/app/apikey) and click **Create API key**.
2. Choose **Create a new project**.

Don't attach a billing account to that project. A project with billing (or an empty prepaid balance)
can return `402` errors, while a fresh project uses the free tier.

### 4. Run

```bash
export GEMINI_API_KEY="paste_your_key_here"
python3 agent.py
```

To keep the key across sessions: `echo 'export GEMINI_API_KEY="..."' >> ~/.bashrc`.

---

## Using it

```text
You> Create a Python script named monitor.py that checks battery status and prints the result.
Agent: I'll check that the Termux:API tool is installed first. [command: command -v termux-battery-status || pkg install -y termux-api]
[Agent wants to run: command -v termux-battery-status || pkg install -y termux-api] Allow? (y/n) y
[exit 0]
/data/data/com.termux/files/usr/bin/termux-battery-status
Agent: Now I'll write monitor.py. …
```

Ideas:

- "Check available storage and RAM and tell me if the phone is running low."
- "Look at the error in script.py, explain what's broken, patch it and test-run it."
- "Set up a small Flask app in ~/projects/notes and start it on port 8080."

Answer `n` to decline a command, and the agent will suggest another approach. In the chat, type `reset`
to clear the conversation or `exit` to quit. Press `Ctrl+C` to stop a long-running request.

### Settings

| Environment variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | required | Your Google AI Studio key |
| `GEMINI_MODEL` | `gemini-flash-latest` | Any Gemini model your key can use, e.g. `gemini-2.5-flash` |
| `AGENT_CMD_TIMEOUT` | `120` | Seconds before a command is stopped |
| `AGENT_MAX_STEPS` | `8` | Commands per request before the agent pauses and asks you to say "continue" |

Battery, camera, SMS and similar features need the **Termux:API** app plus `pkg install termux-api`.

---

## Web demo

`frontend/` is a small React page that plays scripted sessions in a phone-shaped terminal. You approve
or decline each command, the same way you would on a phone. It makes no API calls.

```bash
cd frontend && npm install && npm run dev
```

**Vercel:** import the repo and set **Root Directory** to `frontend`.

## Development

```bash
pip install pytest
pytest -q            # the Gemini API, user input and shell runner are all faked in tests
```

## Project structure

```text
droid-agent/
├── agent.py          # the whole agent (standard library only)
├── tests/            # pytest suite
└── frontend/         # web demo (Vite + React)
```

## License

MIT
