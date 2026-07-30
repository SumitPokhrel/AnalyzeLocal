"""Request and response models shared by the API routes and the pipeline."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Server status and local model availability."""

    status: str
    configured_model: str
    ollama_available: bool


class AnalyzeResponse(BaseModel):
    """Result of running one document through the pipeline."""

    document_id: str
    analysis: str


class CompareResponse(BaseModel):
    """Result of comparing two documents side by side."""

    document_ids: list[str]
    comparison: str


class QuestionRequest(BaseModel):
    """A follow-up question about a document already held in memory."""

    document_id: str
    question: str


class QuestionResponse(BaseModel):
    """The model answer to a follow-up question."""

    answer: str
