"""Request and response models shared by the API routes and the pipeline.

The analyze, compare, and question routes stream newline delimited JSON.
Every line is one of the event models below, discriminated by the event
field. frontend/src/api.ts mirrors these by hand.
"""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Server status and local model availability."""

    status: str
    configured_model: str
    ollama_available: bool


class QuestionRequest(BaseModel):
    """A follow-up question about a document already held in memory."""

    document_id: str
    question: str


class StatusEvent(BaseModel):
    """Which phase of the work has just started."""

    event: Literal["status"] = "status"
    stage: str
    message: str


class MetaEvent(BaseModel):
    """What the pipeline worked out before calling the model.

    document_ids always holds one id per document, so the shape does not
    change between the analyze and compare routes.

    unsupported_type says the document was recognized as a kind this tool
    does not handle well. It is a separate field from truncated because the
    two are different problems: one is this document being too long, the
    other is this whole class of document being out of scope.
    """

    event: Literal["meta"] = "meta"
    document_ids: list[str]
    document_type: str
    truncated: bool
    unsupported_type: bool = False


class TokenEvent(BaseModel):
    """One chunk of generated text, tagged with the phase that produced it."""

    event: Literal["token"] = "token"
    stage: str
    text: str


class WarningEvent(BaseModel):
    """Quotes in the finished answer that are not in the source document."""

    event: Literal["warning"] = "warning"
    unverified: list[str]


class CoverageEvent(BaseModel):
    """How much of the answer could be checked against the document.

    Sent on every finished answer, not only when something fails. Without
    it, an answer where nothing was checkable looks exactly like one where
    everything checked out.

    The counts come from a regular expression over the answer text, so they
    are approximate and must be presented that way.
    """

    event: Literal["coverage"] = "coverage"
    figures: int
    quoted: int


class RestartEvent(BaseModel):
    """The answer is being generated again from a shorter excerpt.

    Sent when the first attempt overflowed the context window. Anything
    already streamed came from a run that silently lost the front of the
    document, so the reader has to discard it. This is both the signal to
    clear what is on screen and the explanation for why the wait doubled.
    """

    event: Literal["restart"] = "restart"
    reason: Literal["context_overflow"]
    message: str


class DoneEvent(BaseModel):
    """The answer finished normally and the quote check ran."""

    event: Literal["done"] = "done"


class IncompleteEvent(BaseModel):
    """The answer stopped early.

    Three reasons, differing in how much the reader can trust what is on
    screen. "length" means the output cap was reached: the text stops mid
    thought, but the quote check still ran on what arrived. "interrupted"
    means generation broke partway: the quote check never ran, so nothing on
    screen has been verified. "context_overflow" means the document did not
    fit even after a second, shorter attempt, so the model was working from
    a silently truncated view of it.
    """

    event: Literal["incomplete"] = "incomplete"
    reason: Literal["length", "interrupted", "context_overflow"]
    detail: str


class ErrorEvent(BaseModel):
    """The work failed before any answer text was produced."""

    event: Literal["error"] = "error"
    detail: str


StreamEvent = (
    StatusEvent
    | MetaEvent
    | TokenEvent
    | WarningEvent
    | CoverageEvent
    | RestartEvent
    | DoneEvent
    | IncompleteEvent
    | ErrorEvent
)
