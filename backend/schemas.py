"""Request and response models shared by the API routes and the pipeline."""

from pydantic import BaseModel


class RedactionSpan(BaseModel):
    """One stretch of text that was replaced with a placeholder.

    The original value is included so the review step can show the user what
    was caught. It stays in memory on this machine and is never sent to the
    analysis step.
    """

    start: int
    end: int
    label: str
    placeholder: str
    source: str
    original: str


class RedactionResult(BaseModel):
    """Redacted text plus the list of what was replaced in it."""

    redacted_text: str
    spans: list[RedactionSpan]


class HealthResponse(BaseModel):
    """Server status and local model availability."""

    status: str
    configured_model: str
    ollama_available: bool


class AnalyzeResponse(BaseModel):
    """Result of running one document through the full pipeline."""

    document_id: str
    redacted_text: str
    spans: list[RedactionSpan]
    analysis: str


class CompareResponse(BaseModel):
    """Result of comparing two documents side by side."""

    document_ids: list[str]
    redacted_texts: list[str]
    spans: list[list[RedactionSpan]]
    comparison: str


class QuestionRequest(BaseModel):
    """A follow-up question about a document already held in memory."""

    document_id: str
    question: str


class QuestionResponse(BaseModel):
    """The model answer to a follow-up question."""

    answer: str
