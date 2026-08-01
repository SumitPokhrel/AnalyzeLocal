"""Tests for the streaming routes and the event sequence they produce.

model.generate_stream is replaced with a fake, so none of this needs Ollama.
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
import config
from app import app
from pipeline import analyze, model


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A test client that returns error responses instead of raising."""
    return TestClient(app, raise_server_exceptions=False)


def chunks(*texts: str, done_reason: str = "stop") -> Iterator[model.ModelChunk]:
    """Build a streamed reply ending with the given reason."""
    for text in texts:
        yield model.ModelChunk(text=text, done_reason=None)
    yield model.ModelChunk(text="", done_reason=done_reason)


def install(monkeypatch: pytest.MonkeyPatch, maker) -> list[str]:
    """Replace the model stream. Returns the list of prompts it was given."""
    prompts: list[str] = []

    def generate_stream(prompt: str, system: str | None = None):
        prompts.append(prompt)
        return maker()

    monkeypatch.setattr(model, "generate_stream", generate_stream)
    return prompts


def events(response) -> list[dict]:
    """Parse an ndjson response body into event dicts."""
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def names(response) -> list[str]:
    """The event names in order."""
    return [item["event"] for item in events(response)]


def upload(client: TestClient, path: Path):
    return client.post("/api/analyze", files={"file": (path.name, path.read_bytes())})


# The utf8 fixture document reads "Base salary: 145000 USD", so QUOTED is
# verbatim from it and INVENTED is not.
QUOTED = 'The pay is "Base salary: 145000 USD".'
INVENTED = 'The pay is "Base salary: 999999 USD".'


def test_analyze_streams_ndjson(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route answers with newline delimited JSON, not a single body."""
    install(monkeypatch, lambda: chunks("Base salary ", "is 145000 USD."))
    response = upload(client, documents["utf8"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")


def test_analyze_event_order(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Meta arrives before any token, and done is last."""
    install(monkeypatch, lambda: chunks("Base ", "salary."))
    order = names(upload(client, documents["utf8"]))
    assert order[0] == "meta"
    assert order[1] == "status"
    assert order[-1] == "done"
    assert order.count("token") == 2


def test_analyze_meta_carries_type_and_truncation(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The detected type and truncation flag reach the client before text."""
    install(monkeypatch, lambda: chunks("text"))
    meta = events(upload(client, documents["utf8"]))[0]
    assert meta["truncated"] is False
    assert len(meta["document_ids"]) == 1
    assert meta["document_type"] in {"job_offer", "lease", "tax_return", "generic"}
    assert meta["unsupported_type"] is False


def test_warning_follows_the_answer(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invented quote produces a warning event after the tokens."""
    install(monkeypatch, lambda: chunks(INVENTED))
    order = names(upload(client, documents["utf8"]))
    assert order.index("warning") > order.index("token")
    assert order[-1] == "done"


def test_clean_answer_has_no_warning(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An answer whose quotes check out emits no warning event."""
    install(monkeypatch, lambda: chunks(QUOTED))
    assert "warning" not in names(upload(client, documents["utf8"]))


def test_output_cap_ends_with_incomplete_not_done(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hitting num_predict is reported, not passed off as a finished answer.

    Under streaming a capped answer just looks like text stopping, which is
    the same invisible failure as an empty response. The terminal event says
    so instead.
    """
    install(monkeypatch, lambda: chunks(QUOTED, done_reason="length"))
    order = names(upload(client, documents["utf8"]))
    assert "done" not in order
    assert order[-1] == "incomplete"

    final = events(upload(client, documents["utf8"]))[-1]
    assert final["reason"] == "length"


def test_output_cap_still_runs_the_quote_check(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capped answer is short, but what arrived is still checked."""
    install(monkeypatch, lambda: chunks(INVENTED, done_reason="length"))
    order = names(upload(client, documents["utf8"]))
    assert order.index("warning") < order.index("incomplete")


def test_interrupted_stream_says_the_answer_is_incomplete(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generation breaking partway is reported rather than rendered as done.

    The reader is looking at text that was never checked, so silence here
    would be worse than the truncation it resembles.
    """

    def breaks() -> Iterator[model.ModelChunk]:
        yield model.ModelChunk(text="Base salary is ", done_reason=None)
        raise model.ModelError("the connection dropped")

    install(monkeypatch, breaks)
    response = upload(client, documents["utf8"])
    order = names(response)
    assert order[-1] == "incomplete"
    assert events(response)[-1]["reason"] == "interrupted"


def test_interrupted_stream_emits_no_warning(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No warning event, because the quote check never ran.

    The absence has to be stated by the incomplete event, since a missing
    warning would otherwise read as a clean bill of health.
    """

    def breaks() -> Iterator[model.ModelChunk]:
        yield model.ModelChunk(text=INVENTED, done_reason=None)
        raise model.ModelError("the connection dropped")

    install(monkeypatch, breaks)
    response = upload(client, documents["utf8"])
    assert "warning" not in names(response)
    assert "did not run" in events(response)[-1]["detail"]


def test_failure_before_any_text_is_an_error(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model failure with nothing on screen is an error, not an incomplete."""

    def refuse() -> Iterator[model.ModelChunk]:
        raise model.ModelError("Check that Ollama is running.")
        yield  # pragma: no cover

    install(monkeypatch, refuse)
    response = upload(client, documents["utf8"])
    order = names(response)
    assert order[-1] == "error"
    assert "Ollama" in events(response)[-1]["detail"]


def test_empty_answer_is_an_error(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream that produces no text at all is reported.

    This is the shape the thinking-budget failure takes: the model returns
    normally, having spent the whole budget on reasoning.
    """
    install(monkeypatch, lambda: chunks(done_reason="length"))
    response = upload(client, documents["utf8"])
    assert names(response)[-1] == "error"
    assert "empty answer" in events(response)[-1]["detail"]


def test_extraction_failure_stays_a_real_status_code(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Extraction runs before the stream opens, so 422 survives."""
    install(monkeypatch, lambda: chunks("unused"))
    response = upload(client, documents["scanned_pdf"])
    assert response.status_code == 422
    assert "scan" in response.json()["detail"]


def test_compare_streams_all_three_calls(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both digests stream, not just the final comparison.

    Two silent digests would be about a minute of dead air, which is most of
    the wait.
    """
    install(monkeypatch, lambda: chunks("some text"))
    response = client.post(
        "/api/compare",
        files={
            "first": ("a.txt", documents["utf8"].read_bytes()),
            "second": ("b.txt", documents["utf8"].read_bytes()),
        },
    )
    assert response.status_code == 200
    stages = [item["stage"] for item in events(response) if item["event"] == "token"]
    assert set(stages) == {"reading_first", "reading_second", "comparing"}


def test_compare_meta_holds_both_document_ids(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compare reports two ids in the same field shape as analyze."""
    install(monkeypatch, lambda: chunks("some text"))
    response = client.post(
        "/api/compare",
        files={
            "first": ("a.txt", documents["utf8"].read_bytes()),
            "second": ("b.txt", documents["utf8"].read_bytes()),
        },
    )
    assert len(events(response)[0]["document_ids"]) == 2


def test_question_streams_and_records_history(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished answer is kept as context for the next question."""
    prompts = install(monkeypatch, lambda: chunks("The salary is 145000 USD."))
    document_id = events(upload(client, documents["utf8"]))[0]["document_ids"][0]

    client.post(
        "/api/question", json={"document_id": document_id, "question": "Salary?"}
    )
    assert app_module.HISTORY[document_id] == [("Salary?", "The salary is 145000 USD.")]

    client.post(
        "/api/question", json={"document_id": document_id, "question": "Bonus?"}
    )
    assert "Earlier question: Salary?" in prompts[-1]


def test_history_is_capped(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the most recent turns are kept, since history costs context."""
    install(monkeypatch, lambda: chunks("An answer."))
    document_id = events(upload(client, documents["utf8"]))[0]["document_ids"][0]
    for number in range(config.HISTORY_TURNS + 2):
        client.post(
            "/api/question",
            json={"document_id": document_id, "question": f"Question {number}?"},
        )
    assert len(app_module.HISTORY[document_id]) == config.HISTORY_TURNS


def test_interrupted_answer_is_not_kept_as_history(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half finished answer is not fed back into the next prompt.

    Storing it would carry an unverified fragment into every later turn.
    """
    install(monkeypatch, lambda: chunks("A good answer."))
    document_id = events(upload(client, documents["utf8"]))[0]["document_ids"][0]
    app_module.HISTORY.pop(document_id, None)

    def breaks() -> Iterator[model.ModelChunk]:
        yield model.ModelChunk(text="half an ans", done_reason=None)
        raise model.ModelError("dropped")

    install(monkeypatch, breaks)
    client.post(
        "/api/question", json={"document_id": document_id, "question": "Salary?"}
    )
    assert document_id not in app_module.HISTORY


def test_unknown_document_id_still_returns_404(client: TestClient) -> None:
    """The lookup happens before the stream opens, so 404 survives."""
    response = client.post(
        "/api/question", json={"document_id": "missing", "question": "Salary?"}
    )
    assert response.status_code == 404


def test_stage_constants_match_the_frontend_progress_set() -> None:
    """The digest stages are the ones the interface routes to the progress area."""
    assert analyze.STAGE_READING_FIRST == "reading_first"
    assert analyze.STAGE_READING_SECOND == "reading_second"
    assert analyze.STAGE_COMPARING == "comparing"


def overflowing(*texts: str, prompt_tokens: int = 0, eval_tokens: int = 50):
    """A reply whose token counts say the context window was exceeded."""
    tokens = prompt_tokens or config.OLLAMA_NUM_CTX

    def maker() -> Iterator[model.ModelChunk]:
        for text in texts:
            yield model.ModelChunk(text=text, done_reason=None)
        yield model.ModelChunk(
            text="",
            done_reason="stop",
            prompt_tokens=tokens,
            eval_tokens=eval_tokens,
        )

    return maker


def fitting(*texts: str):
    """A reply whose token counts sit comfortably inside the window."""

    def maker() -> Iterator[model.ModelChunk]:
        for text in texts:
            yield model.ModelChunk(text=text, done_reason=None)
        yield model.ModelChunk(
            text="", done_reason="stop", prompt_tokens=1000, eval_tokens=100
        )

    return maker


def alternating(monkeypatch: pytest.MonkeyPatch, makers: list) -> list[str]:
    """Install a sequence of replies, one per call. Returns the prompts."""
    prompts: list[str] = []
    remaining = list(makers)

    def generate_stream(prompt: str, system: str | None = None):
        prompts.append(prompt)
        return (remaining.pop(0) if len(remaining) > 1 else remaining[0])()

    monkeypatch.setattr(model, "generate_stream", generate_stream)
    return prompts


def test_overflow_retries_once_and_announces_it(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first attempt that overflowed is discarded and rerun, visibly.

    An unexplained doubled wait is worse than an explained one, so the
    restart event carries the reason.
    """
    prompts = alternating(
        monkeypatch, [overflowing("bad answer"), fitting(QUOTED)]
    )
    response = upload(client, documents["utf8"])
    order = names(response)

    assert "restart" in order
    assert len(prompts) == 2
    assert order[-1] == "done"

    restart = next(e for e in events(response) if e["event"] == "restart")
    assert restart["reason"] == "context_overflow"
    assert "shorter excerpt" in restart["message"]


def test_retry_is_sent_a_shorter_excerpt(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second attempt carries less document text, sized from measurement.

    Uses a large document, because that is the only case where retrying
    means anything. The excerpt is what has to shrink: the prompt as a whole
    also gains the fragment instruction on the second pass.
    """
    prompts = alternating(
        monkeypatch,
        [overflowing("bad answer", prompt_tokens=config.OLLAMA_NUM_CTX), fitting(QUOTED)],
    )
    path = tmp_path / "long.txt"
    path.write_text("The tenant shall pay rent on the first of the month. " * 2000)
    client.post("/api/analyze", files={"file": (path.name, path.read_bytes())})

    assert len(prompts) == 2
    excerpts = [len(p) - len(analyze.FRAGMENT_INSTRUCTION) if analyze.FRAGMENT_INSTRUCTION in p
                else len(p) for p in prompts]
    assert excerpts[1] < excerpts[0]


def test_restart_comes_before_the_replacement_tokens(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clear signal arrives before the answer that replaces the old one."""
    alternating(monkeypatch, [overflowing("bad answer"), fitting(QUOTED)])
    order = names(upload(client, documents["utf8"]))
    assert order.index("restart") < len(order) - 1
    assert "token" in order[order.index("restart") :]


def test_second_overflow_fails_loudly_instead_of_retrying_again(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two overflows stop, rather than making the user wait for a third."""
    prompts = alternating(monkeypatch, [overflowing("bad"), overflowing("also bad")])
    response = upload(client, documents["utf8"])
    order = names(response)

    assert len(prompts) == 2
    assert order.count("restart") == 1
    assert order[-1] == "incomplete"
    final = events(response)[-1]
    assert final["reason"] == "context_overflow"
    assert "Do not rely on this answer" in final["detail"]


def test_no_retry_when_the_context_fits(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A normal run makes one call and emits no restart."""
    prompts = alternating(monkeypatch, [fitting(QUOTED)])
    order = names(upload(client, documents["utf8"]))
    assert len(prompts) == 1
    assert "restart" not in order


def test_coverage_is_reported_on_every_answer(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Coverage arrives even when no quote failed."""
    alternating(monkeypatch, [fitting(QUOTED)])
    response = upload(client, documents["utf8"])
    assert "coverage" in names(response)
    coverage = next(e for e in events(response) if e["event"] == "coverage")
    assert coverage["quoted"] >= 1


def test_zero_coverage_is_reported_rather_than_passing_silently(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A paraphrased answer reports no coverage and raises no warning.

    Regression test. On a blank 1040 the model paraphrased every figure, so
    verify_quotes had nothing to check and the answer displayed as clean.
    """
    alternating(monkeypatch, [fitting("Total income is the sum of lines 1z and 8.")])
    response = upload(client, documents["utf8"])
    coverage = next(e for e in events(response) if e["event"] == "coverage")
    assert coverage["quoted"] == 0
    assert coverage["figures"] > 0
    assert "warning" not in names(response)


def test_status_carries_a_wait_estimate_for_a_long_document(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A large document says roughly how long the first text will take."""
    alternating(monkeypatch, [fitting(QUOTED)])
    path = tmp_path / "long.txt"
    path.write_text("The tenant shall pay rent on time. " * 3000)
    response = client.post(
        "/api/analyze", files={"file": (path.name, path.read_bytes())}
    )
    status = next(e for e in events(response) if e["event"] == "status")
    assert "seconds" in status["message"]


TAX_RETURN_TEXT = (
    "U.S. Individual Income Tax Return, Form 1040. Filing status: single. "
    "Adjusted gross income and taxable income are reported here. Federal "
    "income tax withholding applies. Internal Revenue Service."
)


def test_tax_return_upload_is_flagged_unsupported(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uploading a 1040 says so before any analysis text arrives.

    The notice has to reach the reader with the same weight as the
    truncation banner, so it rides on the same meta event.
    """
    alternating(monkeypatch, [fitting("An answer.")])
    path = tmp_path / "return.txt"
    path.write_text(TAX_RETURN_TEXT)
    response = client.post(
        "/api/analyze", files={"file": (path.name, path.read_bytes())}
    )
    meta = events(response)[0]
    assert meta["document_type"] == "tax_return"
    assert meta["unsupported_type"] is True


def test_supported_upload_is_not_flagged_unsupported(
    client: TestClient, documents: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ordinary document carries no unsupported notice."""
    alternating(monkeypatch, [fitting(QUOTED)])
    meta = events(upload(client, documents["utf8"]))[0]
    assert meta["unsupported_type"] is False
