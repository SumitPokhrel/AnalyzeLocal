"""Analyze document text with the local model.

Every function here reads the document text as extracted, with nothing
removed. The text goes to the local Ollama process and nowhere else.

Work is produced as a stream of events rather than a finished string, so the
interface can show text as it arrives. A first analysis takes about thirty
seconds and a comparison about eighty, which is too long to show nothing.

Three things shape how the prompts are built. The document always comes
first, because Ollama caches the KV prefix and an unchanged document then
costs almost nothing to re-send on a follow-up question. Every figure the
model reports has to carry a quote, so verify_quotes can check it against the
source once generation finishes. And the token counts that come back are
checked against the context window, because Ollama drops the front of an
oversized prompt silently and the model invents text to fill the gap.
"""

import re
from collections.abc import Callable, Iterator, Sequence
from typing import NamedTuple

import config
from schemas import (
    CoverageEvent,
    DoneEvent,
    ErrorEvent,
    IncompleteEvent,
    MetaEvent,
    RestartEvent,
    StatusEvent,
    StreamEvent,
    TokenEvent,
    WarningEvent,
)

from . import model

# Prose runs about 3.6 characters per token, but a dense form runs about
# 2.9: a blank IRS 1040 with schedules came to 2.9, and the 3.5 that prose
# suggested under-counted it by 20 percent. 2.8 is the pessimistic end of
# what has been measured.
#
# This is only a first cut. Ollama has no tokenizer endpoint, so the real
# size of a prompt is unknowable until it has been sent, and the guard that
# matters is the overflow check on the counts that come back.
CHARS_PER_TOKEN: float = 2.8

# Tokens set aside for the system prompt, which is not part of the document
# budget but does count against the context window.
SYSTEM_RESERVE_TOKENS: int = 400

# Measured prompt evaluation rate on an M1 Pro, used only to tell the user
# roughly how long a large document will take before the first token.
PROMPT_EVAL_TOKENS_PER_SECOND: int = 166

# Below this, the wait is short enough that an estimate is noise.
ESTIMATE_THRESHOLD_TOKENS: int = 2000

# How many distinct keywords a type needs before it beats the generic
# checklist.
TYPE_MATCH_THRESHOLD: int = 2

STAGE_ANALYZING: str = "analyzing"
STAGE_READING_FIRST: str = "reading_first"
STAGE_READING_SECOND: str = "reading_second"
STAGE_COMPARING: str = "comparing"
STAGE_ANSWERING: str = "answering"

ANALYSIS_SYSTEM_PROMPT: str = (
    "You are a careful assistant that explains documents in plain language. "
    "Follow these rules without exception. "
    "Answer only from the document you are given. "
    "Never infer, estimate, or fill in a number that is not written there. "
    "Every figure, date, name, and deadline you report must be followed by a "
    "short quote of the exact wording from the document, in double quotes. "
    "This applies to forms and tables too: quote the line label and its "
    "wording rather than describing it in your own words. "
    "If the document does not say something, write 'not stated in the "
    "document' instead of guessing."
)

COMPARISON_SYSTEM_PROMPT: str = (
    "You are a careful assistant comparing two documents. "
    "You are given a summary of each one, already extracted from the "
    "originals. Put the two side by side point by point and say which "
    "differs and by how much. "
    "Use only what is in the two summaries. "
    "Keep the quotes that the summaries give you when you report a figure. "
    "If a point is missing from one summary, say so rather than guessing."
)

# Added to the prompt when the document did not fit. The banner tells the
# user the text was cut, but the model still described the whole document
# from the fragment it saw, listing two schedules out of eight as though
# that were the full contents.
FRAGMENT_INSTRUCTION: str = (
    "Important: you are seeing only the beginning of a longer document. The "
    "rest was cut off and you cannot see it. Scope every statement to what "
    "is shown above. Do not describe what the document contains as a whole, "
    "and do not present a list of its sections or attachments as complete."
)

LENGTH_DETAIL: str = (
    "The answer reached the output limit and stopped early. What is shown "
    "was checked against the document, but the rest of the answer is "
    "missing."
)

INTERRUPTED_DETAIL: str = (
    "The answer stopped partway through, so the quote check did not run. "
    "Nothing above has been checked against the document."
)

EMPTY_ANSWER_DETAIL: str = (
    "The local model returned an empty answer. If thinking has been turned "
    "on, the reasoning may have used the whole token budget."
)

OVERFLOW_DETAIL: str = (
    "This document does not fit in the model's context window, even after a "
    "second attempt with a shorter excerpt. The model was working from a "
    "silently cut down view of it and may have invented the parts it could "
    "not see. Do not rely on this answer."
)

RESTART_MESSAGE: str = (
    "That attempt used more context than the model can hold, so the start "
    "of the document was dropped and the answer could not be trusted. "
    "Starting again with a shorter excerpt. This doubles the wait."
)

RETRY_NOTE: str = (
    "The first attempt overflowed the model's context window and was "
    "discarded. This answer is the second attempt, made from a shorter "
    "excerpt of the document."
)

CHECKLISTS: dict[str, tuple[str, ...]] = {
    "job_offer": (
        "Base salary, and how often it is paid",
        "Bonuses, signing or annual, and any condition to repay them",
        "Equity, how much, over what schedule, and any cliff",
        "Start date, and any deadline to accept the offer",
        "How employment can end, notice period, at-will status",
        "Benefits, and when they start",
    ),
    "lease": (
        "Monthly rent, when it is due, and any late fee",
        "Security deposit, how much, and what returns it",
        "Lease term, start and end dates",
        "Renewal terms, and the penalty for leaving early",
        "What the tenant pays beyond rent, utilities and maintenance",
        "Restrictions on pets, guests, or subletting",
    ),
    "generic": (
        "What kind of document this is, and who the parties are",
        "Every amount of money, and what each one is for",
        "Every date and deadline",
        "What each party is obliged to do",
        "Anything unusual, one sided, or easy to miss",
    ),
}

# Document kinds this tool recognizes but does not handle well. Detection is
# kept deliberately: dropping the claim from the documentation does not stop
# anyone uploading a 1040, and quietly doing a poor job of it is the failure
# this project has spent its whole history designing against. A recognized
# but unsupported document gets the generic checklist and a plain notice.
UNSUPPORTED_TYPES: frozenset[str] = frozenset({"tax_return"})

TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "job_offer": (
        "base salary",
        "signing bonus",
        "vesting",
        "at-will",
        "offer of employment",
        "restricted stock",
        "equity grant",
        "annual bonus",
    ),
    "lease": (
        "tenant",
        "landlord",
        "security deposit",
        "premises",
        "monthly rent",
        "lease term",
        "sublet",
    ),
    "tax_return": (
        "adjusted gross income",
        "taxable income",
        "form 1040",
        "withholding",
        "filing status",
        "internal revenue",
        "refund",
    ),
}

# Curly double quotes are mapped to straight ones before matching, so a
# quote is still found when the model writes typographic ones. Built from
# code points to keep this file plain ASCII.
CURLY_DOUBLE_QUOTES: dict[int, str] = {0x201C: '"', 0x201D: '"'}

QUOTE_PATTERN = re.compile(r'"([^"]{4,})"')

# Markdown list markers are stripped before counting figures, so bullet
# numbering is not mistaken for a figure the model reported.
LIST_MARKER_PATTERN = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+")

# A number, with optional thousands separators, decimals, and a trailing
# letter for form line labels such as 1z or 11b.
FIGURE_PATTERN = re.compile(r"\b\d[\d,]*(?:\.\d+)?[a-z]?\b")

# Everything that is not a word character or a space, dropped before a quote
# is matched against its source. See normalize_for_matching.
PUNCTUATION_PATTERN = re.compile(r"[^a-z0-9 ]+")

# The phrase the system prompt tells the model to use for a point the
# document does not cover. The model often puts it in quotes, which makes it
# look like a quotation from the document that cannot be found there.
NOT_STATED_PREFIX: str = "not stated"


class Coverage(NamedTuple):
    """How many of the figures in an answer carried a supporting quote.

    Approximate on purpose. The figure count comes from a regular expression
    over the answer, which cannot tell a salary from a form line label.
    """

    figures: int
    quoted: int


class StageResult:
    """How one streamed model call ended.

    interrupted and failure both mean the call raised. They are separated by
    whether any text had already reached the reader: a failure with nothing
    on screen is an error, while a failure partway through leaves unverified
    text visible and has to say so.
    """

    def __init__(self) -> None:
        self.text: str = ""
        self.source: str = ""
        self.cut_off: bool = False
        self.interrupted: bool = False
        self.failure: str | None = None
        self.prompt_tokens: int = 0
        self.eval_tokens: int = 0
        self.retried: bool = False
        self.overflowed: bool = False

    def reset_output(self) -> None:
        """Clear what one attempt produced, keeping the retry bookkeeping."""
        self.text = ""
        self.cut_off = False
        self.interrupted = False
        self.failure = None
        self.prompt_tokens = 0
        self.eval_tokens = 0


def estimate_tokens(text: str) -> int:
    """Estimate how many tokens a piece of text will use."""
    return int(len(text) / CHARS_PER_TOKEN)


def detect_document_type(text: str) -> str:
    """Guess the document type from its wording.

    Keyword scoring rather than a model call, because it is instant, gives
    the same answer every time, and can be tested without Ollama.
    """
    lowered = text.lower()
    best_type = "generic"
    best_score = 0
    for name, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in lowered)
        if score > best_score:
            best_type = name
            best_score = score
    if best_score < TYPE_MATCH_THRESHOLD:
        return "generic"
    return best_type


def is_unsupported(document_type: str) -> bool:
    """Report whether this kind of document is out of scope."""
    return document_type in UNSUPPORTED_TYPES


def truncate_to_budget(text: str, max_tokens: int) -> tuple[str, bool]:
    """Cut text down to a token budget, reporting whether anything was cut."""
    if estimate_tokens(text) <= max_tokens:
        return text, False
    limit = int(max_tokens * CHARS_PER_TOKEN)
    return text[:limit].rstrip(), True


def context_overflowed(result: StageResult) -> bool:
    """Report whether the model lost part of its prompt to the window.

    Two ways it happens, both silent. If the prompt alone is larger than the
    window, Ollama pins prompt_eval_count to num_ctx and discards the front.
    If the prompt fits but prompt plus output crosses the window, the context
    shifts during generation and the front is evicted mid answer. Measured on
    qwen3:8b, both leave done_reason as "stop" and the model fabricates
    whatever it can no longer see.
    """
    if result.prompt_tokens <= 0:
        return False
    if result.prompt_tokens >= config.OLLAMA_NUM_CTX:
        return True
    return result.prompt_tokens + result.eval_tokens > config.OLLAMA_NUM_CTX


def measured_budget_chars(sent_chars: int, prompt_tokens: int) -> int:
    """Work out how many prompt characters fit, from what a call really used.

    This replaces the estimate with a measurement. The ratio comes from the
    attempt that just overflowed, so it is correct for this document rather
    than for documents in general.
    """
    if prompt_tokens <= 0:
        return sent_chars
    ratio = sent_chars / prompt_tokens
    allowed = (
        config.OLLAMA_NUM_CTX - config.OLLAMA_NUM_PREDICT - SYSTEM_RESERVE_TOKENS
    )
    return max(1, int(allowed * ratio))


def describe_wait(text: str) -> str:
    """Say how long the first text will take, when the wait is long enough.

    Prompt evaluation happens before any token can be produced, so on a large
    document the stream shows nothing for most of a minute. The estimate is
    rough by construction and is worded that way.
    """
    tokens = estimate_tokens(text)
    if tokens < ESTIMATE_THRESHOLD_TOKENS:
        return "Reading the document"
    seconds = round(tokens / PROMPT_EVAL_TOKENS_PER_SECOND / 5) * 5
    return (
        f"Reading a long document, roughly {tokens:,} tokens. "
        f"The first text should appear in about {seconds} seconds"
    )


def straighten_quotes(text: str) -> str:
    """Replace typographic double quotes with straight ones."""
    return text.translate(CURLY_DOUBLE_QUOTES)


def normalize_for_matching(text: str) -> str:
    """Reduce text to what a quote and its source must share to be the same.

    Case, whitespace, and punctuation are all removed, which leaves words and
    figures. Those are what a quote is actually claiming; the rest is layout.

    Punctuation removal is what handles the dot leaders on a form line, as in
    "Add lines 16 and 17 . . . . . . 18". They sit between a label and its
    answer box, carry no meaning, and are not reproduced when the model
    quotes the line, so a substantively verbatim quote failed to match.

    A formatting difference is not a fabrication. Treating it as one produces
    warnings that teach people to ignore warnings, which costs more than the
    warning was ever worth.
    """
    text = straighten_quotes(text).lower()
    text = PUNCTUATION_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def real_quotes(answer: str) -> list[str]:
    """Quoted spans in an answer, excluding the not-stated marker."""
    return [
        quote
        for quote in QUOTE_PATTERN.findall(straighten_quotes(answer))
        if not normalize_for_matching(quote).startswith(NOT_STATED_PREFIX)
    ]


def verify_quotes(answer: str, source: str) -> list[str]:
    """Return the quotes in an answer that do not appear in the source.

    This is the check behind the grounding rules in the system prompt. A
    model that invents a salary figure usually invents the quote alongside
    it, and an invented quote is something we can actually detect.

    The not-stated marker is skipped. It is the model following instructions,
    not quoting the document, and flagging it would put a false warning on
    almost every answer.
    """
    haystack = normalize_for_matching(source)
    unverified: list[str] = []
    for quote in real_quotes(answer):
        needle = normalize_for_matching(quote)
        if needle and needle not in haystack:
            unverified.append(quote.strip())
    return unverified


def measure_coverage(answer: str) -> Coverage:
    """Count figures in an answer and how many sit inside a quote.

    Reported on every answer, not only when a quote fails. On a dense form
    the model paraphrases instead of quoting, which produces an answer with
    no quotes at all: verify_quotes passes because it has nothing to check,
    and that reads on screen exactly like a fully verified answer.
    """
    quoted_blob = " ".join(real_quotes(answer))
    body = LIST_MARKER_PATTERN.sub("", straighten_quotes(answer))
    figures = set(FIGURE_PATTERN.findall(body))
    quoted = {figure for figure in figures if figure in quoted_blob}
    return Coverage(figures=len(figures), quoted=len(quoted))


def format_checklist(document_type: str) -> str:
    """Render the checklist for a document type as prompt lines."""
    items = CHECKLISTS.get(document_type, CHECKLISTS["generic"])
    return "\n".join(f"- {item}" for item in items)


def fragment_note(truncated: bool) -> str:
    """The scoping instruction, when the model is seeing only a fragment."""
    return f"\n\n{FRAGMENT_INSTRUCTION}" if truncated else ""


def build_analysis_prompt(
    text: str, document_type: str, truncated: bool = False
) -> str:
    """Build the analysis prompt, document first so the prefix caches."""
    return (
        f"Document:\n{text}{fragment_note(truncated)}\n\n"
        "Explain this document in plain language. Cover each of these "
        "points, and write 'not stated in the document' for any the "
        f"document does not answer:\n{format_checklist(document_type)}"
    )


def build_digest_prompt(
    text: str, document_type: str, truncated: bool = False
) -> str:
    """Build the prompt that reduces one document to its key fields."""
    return (
        f"Document:\n{text}{fragment_note(truncated)}\n\n"
        "Give one short line for each point below, in the order listed. "
        "Put the figure first, then the exact quote from the document that "
        "supports it. Write 'not stated in the document' for any point the "
        f"document does not answer:\n{format_checklist(document_type)}"
    )


def build_comparison_prompt(first_digest: str, second_digest: str) -> str:
    """Build the prompt that puts two document summaries side by side."""
    return (
        f"First document:\n{first_digest}\n\n"
        f"Second document:\n{second_digest}\n\n"
        "Compare the two point by point. For each point, say what each "
        "document offers and which is better, or say that they match. "
        "Finish with the differences that matter most."
    )


def build_question_prompt(
    text: str,
    question: str,
    history: Sequence[tuple[str, str]],
    truncated: bool = False,
) -> str:
    """Build a follow-up prompt: document, then history, then the question.

    The document stays at the front and unchanged between questions, so
    Ollama's prompt cache covers it. Measured, that turns a 19 second prompt
    evaluation into 0.05 seconds on the second question.
    """
    parts = [f"Document:\n{text}{fragment_note(truncated)}"]
    for asked, answered in history:
        parts.append(f"Earlier question: {asked}\nEarlier answer: {answered}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def stream_stage(
    prompt: str, system: str, stage: str, result: StageResult
) -> Iterator[StreamEvent]:
    """Stream one model call as token events, recording how it ended.

    Nothing is raised out of here. The caller decides what a failure means
    based on whether any text had already been sent.
    """
    try:
        for chunk in model.generate_stream(prompt, system):
            if chunk.text:
                result.text += chunk.text
                yield TokenEvent(stage=stage, text=chunk.text)
            if chunk.done_reason == "length":
                result.cut_off = True
            if chunk.prompt_tokens:
                result.prompt_tokens = chunk.prompt_tokens
                result.eval_tokens = chunk.eval_tokens
    except model.ModelError as problem:
        if result.text:
            result.interrupted = True
        else:
            result.failure = str(problem)


def stream_generation(
    document: str,
    build_prompt: Callable[[str, bool], str],
    system: str,
    stage: str,
    result: StageResult,
) -> Iterator[StreamEvent]:
    """Stream one generation, retrying once from a shorter excerpt on overflow.

    Retried at most once. If the second attempt also overflows the window it
    is reported rather than retried again, because a third attempt would only
    make the user wait longer for an answer that still cannot be trusted.
    """
    trimmed, truncated = truncate_to_budget(document, config.DOCUMENT_TOKEN_BUDGET)
    result.source = trimmed
    yield from stream_stage(build_prompt(trimmed, truncated), system, stage, result)

    if result.failure is not None or result.interrupted:
        return
    if not context_overflowed(result):
        return

    # Size the second attempt from what the first one actually used, rather
    # than from the estimate that just proved wrong.
    prompt = build_prompt(trimmed, truncated)
    overhead = len(prompt) - len(trimmed)
    allowed = measured_budget_chars(len(prompt), result.prompt_tokens) - overhead
    shorter = document[: max(1, allowed)].rstrip()

    yield RestartEvent(reason="context_overflow", message=RESTART_MESSAGE)
    result.reset_output()
    result.retried = True
    result.source = shorter
    yield from stream_stage(build_prompt(shorter, True), system, stage, result)

    if result.failure is None and not result.interrupted:
        result.overflowed = context_overflowed(result)


def finish(result: StageResult) -> Iterator[StreamEvent]:
    """Emit the closing events for a finished stage.

    Exactly one terminal event is produced: error, incomplete, or done. The
    quote check runs only when there is a complete answer to check, so an
    interrupted answer carries no warning and says as much.
    """
    if result.failure is not None:
        yield ErrorEvent(detail=result.failure)
        return
    if result.interrupted:
        yield IncompleteEvent(reason="interrupted", detail=INTERRUPTED_DETAIL)
        return
    if not result.text.strip():
        yield ErrorEvent(detail=EMPTY_ANSWER_DETAIL)
        return

    unverified = verify_quotes(result.text, result.source)
    if unverified:
        yield WarningEvent(unverified=unverified)

    coverage = measure_coverage(result.text)
    yield CoverageEvent(figures=coverage.figures, quoted=coverage.quoted)

    if result.overflowed:
        yield IncompleteEvent(reason="context_overflow", detail=OVERFLOW_DETAIL)
        return
    if result.cut_off:
        yield IncompleteEvent(reason="length", detail=LENGTH_DETAIL)
        return
    yield DoneEvent()


def stream_analysis(text: str, document_ids: list[str]) -> Iterator[StreamEvent]:
    """Analyze one document, streaming the answer as it is produced."""
    document_type = detect_document_type(text)
    trimmed, truncated = truncate_to_budget(text, config.DOCUMENT_TOKEN_BUDGET)

    yield MetaEvent(
        document_ids=document_ids,
        document_type=document_type,
        truncated=truncated,
        unsupported_type=is_unsupported(document_type),
    )
    yield StatusEvent(stage=STAGE_ANALYZING, message=describe_wait(trimmed))

    result = StageResult()
    yield from stream_generation(
        text,
        lambda body, cut: build_analysis_prompt(body, document_type, cut),
        ANALYSIS_SYSTEM_PROMPT,
        STAGE_ANALYZING,
        result,
    )
    yield from finish(result)


def stream_comparison(
    first_text: str, second_text: str, document_ids: list[str]
) -> Iterator[StreamEvent]:
    """Compare two documents, streaming all three model calls.

    Each document is digested on its own first, then the two digests are
    compared. Two full documents in one prompt would be about 7000 tokens,
    which barely fits the context window, and an 8B model given both at once
    tends to summarize them in turn instead of lining the figures up.

    The digests stream too. They take most of the eighty seconds, so leaving
    them silent would mean a minute of nothing on screen.
    """
    document_type = detect_document_type(f"{first_text}\n{second_text}")
    budget = config.DOCUMENT_TOKEN_BUDGET
    _, first_cut = truncate_to_budget(first_text, budget)
    _, second_cut = truncate_to_budget(second_text, budget)

    yield MetaEvent(
        document_ids=document_ids,
        document_type=document_type,
        truncated=first_cut or second_cut,
        unsupported_type=is_unsupported(document_type),
    )

    digests: list[str] = []
    sources: list[str] = []
    for text, stage, label in (
        (first_text, STAGE_READING_FIRST, "first"),
        (second_text, STAGE_READING_SECOND, "second"),
    ):
        trimmed, _ = truncate_to_budget(text, budget)
        yield StatusEvent(
            stage=stage, message=f"Reading the {label} document. {describe_wait(trimmed)}"
        )
        result = StageResult()
        yield from stream_generation(
            text,
            lambda body, cut: build_digest_prompt(body, document_type, cut),
            ANALYSIS_SYSTEM_PROMPT,
            stage,
            result,
        )
        if result.failure is not None:
            yield ErrorEvent(detail=result.failure)
            return
        if result.interrupted:
            yield IncompleteEvent(reason="interrupted", detail=INTERRUPTED_DETAIL)
            return
        if result.overflowed:
            yield IncompleteEvent(reason="context_overflow", detail=OVERFLOW_DETAIL)
            return
        digests.append(result.text)
        sources.append(result.source)

    yield StatusEvent(stage=STAGE_COMPARING, message="Comparing the two")
    result = StageResult()
    result.source = "\n".join(sources)
    yield from stream_stage(
        build_comparison_prompt(digests[0], digests[1]),
        COMPARISON_SYSTEM_PROMPT,
        STAGE_COMPARING,
        result,
    )
    yield from finish(result)


def stream_answer(
    text: str, question: str, history: Sequence[tuple[str, str]] = ()
) -> Iterator[StreamEvent]:
    """Answer a follow-up question about a document, streaming the answer."""
    trimmed, _ = truncate_to_budget(text, config.DOCUMENT_TOKEN_BUDGET)
    yield StatusEvent(stage=STAGE_ANSWERING, message=describe_wait(trimmed))

    result = StageResult()
    yield from stream_generation(
        text,
        lambda body, cut: build_question_prompt(body, question, history, cut),
        ANALYSIS_SYSTEM_PROMPT,
        STAGE_ANSWERING,
        result,
    )
    yield from finish(result)
