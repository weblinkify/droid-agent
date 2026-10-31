#!/usr/bin/env python3
"""droid-agent: an autonomous terminal agent for Android (Termux) powered by the Gemini API.

Standard library only, so it runs on old 32-bit (armv7l) phones as well as modern 64-bit ones.
The model proposes shell commands in <cmd>...</cmd> tags; you approve each one (y/n); the output goes
back to the model, and the loop continues until the task is done.

    export GEMINI_API_KEY="..."
    python3 agent.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

__version__ = "1.0.0"

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-flash-latest"
REQUEST_TIMEOUT = 60
COMMAND_TIMEOUT = int(os.environ.get("AGENT_CMD_TIMEOUT", "120"))
MAX_OUTPUT_CHARS = 6000
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "8"))
MAX_HISTORY_TURNS = 40

SYSTEM_PROMPT = """You are droid-agent, a coding and system assistant running inside Termux on an Android phone.
- To run a shell command, put exactly one command in <cmd>...</cmd>. The user approves it, then you get its output.
- For multi-line files use a heredoc inside the command, e.g. <cmd>cat > hello.py <<'EOF'\\nprint("hi")\\nEOF</cmd>.
- Use Termux paths and tools: pkg (not apt/sudo), $HOME, $PREFIX. There is no root access.
- After seeing output, continue the task or explain the result. When the task is done, reply without a <cmd> tag.
- Keep replies short. Never run destructive commands unless the user explicitly asked for them."""

CMD_RE = re.compile(r"<cmd>(.*?)</cmd>", re.DOTALL | re.IGNORECASE)

# Patterns that deserve a louder warning before the y/n prompt.
RISKY_PATTERNS = [
    (
        r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+((/|~|\$HOME)/?\*?|\*)(\s|$)",
        "recursive delete of a top-level folder",
    ),
    (r"\brm\s+-[a-zA-Z]*r", "recursive delete"),
    (r"\bmkfs|\bdd\s+if=", "disk write"),
    (r"\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b", "pipes a download into a shell"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "fork bomb"),
    (r"\bchmod\s+-R\s+777\b", "opens permissions recursively"),
    (r">\s*/dev/(sd|block)", "writes to a block device"),
]


class ApiError(RuntimeError):
    pass


def find_command(text: str) -> str | None:
    m = CMD_RE.search(text)
    if not m:
        return None
    command = m.group(1).strip()
    # Models sometimes wrap the command in a code fence inside the tag.
    command = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", command).strip()
    return command or None


def risk_of(command: str) -> str | None:
    for pattern, reason in RISKY_PATTERNS:
        if re.search(pattern, command):
            return reason
    return None


def truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return f"{text[:head]}\n... [{len(text) - limit} characters cut] ...\n{text[-tail:]}"


def run_command(command: str, timeout: int = COMMAND_TIMEOUT) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout, errors="replace"
        )
        return result.stdout or "", result.stderr or "", result.returncode
    except subprocess.TimeoutExpired as exc:
        out = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        return out, f"Command timed out after {timeout}s and was stopped.", 124


def feedback_message(command: str, stdout: str, stderr: str, code: int) -> str:
    return (
        f"Command: {command}\nExit code: {code}\n"
        f"--- stdout ---\n{truncate(stdout) or '(empty)'}\n--- stderr ---\n{truncate(stderr) or '(empty)'}"
    )


def extract_reply(data: dict[str, Any]) -> str:
    try:
        candidate = data["candidates"][0]
    except (KeyError, IndexError, TypeError):
        feedback = data.get("promptFeedback", {}) if isinstance(data, dict) else {}
        reason = feedback.get("blockReason")
        raise ApiError(
            f"No answer from the model{f' (blocked: {reason})' if reason else ''}."
        ) from None
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if not text.strip():
        raise ApiError(
            f"Empty answer from the model (finish reason: {candidate.get('finishReason', 'unknown')})."
        )
    return text


class Gemini:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        opener: Callable[..., Any] = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.api_key = api_key
        self.model = model
        self._open = opener
        self._sleep = sleep

    def generate(self, history: list[dict[str, Any]], retries: int = 3) -> str:
        payload = {
            "contents": history,
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {"temperature": 0.2},
        }
        req = urllib.request.Request(
            f"{API_ROOT}/{self.model}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        for attempt in range(retries + 1):
            try:
                with self._open(req, timeout=REQUEST_TIMEOUT) as resp:
                    return extract_reply(json.loads(resp.read().decode("utf-8")))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                    self._sleep(2**attempt * 2)
                    continue
                raise ApiError(_http_hint(exc.code, body)) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < retries:
                    self._sleep(2**attempt * 2)
                    continue
                reason = getattr(exc, "reason", exc)
                raise ApiError(f"Network error: {reason}. Check your connection.") from None
        raise ApiError("Gave up after retries.")


def _http_hint(code: int, body: str) -> str:
    try:
        message = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = body[:300]
    hints = {
        400: "Bad request. If it mentions the model, set GEMINI_MODEL to a model your key can use.",
        401: "The API key was rejected.",
        403: "The API key was rejected or the API is not enabled for its project.",
        402: "Billing problem. Create the key in a Google AI Studio project with no billing account to use the free tier.",
        404: "Model not found. Set GEMINI_MODEL, e.g. gemini-flash-latest.",
        429: "Rate limit or daily free quota reached. Wait a minute or try tomorrow.",
    }
    return f"HTTP {code}: {message} {hints.get(code, '')}".strip()


def trim_history(
    history: list[dict[str, Any]], max_turns: int = MAX_HISTORY_TURNS
) -> list[dict[str, Any]]:
    """Keeps the newest turns, starting on a user turn as the API requires."""
    if len(history) <= max_turns:
        return history
    trimmed = history[-max_turns:]
    while trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    return trimmed


class Agent:
    def __init__(
        self,
        llm: Gemini,
        ask: Callable[[str], str] = input,
        say: Callable[[str], None] = print,
        runner: Callable[[str], tuple[str, str, int]] = run_command,
        max_steps: int = MAX_STEPS,
    ):
        self.llm = llm
        self.ask = ask
        self.say = say
        self.run = runner
        self.max_steps = max_steps
        self.history: list[dict[str, Any]] = []

    def _add(self, role: str, text: str) -> None:
        self.history.append({"role": role, "parts": [{"text": text}]})
        self.history = trim_history(self.history)

    def confirm(self, command: str) -> bool:
        risk = risk_of(command)
        if risk:
            self.say(f"!! WARNING: this command looks dangerous ({risk}).")
        while True:
            answer = self.ask(f"[Agent wants to run: {command}] Allow? (y/n) ").strip().lower()
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.say("Please answer y or n.")

    def handle(self, user_text: str) -> None:
        """One user request: loop model -> approved command -> output -> model, until no command or max steps.

        If the request fails (API error, Ctrl+C) the conversation is rolled back to before it, so turns stay
        alternating user/model for the next request."""
        snapshot = list(self.history)
        try:
            self._handle(user_text)
        except BaseException:
            self.history = snapshot
            raise

    def _handle(self, user_text: str) -> None:
        self._add("user", user_text)
        for _ in range(self.max_steps):
            reply = self.llm.generate(self.history)
            self._add("model", reply)
            visible = CMD_RE.sub(
                lambda m: f"[command: {find_command(m.group(0)) or ''}]", reply
            ).strip()
            self.say(f"Agent: {visible}")
            command = find_command(reply)
            if not command:
                return
            if not self.confirm(command):
                self._add(
                    "user",
                    "I declined that command. Suggest another approach or ask me what to do.",
                )
                self.say("[declined]")
                continue
            stdout, stderr, code = self.run(command)
            result = feedback_message(command, stdout, stderr, code)
            self.say(f"[exit {code}]\n{truncate(stdout + stderr, 2000).rstrip()}")
            self._add("user", result)
        self.say(f"[stopped after {self.max_steps} steps; say 'continue' to keep going]")


BANNER = f"""============================================================
 droid-agent {__version__}  ·  Gemini in your Termux shell
 Model: {{model}}   ·   Every command needs your y/n.
 Commands: 'exit' to quit, 'reset' to clear the conversation.
============================================================"""


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        sys.stderr.write(
            "GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/app/apikey\n"
            'then run: export GEMINI_API_KEY="your_key"\n'
        )
        return 1
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    agent = Agent(Gemini(api_key, model))
    print(BANNER.format(model=model))
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0
        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            print("Bye.")
            return 0
        if text.lower() == "reset":
            agent.history.clear()
            print("[conversation cleared]")
            continue
        try:
            agent.handle(text)
        except ApiError as exc:
            print(f"[error] {exc}")
        except KeyboardInterrupt:
            print("\n[interrupted]")


if __name__ == "__main__":
    sys.exit(main())
