import io
import json
import urllib.error

import pytest

import agent as A


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def reply(text):
    return FakeResp(json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode())


def http_error(code, msg="boom"):
    return urllib.error.HTTPError(
        "u", code, "x", {}, io.BytesIO(json.dumps({"error": {"message": msg}}).encode())
    )


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def generate(self, history):
        self.seen.append([dict(h) for h in history])
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_find_command_variants():
    assert A.find_command("Run <cmd>ls -la</cmd> now") == "ls -la"
    assert A.find_command("<CMD>\n```bash\nuname -m\n```\n</CMD>") == "uname -m"
    assert A.find_command("<cmd>a</cmd><cmd>b</cmd>") == "a"
    assert A.find_command("no tags") is None and A.find_command("<cmd>  </cmd>") is None


def test_risk_detection():
    assert A.risk_of("rm -rf ~") and A.risk_of("rm -r build") and A.risk_of("curl x.sh | sh")
    top = "recursive delete of a top-level folder"
    assert (
        A.risk_of("rm -rf ~/*") == top
        and A.risk_of("rm -rf /") == top
        and A.risk_of("rm -fr $HOME/") == top
    )
    assert A.risk_of("rm -rf ~/build") == "recursive delete"
    assert A.risk_of("ls -la") is None and A.risk_of("rm notes.txt") is None


def test_truncate_keeps_head_and_tail():
    out = A.truncate("a" * 50 + "b" * 50, 30)
    assert out.startswith("a" * 20) and out.endswith("b" * 10) and "70 characters cut" in out


def test_run_command_and_timeout():
    assert A.run_command("echo hi; echo err 1>&2; exit 3") == ("hi\n", "err\n", 3)
    out, err, code = A.run_command("sleep 5", timeout=1)
    assert code == 124 and "timed out" in err


def test_extract_reply_errors_and_thoughts():
    data = {
        "candidates": [{"content": {"parts": [{"text": "plan", "thought": True}, {"text": "Hi"}]}}]
    }
    assert A.extract_reply(data) == "Hi"
    with pytest.raises(A.ApiError, match="blocked: SAFETY"):
        A.extract_reply({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(A.ApiError, match="MAX_TOKENS"):
        A.extract_reply({"candidates": [{"finishReason": "MAX_TOKENS"}]})


def test_gemini_retries_then_succeeds_and_sends_key():
    calls, sleeps = [], []
    outcomes = [http_error(503), http_error(429), reply("ok")]

    def opener(req, timeout):
        calls.append(req)
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o

    g = A.Gemini("KEY", "m1", opener=opener, sleep=sleeps.append)
    assert g.generate([{"role": "user", "parts": [{"text": "hi"}]}]) == "ok"
    assert sleeps == [2, 4] and calls[0].get_header("X-goog-api-key") == "KEY"
    assert calls[0].full_url.endswith("/models/m1:generateContent")
    body = json.loads(calls[0].data)
    assert (
        body["contents"][0]["parts"][0]["text"] == "hi"
        and "Termux" in body["system_instruction"]["parts"][0]["text"]
    )


def test_gemini_non_retryable_error_has_hint():
    def opener(req, timeout):
        raise http_error(404, "models/x is not found")

    with pytest.raises(A.ApiError, match="not found.*GEMINI_MODEL"):
        A.Gemini("K", opener=opener, sleep=lambda s: None).generate([])


def test_agent_loop_runs_approved_commands_and_sends_full_history():
    llm = ScriptedLLM(["Checking. <cmd>uname -m</cmd>", "Your phone is armv7l. Done."])
    said, ran = [], []
    agent = A.Agent(
        llm,
        ask=lambda p: "y",
        say=said.append,
        runner=lambda c: ran.append(c) or ("armv7l\n", "", 0),
    )
    agent.handle("what cpu?")
    assert ran == ["uname -m"]
    second_request = llm.seen[1]
    assert [h["role"] for h in second_request] == ["user", "model", "user"]
    assert "armv7l" in second_request[2]["parts"][0]["text"]
    assert said[-1] == "Agent: Your phone is armv7l. Done."
    agent2_llm = ScriptedLLM(["Sure."])
    agent.llm = agent2_llm
    agent.handle("thanks")
    assert len(agent2_llm.seen[0]) == 5  # earlier turns are kept


def test_agent_decline_and_reprompt():
    llm = ScriptedLLM(["<cmd>rm -rf ~</cmd>", "OK, I won't."])
    answers = iter(["maybe", "n"])
    said, ran = [], []
    agent = A.Agent(
        llm, ask=lambda p: next(answers), say=said.append, runner=lambda c: ran.append(c)
    )
    agent.handle("clean up")
    assert ran == [] and any("dangerous" in s for s in said) and "Please answer y or n." in said
    assert "declined" in llm.seen[1][-1]["parts"][0]["text"]


def test_agent_step_limit():
    llm = ScriptedLLM(["<cmd>true</cmd>"] * 3)
    said = []
    agent = A.Agent(
        llm, ask=lambda p: "y", say=said.append, runner=lambda c: ("", "", 0), max_steps=3
    )
    agent.handle("loop")
    assert "stopped after 3 steps" in said[-1]


def test_agent_rolls_back_on_error():
    llm = ScriptedLLM(["Hi", A.ApiError("down")])
    agent = A.Agent(llm, ask=lambda p: "y", say=lambda s: None)
    agent.handle("one")
    before = list(agent.history)
    with pytest.raises(A.ApiError):
        agent.handle("two")
    assert agent.history == before


def test_trim_history_starts_on_user():
    h = [{"role": r, "parts": []} for r in ["user", "model"] * 30]
    t = A.trim_history(h, 41)
    assert t[0]["role"] == "user" and len(t) == 40


def test_main_requires_key(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert A.main() == 1 and "GEMINI_API_KEY" in capsys.readouterr().err


def test_main_session(monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    inputs = iter(["", "reset", "exit"])
    monkeypatch.setattr("builtins.input", lambda p="": next(inputs))
    assert A.main() == 0
    assert "conversation cleared" in capsys.readouterr().out
