"""Tests for pipeline/model.py.

The HTTP call is replaced with a fake, so none of this needs Ollama running.
generate_stream is lazy, so every test consumes it before asserting on the
request that was sent.
"""

import json
from typing import Any

import httpx
import pytest

import config
from pipeline.model import ModelError, build_timeout, generate_stream


class FakeStream:
    """Stands in for the context manager httpx.stream returns."""

    def __init__(self, status_code: int, lines: list[str], text: str = "") -> None:
        self.status_code = status_code
        self._lines = lines
        self.text = text

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def read(self) -> bytes:
        return b""

    def iter_lines(self):
        return iter(self._lines)


class Recorder:
    """Captures the request handed to httpx.stream."""

    def __init__(self, response: FakeStream) -> None:
        self.response = response
        self.body: dict[str, Any] = {}
        self.timeout: httpx.Timeout | None = None
        self.url = ""
        self.method = ""

    def stream(
        self, method: str, url: str, json: dict[str, Any], timeout: httpx.Timeout
    ) -> FakeStream:
        self.method = method
        self.url = url
        self.body = json
        self.timeout = timeout
        return self.response


def line(text: str, done: bool = False, reason: str | None = None) -> str:
    """Build one line of Ollama's streaming ndjson."""
    payload: dict[str, Any] = {"response": text, "done": done}
    if reason is not None:
        payload["done_reason"] = reason
    return json.dumps(payload)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """Replace httpx.stream with a recorder returning a successful reply."""
    made = Recorder(
        FakeStream(200, [line("an "), line("answer"), line("", done=True, reason="stop")])
    )
    monkeypatch.setattr(httpx, "stream", made.stream)
    return made


def test_thinking_is_disabled_in_the_request_body(recorder: Recorder) -> None:
    """think is sent explicitly as false.

    Regression test. Ollama turns thinking on by default for models that
    support it, and qwen3:8b does. Measured, the reasoning tokens come out of
    the same budget as the answer: with num_predict 200 the whole budget went
    to thinking and the response came back empty.
    """
    list(generate_stream("a prompt"))
    assert recorder.body["think"] is False


def test_request_body_carries_the_runtime_options(recorder: Recorder) -> None:
    """num_ctx, num_predict, and temperature are sent on every call."""
    list(generate_stream("a prompt"))
    options = recorder.body["options"]
    assert options["num_ctx"] == config.OLLAMA_NUM_CTX
    assert options["num_predict"] == config.OLLAMA_NUM_PREDICT
    assert options["temperature"] == 0


def test_request_asks_for_a_stream_and_keeps_the_model_warm(
    recorder: Recorder,
) -> None:
    """Streaming is on, and keep_alive holds the model in memory."""
    list(generate_stream("a prompt"))
    assert recorder.body["stream"] is True
    assert recorder.body["keep_alive"] == config.OLLAMA_KEEP_ALIVE
    assert recorder.method == "POST"


def test_system_prompt_is_only_sent_when_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The system field is omitted rather than sent empty."""
    made = Recorder(FakeStream(200, [line("", done=True, reason="stop")]))
    monkeypatch.setattr(httpx, "stream", made.stream)

    list(generate_stream("a prompt"))
    assert "system" not in made.body

    list(generate_stream("a prompt", system="be careful"))
    assert made.body["system"] == "be careful"


def test_chunks_carry_text_then_a_final_reason(recorder: Recorder) -> None:
    """Text arrives chunk by chunk, with the stop reason on the last one."""
    chunks = list(generate_stream("a prompt"))
    assert [chunk.text for chunk in chunks] == ["an ", "answer", ""]
    assert chunks[-1].done_reason == "stop"
    assert chunks[0].done_reason is None


def test_output_cap_is_reported_as_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hitting num_predict comes back as done_reason length.

    This is the only signal that an answer was cut off rather than finished,
    so it has to survive to the caller.
    """
    made = Recorder(FakeStream(200, [line("cut "), line("", done=True, reason="length")]))
    monkeypatch.setattr(httpx, "stream", made.stream)
    assert list(generate_stream("a prompt"))[-1].done_reason == "length"


def test_timeout_is_not_the_httpx_default(recorder: Recorder) -> None:
    """The read timeout covers a cold start, not the httpx default of five."""
    list(generate_stream("a prompt"))
    assert recorder.timeout is not None
    assert recorder.timeout.read == config.OLLAMA_TIMEOUT
    assert recorder.timeout.read > 5.0
    assert recorder.timeout.connect == 5.0


def test_build_timeout_separates_connect_from_read() -> None:
    """Connect stays short so a stopped Ollama fails fast."""
    timeout = build_timeout()
    assert timeout.connect == 5.0
    assert timeout.read == config.OLLAMA_TIMEOUT


def test_missing_model_gives_an_actionable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 from Ollama names the pull command."""
    made = Recorder(FakeStream(404, [], text="model not found"))
    monkeypatch.setattr(httpx, "stream", made.stream)
    with pytest.raises(ModelError, match="ollama pull"):
        list(generate_stream("a prompt"))


def test_server_error_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-200 reply is surfaced rather than parsed as an answer."""
    made = Recorder(FakeStream(500, [], text="internal failure"))
    monkeypatch.setattr(httpx, "stream", made.stream)
    with pytest.raises(ModelError, match="internal failure"):
        list(generate_stream("a prompt"))


def test_error_inside_the_stream_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama can report a failure mid-stream after a 200."""
    made = Recorder(FakeStream(200, [json.dumps({"error": "out of memory"})]))
    monkeypatch.setattr(httpx, "stream", made.stream)
    with pytest.raises(ModelError, match="out of memory"):
        list(generate_stream("a prompt"))


def test_unreadable_line_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """A line that is not JSON does not escape as a decode error."""
    made = Recorder(FakeStream(200, ["this is not json"]))
    monkeypatch.setattr(httpx, "stream", made.stream)
    with pytest.raises(ModelError, match="could not be read"):
        list(generate_stream("a prompt"))


def test_unreachable_ollama_gives_a_readable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection failure says to check that Ollama is running."""

    def refuse(*args: object, **kwargs: object) -> FakeStream:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "stream", refuse)
    with pytest.raises(ModelError, match="Ollama is running"):
        list(generate_stream("a prompt"))


def test_timeout_gives_a_readable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A read timeout explains itself rather than raising httpx internals."""

    def stall(*args: object, **kwargs: object) -> FakeStream:
        raise httpx.ReadTimeout("too slow")

    monkeypatch.setattr(httpx, "stream", stall)
    with pytest.raises(ModelError, match="did not finish"):
        list(generate_stream("a prompt"))
