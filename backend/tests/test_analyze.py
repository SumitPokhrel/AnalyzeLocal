"""Tests for pipeline/analyze.py.

The model stream is replaced with a recorder, so none of this needs Ollama.
Event sequencing is covered end to end in test_stream.py; this file covers
the pure helpers and the prompts that get built.
"""

from collections.abc import Iterator

import pytest

import config
from pipeline import analyze, model


class RecordingModel:
    """Stands in for model.generate_stream, recording every prompt."""

    def __init__(self, reply: str = "a canned answer") -> None:
        self.reply = reply
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def generate_stream(
        self, prompt: str, system: str | None = None
    ) -> Iterator[model.ModelChunk]:
        self.prompts.append(prompt)
        self.systems.append(system)
        yield model.ModelChunk(text=self.reply, done_reason=None)
        yield model.ModelChunk(text="", done_reason="stop")


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> RecordingModel:
    """Replace the model stream used inside analyze.py."""
    made = RecordingModel()
    monkeypatch.setattr(analyze.model, "generate_stream", made.generate_stream)
    return made


OFFER = (
    "OFFER OF EMPLOYMENT\n"
    "Your base salary will be 168000 USD per year. "
    "You will receive a signing bonus of 25000 USD. "
    "Your equity grant is 8000 restricted stock units with vesting over "
    "four years. This position is at-will."
)

LEASE = (
    "RESIDENTIAL LEASE\n"
    "The tenant shall pay monthly rent of 2450 USD to the landlord. "
    "The security deposit is 4900 USD. The premises may not be sublet. "
    "The lease term runs for twelve months."
)

TAX_RETURN = (
    "U.S. Individual Income Tax Return, Form 1040\n"
    "Filing status: single. Adjusted gross income: 91500 USD. "
    "Taxable income: 77800 USD. Federal income tax withholding: 14200 USD. "
    "Refund: 1350 USD."
)


def test_detects_a_job_offer() -> None:
    """An offer letter scores against the job offer keywords."""
    assert analyze.detect_document_type(OFFER) == "job_offer"


def test_detects_a_lease() -> None:
    """A lease scores against the lease keywords."""
    assert analyze.detect_document_type(LEASE) == "lease"


def test_detects_a_tax_return() -> None:
    """A tax return scores against the tax return keywords."""
    assert analyze.detect_document_type(TAX_RETURN) == "tax_return"


def test_unrecognized_document_falls_back_to_generic() -> None:
    """A document matching nothing gets the generic checklist."""
    assert analyze.detect_document_type("A shopping list. Milk. Bread.") == "generic"


def test_single_keyword_is_not_enough_to_claim_a_type() -> None:
    """One incidental keyword does not pick a type.

    The word refund turns up in plenty of documents that are not tax
    returns, so a single hit stays generic.
    """
    assert analyze.detect_document_type("Ask about a refund if it breaks.") == "generic"


def test_short_document_is_not_truncated() -> None:
    """A document inside the budget is passed through unchanged."""
    text, truncated = analyze.truncate_to_budget(OFFER, config.DOCUMENT_TOKEN_BUDGET)
    assert text == OFFER
    assert truncated is False


def test_long_document_is_truncated_and_reported() -> None:
    """A document past the budget is cut and the flag is set."""
    long_text = "word " * 40000
    text, truncated = analyze.truncate_to_budget(long_text, config.DOCUMENT_TOKEN_BUDGET)
    assert truncated is True
    assert len(text) < len(long_text)
    assert analyze.estimate_tokens(text) <= config.DOCUMENT_TOKEN_BUDGET


def test_verify_quotes_accepts_a_real_quote() -> None:
    """A quote lifted from the document verifies."""
    answer = 'Base salary is 168000 USD, "Your base salary will be 168000 USD".'
    assert analyze.verify_quotes(answer, OFFER) == []


def test_verify_quotes_flags_a_fabricated_quote() -> None:
    """A quote that is not in the document is reported.

    This is the failure that matters most: a wrong salary figure reads
    exactly as confidently as a right one.
    """
    answer = 'Base salary is 195000 USD, "Your base salary will be 195000 USD".'
    assert analyze.verify_quotes(answer, OFFER) == [
        "Your base salary will be 195000 USD"
    ]


def test_verify_quotes_ignores_whitespace_and_case() -> None:
    """Line wrapping in the source does not break a genuine quote."""
    source = "Your base salary\n   will be   168000 USD per year."
    answer = 'It says "your base salary will be 168000 USD".'
    assert analyze.verify_quotes(answer, source) == []


def test_verify_quotes_handles_typographic_quotes() -> None:
    """Curly quotes from the model are matched like straight ones."""
    answer = "It says \u201cYour base salary will be 168000 USD\u201d."
    assert analyze.verify_quotes(answer, OFFER) == []


def test_not_stated_marker_is_not_flagged_as_a_quote() -> None:
    """The not-stated phrase does not raise a false warning.

    Regression test. The system prompt tells the model to write 'not stated
    in the document' for a missing point, and the model puts it in double
    quotes. That parsed as a quotation, so a live run on a clean offer letter
    produced a warning saying the phrase could not be found in the document.
    """
    answer = 'Notice period: "not stated in the document".'
    assert analyze.verify_quotes(answer, OFFER) == []


def test_a_real_invention_is_still_flagged_alongside_the_marker() -> None:
    """Skipping the marker does not weaken the check around it."""
    answer = (
        'Notice: "not stated in the document". '
        'Salary is "Your base salary will be 999999 USD".'
    )
    assert analyze.verify_quotes(answer, OFFER) == [
        "Your base salary will be 999999 USD"
    ]


def test_analysis_prompt_puts_the_document_first(recorder: RecordingModel) -> None:
    """The document leads the prompt so Ollama's prefix cache covers it.

    Measured, a cached prefix turns a 19 second prompt evaluation into 0.05
    seconds on the next question, which is what makes follow-ups usable.
    """
    list(analyze.stream_analysis(OFFER, ["abc"]))
    assert recorder.prompts[0].startswith("Document:\n")


def test_analysis_prompt_carries_the_matching_checklist(
    recorder: RecordingModel,
) -> None:
    """A lease gets the lease checklist, not the job offer one."""
    list(analyze.stream_analysis(LEASE, ["abc"]))
    prompt = recorder.prompts[0]
    assert "Security deposit" in prompt
    assert "Base salary" not in prompt


def test_analysis_sends_the_grounding_system_prompt(
    recorder: RecordingModel,
) -> None:
    """The grounding rules go with every analysis call."""
    list(analyze.stream_analysis(OFFER, ["abc"]))
    assert recorder.systems[0] == analyze.ANALYSIS_SYSTEM_PROMPT


def test_compare_digests_each_document_then_compares(
    recorder: RecordingModel,
) -> None:
    """Comparison is three calls: one digest each, then the comparison."""
    list(analyze.stream_comparison(OFFER, LEASE, ["a", "b"]))
    assert len(recorder.prompts) == 3


def test_compare_shows_each_document_only_its_own_text(
    recorder: RecordingModel,
) -> None:
    """A digest call sees one document, never both.

    Keeping them apart is what makes the quotes in each digest traceable to
    a single source.
    """
    list(analyze.stream_comparison(OFFER, LEASE, ["a", "b"]))
    first, second = recorder.prompts[0], recorder.prompts[1]
    assert "168000 USD" in first and "2450 USD" not in first
    assert "2450 USD" in second and "168000 USD" not in second


def test_compare_uses_the_comparison_system_prompt(
    recorder: RecordingModel,
) -> None:
    """The final call is told it is comparing summaries, not documents."""
    list(analyze.stream_comparison(OFFER, LEASE, ["a", "b"]))
    assert recorder.systems[2] == analyze.COMPARISON_SYSTEM_PROMPT


def test_question_prompt_puts_document_first_then_history(
    recorder: RecordingModel,
) -> None:
    """Document, then earlier turns, then the new question."""
    history = [("What is the salary?", "168000 USD.")]
    list(analyze.stream_answer(OFFER, "And the bonus?", history))
    prompt = recorder.prompts[0]
    assert prompt.startswith("Document:\n")
    assert prompt.index("Earlier question:") < prompt.index("Question: And the bonus?")


def test_question_without_history_omits_the_earlier_section(
    recorder: RecordingModel,
) -> None:
    """A first question carries no history block."""
    list(analyze.stream_answer(OFFER, "What is the salary?"))
    assert "Earlier question:" not in recorder.prompts[0]
