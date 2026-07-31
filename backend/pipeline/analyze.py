"""Analyze document text with the local model.

Every function here reads the document text as extracted, with nothing
removed. The text goes to the local Ollama process and nowhere else.

Work is produced as a stream of events rather than a finished string, so the
interface can show text as it arrives. A first analysis takes about thirty
seconds and a comparison about eighty, which is too long to show nothing.

Two things shape how the prompts are built. The document always comes first,
because Ollama caches the KV prefix and an unchanged document then costs
almost nothing to re-send on a follow-up question. And every figure the model
reports has to carry a quote, so verify_quotes can check it against the
source once generation finishes.
"""

import re
from collections.abc import Iterator, Sequence

import config
from schemas import (
    DoneEvent,
    ErrorEvent,
    IncompleteEvent,
    MetaEvent,
    StatusEvent,
    StreamEvent,
    TokenEvent,
    WarningEvent,
)

from . import model

# Measured on a sample document: 12960 characters came to 3559 tokens, about
# 3.6 characters per token. Rounding down to 3.5 makes the estimate slightly
# pessimistic, which is the safe direction for a budget.
CHARS_PER_TOKEN: float = 3.5

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
    "tax_return": (
        "Tax year and filing status",
        "Total income and adjusted gross income",
        "Taxable income and total tax",
        "Withholding and any payments already made",
        "Refund due or balance owed",
        "Notable credits, deductions, or attached schedules",
    ),
    "generic": (
        "What kind of document this is, and who the parties are",
        "Every amount of money, and what each one is for",
        "Every date and deadline",
        "What each party is obliged to do",
        "Anything unusual, one sided, or easy to miss",
    ),
}

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

# The phrase the system prompt tells the model to use for a point the
# document does not cover. The model often puts it in quotes, which makes it
# look like a quotation from the document that cannot be found there.
NOT_STATED_PREFIX: str = "not stated"


class StageResult:
    """How one streamed model call ended.

    interrupted and failure both mean the call raised. They are separated by
    whether any text had already reached the reader: a failure with nothing
    on screen is an error, while a failure partway through leaves unverified
    text visible and has to say so.
    """

    def __init__(self) -> None:
        self.text: str = ""
        self.cut_off: bool = False
        self.interrupted: bool = False
        self.failure: str | None = None


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


def truncate_to_budget(text: str, max_tokens: int) -> tuple[str, bool]:
    """Cut text down to a token budget, reporting whether anything was cut."""
    if estimate_tokens(text) <= max_tokens:
        return text, False
    limit = int(max_tokens * CHARS_PER_TOKEN)
    return text[:limit].rstrip(), True


def straighten_quotes(text: str) -> str:
    """Replace typographic double quotes with straight ones."""
    return text.translate(CURLY_DOUBLE_QUOTES)


def normalize_for_matching(text: str) -> str:
    """Flatten whitespace and case so a quote can be found in the source."""
    return re.sub(r"\s+", " ", text).strip().lower()


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
    for quote in QUOTE_PATTERN.findall(straighten_quotes(answer)):
        needle = normalize_for_matching(quote)
        if not needle or needle.startswith(NOT_STATED_PREFIX):
            continue
        if needle not in haystack:
            unverified.append(quote.strip())
    return unverified


def format_checklist(document_type: str) -> str:
    """Render the checklist for a document type as prompt lines."""
    items = CHECKLISTS.get(document_type, CHECKLISTS["generic"])
    return "\n".join(f"- {item}" for item in items)


def build_analysis_prompt(text: str, document_type: str) -> str:
    """Build the analysis prompt, document first so the prefix caches."""
    return (
        f"Document:\n{text}\n\n"
        "Explain this document in plain language. Cover each of these "
        "points, and write 'not stated in the document' for any the "
        f"document does not answer:\n{format_checklist(document_type)}"
    )


def build_digest_prompt(text: str, document_type: str) -> str:
    """Build the prompt that reduces one document to its key fields."""
    return (
        f"Document:\n{text}\n\n"
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
    text: str, question: str, history: Sequence[tuple[str, str]]
) -> str:
    """Build a follow-up prompt: document, then history, then the question.

    The document stays at the front and unchanged between questions, so
    Ollama's prompt cache covers it. Measured, that turns a 19 second prompt
    evaluation into 0.05 seconds on the second question.
    """
    parts = [f"Document:\n{text}"]
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
    except model.ModelError as problem:
        if result.text:
            result.interrupted = True
        else:
            result.failure = str(problem)


def finish(result: StageResult, source: str) -> Iterator[StreamEvent]:
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

    unverified = verify_quotes(result.text, source)
    if unverified:
        yield WarningEvent(unverified=unverified)

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
    )
    yield StatusEvent(stage=STAGE_ANALYZING, message="Reading the document")

    result = StageResult()
    yield from stream_stage(
        build_analysis_prompt(trimmed, document_type),
        ANALYSIS_SYSTEM_PROMPT,
        STAGE_ANALYZING,
        result,
    )
    yield from finish(result, trimmed)


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
    first_trimmed, first_cut = truncate_to_budget(first_text, budget)
    second_trimmed, second_cut = truncate_to_budget(second_text, budget)

    yield MetaEvent(
        document_ids=document_ids,
        document_type=document_type,
        truncated=first_cut or second_cut,
    )

    digests: list[str] = []
    for text, stage, message in (
        (first_trimmed, STAGE_READING_FIRST, "Reading the first document"),
        (second_trimmed, STAGE_READING_SECOND, "Reading the second document"),
    ):
        yield StatusEvent(stage=stage, message=message)
        result = StageResult()
        yield from stream_stage(
            build_digest_prompt(text, document_type),
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
        digests.append(result.text)

    yield StatusEvent(stage=STAGE_COMPARING, message="Comparing the two")
    result = StageResult()
    yield from stream_stage(
        build_comparison_prompt(digests[0], digests[1]),
        COMPARISON_SYSTEM_PROMPT,
        STAGE_COMPARING,
        result,
    )
    yield from finish(result, f"{first_trimmed}\n{second_trimmed}")


def stream_answer(
    text: str, question: str, history: Sequence[tuple[str, str]] = ()
) -> Iterator[StreamEvent]:
    """Answer a follow-up question about a document, streaming the answer."""
    trimmed, _ = truncate_to_budget(text, config.DOCUMENT_TOKEN_BUDGET)
    yield StatusEvent(stage=STAGE_ANSWERING, message="Looking it up")

    result = StageResult()
    yield from stream_stage(
        build_question_prompt(trimmed, question, history),
        ANALYSIS_SYSTEM_PROMPT,
        STAGE_ANSWERING,
        result,
    )
    yield from finish(result, trimmed)
