"""Analyze document text with the local model.

Every function here reads the document text as extracted, with nothing
removed. The text goes to the local Ollama process and nowhere else.
"""

from . import model

# TODO: replace these with real prompts once the pipeline runs end to end.
ANALYSIS_SYSTEM_PROMPT: str = (
    "You are a careful assistant that explains documents in plain language. "
    "Answer only from the document you are given, and say so plainly when "
    "something is not in it."
)


def analyze(text: str) -> str:
    """Produce a plain-language analysis of one document."""
    # TODO: build a prompt that asks for the document type, the key terms, and
    # anything unusual, then send it to the local model.
    raise NotImplementedError("document analysis is not implemented yet")


def compare(first_text: str, second_text: str) -> str:
    """Compare two documents side by side."""
    # TODO: build a prompt that lines the two documents up on shared terms,
    # for example salary, equity, and notice period on two job offers.
    raise NotImplementedError("document comparison is not implemented yet")


def answer_question(text: str, question: str) -> str:
    """Answer a follow-up question about a document."""
    # TODO: pass the document text as context with the question, and tell the
    # model to say so plainly when the answer is not in the document.
    raise NotImplementedError("question answering is not implemented yet")
