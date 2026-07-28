"""Analyze redacted text with the local model.

Every function here takes text that has already been through redact.py. Do
not call anything in this module with raw document text.
"""

from . import model

# TODO: replace these with real prompts once the pipeline runs end to end.
ANALYSIS_SYSTEM_PROMPT = (
    "You are a careful assistant that explains documents in plain language. "
    "The text has been redacted, and placeholders such as [PERSON_1] stand in "
    "for removed personal details. Never guess what a placeholder hides."
)


def analyze(redacted_text: str) -> str:
    """Produce a plain-language analysis of one redacted document."""
    # TODO: build a prompt that asks for the document type, the key terms, and
    # anything unusual, then send it to the local model.
    raise NotImplementedError("document analysis is not implemented yet")


def compare(first_redacted_text: str, second_redacted_text: str) -> str:
    """Compare two redacted documents side by side."""
    # TODO: build a prompt that lines the two documents up on shared terms,
    # for example salary, equity, and notice period on two job offers.
    raise NotImplementedError("document comparison is not implemented yet")


def answer_question(redacted_text: str, question: str) -> str:
    """Answer a follow-up question about a redacted document."""
    # TODO: pass the redacted text as context with the question, and tell the
    # model to say so plainly when the answer is not in the document.
    raise NotImplementedError("question answering is not implemented yet")
