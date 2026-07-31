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
    """

    event: Literal["meta"] = "meta"
    document_ids: list[str]
    document_type: str
    truncated: bool


class TokenEvent(BaseModel):
    """One chunk of generated text, tagged with the phase that produced it."""

    event: Literal["token"] = "token"
    stage: str
    text: str


class WarningEvent(BaseModel):
    """Quotes in the finished answer that are not in the source document."""

    event: Literal["warning"] = "warning"
    unverified: list[str]


class DoneEvent(BaseModel):
    """The answer finished normally and the quote check ran."""

    event: Literal["done"] = "done"


class IncompleteEvent(BaseModel):
    """The answer stopped early.

    Two reasons, and they differ in how much the reader can trust what is on
    screen. "length" means the output cap was reached: the text stops mid
    thought, but the quote check still ran on what arrived. "interrupted"
    means generation broke partway: the quote check never ran, so nothing on
    screen has been verified.
    """

    event: Literal["incomplete"] = "incomplete"
    reason: Literal["length", "interrupted"]
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
    | DoneEvent
    | IncompleteEvent
    | ErrorEvent
)
