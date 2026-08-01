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


def test_still_detects_a_tax_return() -> None:
    """Detection is kept even though the type is out of scope.

    Dropping the claim from the documentation does not stop anyone uploading
    a 1040. Recognizing it is what lets the app say it is unsupported instead
    of quietly doing a poor job.
    """
    assert analyze.detect_document_type(TAX_RETURN) == "tax_return"


def test_tax_return_is_marked_unsupported() -> None:
    """A recognized tax return is flagged as out of scope."""
    assert analyze.is_unsupported("tax_return") is True


def test_supported_types_are_not_marked_unsupported() -> None:
    """Job offers, leases, and generic documents are in scope."""
    for name in ("job_offer", "lease", "generic"):
        assert analyze.is_unsupported(name) is False


def test_tax_return_gets_the_generic_checklist() -> None:
    """An unsupported type falls back rather than keeping a tailored list.

    The tax return checklist was removed with the claim to handle them, so
    format_checklist falls through to generic. That fallback is the routing.
    """
    assert "tax_return" not in analyze.CHECKLISTS
    assert analyze.format_checklist("tax_return") == analyze.format_checklist("generic")


def test_tax_return_prompt_has_no_tax_specific_points() -> None:
    """The prompt for a 1040 asks the generic questions, not tax ones.

    Asserts on the checklist lines rather than on the whole prompt, because
    the prompt embeds the document and a tax return says "adjusted gross
    income" in its own text.
    """
    prompt = analyze.build_analysis_prompt(TAX_RETURN, "tax_return")
    assert "Tax year and filing status" not in prompt
    assert "Total income and adjusted gross income" not in prompt
    assert "Refund due or balance owed" not in prompt
    assert "What kind of document this is" in prompt


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


def test_overflow_detected_when_the_prompt_is_pinned_to_the_window() -> None:
    """A prompt at exactly num_ctx means Ollama discarded its front.

    Regression test. Measured on qwen3:8b: a prompt larger than num_ctx comes
    back with prompt_eval_count pinned to num_ctx, done_reason still "stop",
    and a sentinel placed at the front of the prompt is gone. The model
    invented a replacement for it rather than saying it could not see one.
    """
    result = analyze.StageResult()
    result.prompt_tokens = config.OLLAMA_NUM_CTX
    result.eval_tokens = 10
    assert analyze.context_overflowed(result) is True


def test_overflow_detected_when_generation_crosses_the_window() -> None:
    """A prompt that fits can still evict the front while generating.

    Regression test. This is what happened to the 1040: prompt 7965 fit
    inside 8192, but 7965 plus 370 generated tokens crossed it, so the front
    of the document was evicted partway through the answer.
    """
    result = analyze.StageResult()
    result.prompt_tokens = config.OLLAMA_NUM_CTX - 200
    result.eval_tokens = 400
    assert analyze.context_overflowed(result) is True


def test_no_overflow_when_everything_fits() -> None:
    """A prompt and answer inside the window is not flagged."""
    result = analyze.StageResult()
    result.prompt_tokens = 1000
    result.eval_tokens = 200
    assert analyze.context_overflowed(result) is False


def test_no_overflow_claimed_without_counts() -> None:
    """A stage with no reported counts is not treated as an overflow."""
    assert analyze.context_overflowed(analyze.StageResult()) is False


def test_measured_budget_uses_the_real_ratio_not_the_estimate() -> None:
    """The retry is sized from what the failed attempt actually used."""
    # 20000 characters measured at 10000 tokens is 2.0 chars per token.
    allowed = (
        config.OLLAMA_NUM_CTX - config.OLLAMA_NUM_PREDICT - analyze.SYSTEM_RESERVE_TOKENS
    )
    assert analyze.measured_budget_chars(20000, 10000) == allowed * 2


def test_coverage_counts_quoted_figures() -> None:
    """Figures sitting inside a quote are counted as covered."""
    answer = 'Base salary "Your base salary will be 168000 USD per year".'
    coverage = analyze.measure_coverage(answer)
    assert coverage.figures == 1
    assert coverage.quoted == 1


def test_coverage_reports_zero_when_nothing_is_quoted() -> None:
    """A paraphrased answer reports no coverage rather than passing silently.

    Regression test. On a blank IRS 1040 the model paraphrased every line
    reference instead of quoting, so verify_quotes had nothing to check and
    returned clean. Zero coverage and full verification looked identical.
    """
    answer = "Total income is the sum of lines 1z, 2b, and 8."
    coverage = analyze.measure_coverage(answer)
    assert coverage.figures > 0
    assert coverage.quoted == 0


def test_coverage_ignores_markdown_list_numbering() -> None:
    """Bullet numbering is not counted as a figure the model reported."""
    answer = "1. First point\n2. Second point\n3. Third point"
    assert analyze.measure_coverage(answer).figures == 0


def test_coverage_ignores_the_not_stated_marker() -> None:
    """The not-stated phrase does not count as a supporting quote."""
    answer = 'Refund: "not stated in the document". Tax year is 2025.'
    coverage = analyze.measure_coverage(answer)
    assert coverage.quoted == 0


def test_fragment_instruction_added_only_when_truncated() -> None:
    """A truncated document tells the model it is seeing a fragment.

    Regression test. With only the banner, the model described the whole
    document from the part it saw, listing two schedules of a 1040 that has
    eight as though that were the complete set.
    """
    cut = analyze.build_analysis_prompt("text", "lease", truncated=True)
    whole = analyze.build_analysis_prompt("text", "lease", truncated=False)
    assert analyze.FRAGMENT_INSTRUCTION in cut
    assert analyze.FRAGMENT_INSTRUCTION not in whole


def test_fragment_instruction_reaches_digest_and_question_prompts() -> None:
    """Scoping applies wherever a truncated document is sent."""
    assert analyze.FRAGMENT_INSTRUCTION in analyze.build_digest_prompt(
        "text", "lease", truncated=True
    )
    assert analyze.FRAGMENT_INSTRUCTION in analyze.build_question_prompt(
        "text", "How much?", (), truncated=True
    )


def test_wait_estimate_only_appears_for_a_long_document() -> None:
    """A short document gets no estimate, a long one gets seconds."""
    assert analyze.describe_wait("short text") == "Reading the document"
    long_message = analyze.describe_wait("word " * 20000)
    assert "seconds" in long_message
    assert "tokens" in long_message


# The dot leaders on a form line, exactly as pypdf extracts them from a 1040.
FORM_LINE = (
    "9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8. This is your total "
    "income . . . . . . . . . . . 9\n"
    "10 Adjustments to income from Schedule 1, line 26 . . . . . . . . . 10"
)


def test_dot_leaders_do_not_break_a_verbatim_quote() -> None:
    """A form line quoted without its leaders still matches the document.

    Regression test. A blank IRS 1040 extracts as "This is your total income
    . . . . . . 9". The model quotes the line without the leaders and with a
    closing period, so the contiguous match failed and seven of eight
    warnings on that document were formatting artifacts.
    """
    quote = (
        '"9 Add lines 1z, 2b, 3b, 4b, 5b, 6b, 7a, and 8. '
        'This is your total income."'
    )
    assert analyze.verify_quotes(quote, FORM_LINE) == []


def test_punctuation_differences_do_not_break_a_quote() -> None:
    """A quote differing only in punctuation is substantively verbatim."""
    source = "Subtract line 14 from line 11b. If zero or less, enter -0-."
    quote = '"Subtract line 14 from line 11b: if zero or less enter -0-"'
    assert analyze.verify_quotes(quote, source) == []


def test_dropping_words_is_still_flagged() -> None:
    """Loosening punctuation does not excuse a quote that omits wording."""
    source = "Subtract line 14 from line 11b. If zero or less, enter -0-."
    quote = '"Subtract line 14 from line 11b, enter -0-"'
    assert analyze.verify_quotes(quote, source) != []


def test_absent_wording_is_still_flagged_after_leader_handling() -> None:
    """A phrase that is nowhere in the document still fails the check.

    Regression test. On the 1040 the model wrote "18 Add lines 16 and 17.
    This is your total tax." The line label is real, but "this is your total
    tax" appears nowhere in the document: the model merged a real label with
    an invented descriptor. Loosening the match for dot leaders must not
    let that through.
    """
    source = "18 Add lines 16 and 17 . . . . . . . . . . . . . . . . 18"
    flagged = analyze.verify_quotes(
        '"18 Add lines 16 and 17. This is your total tax."', source
    )
    assert flagged == ["18 Add lines 16 and 17. This is your total tax."]


def test_fabricated_figure_still_flagged_after_leader_handling() -> None:
    """Loosening formatting does not loosen the figures themselves."""
    answer = 'Salary is "Your base salary will be 999999 USD".'
    assert analyze.verify_quotes(answer, OFFER) == [
        "Your base salary will be 999999 USD"
    ]
