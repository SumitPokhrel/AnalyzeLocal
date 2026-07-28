"""Redact personal information from extracted text.

Two passes run over the text. The first uses patterns and checksums for
structured items like SSNs and account numbers. The second uses a local
GLiNER model for unstructured items like names, addresses, and employers.

The redacted text produced here is the only thing analyze.py is allowed to
see.
"""

from typing import Any

# The return types come from schemas.py on purpose. The pipeline could define
# its own dataclasses and have the API layer convert them, but at this size
# that conversion layer would earn nothing.
from schemas import RedactionResult, RedactionSpan

# Entity types requested from the NER model. Kept here so the list is easy to
# tune once real documents are being tested.
NER_LABELS: tuple[str, ...] = (
    "person",
    "address",
    "organization",
    "employer",
    "phone number",
    "email address",
    "date of birth",
)

# Cached NER model instance. Loading is slow, so it happens once per process.
_ner_model: Any = None


def redact(text: str) -> RedactionResult:
    """Replace personal information in text with labelled placeholders."""
    # TODO: run both passes, merge the results, then apply placeholders.
    detections = find_pattern_matches(text) + find_ner_matches(text)
    merged = merge_overlapping(detections)
    return apply_placeholders(text, merged)


def find_pattern_matches(text: str) -> list[RedactionSpan]:
    """Find structured PII using regular expressions and checksums."""
    # TODO: cover SSN, EIN, bank and account numbers, credit card numbers,
    # emails, phone numbers, and dates. Validate the numeric ones with the
    # checksum helpers below so plain reference numbers are not redacted.
    raise NotImplementedError("pattern matching is not implemented yet")


def find_ner_matches(text: str) -> list[RedactionSpan]:
    """Find unstructured PII using the local NER model."""
    # TODO: load the model, run it over the text in chunks that respect its
    # context window, and convert its output into spans.
    raise NotImplementedError("NER matching is not implemented yet")


def load_ner_model() -> Any:
    """Load the local GLiNER model once and reuse it."""
    # TODO: import gliner here, load config.NER_MODEL_NAME, cache it in the
    # module level _ner_model, and return it.
    raise NotImplementedError("NER model loading is not implemented yet")


def is_valid_ssn(value: str) -> bool:
    """Report whether a nine digit string is a plausible US SSN."""
    # TODO: reject area 000, 666, and 900 to 999, group 00, and serial 0000.
    raise NotImplementedError("SSN validation is not implemented yet")


def is_valid_ein(value: str) -> bool:
    """Report whether a nine digit string is a plausible US EIN."""
    # TODO: check the prefix against the set of assigned IRS campus prefixes.
    raise NotImplementedError("EIN validation is not implemented yet")


def passes_luhn(value: str) -> bool:
    """Report whether a digit string passes the Luhn checksum."""
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) < 2:
        return False
    total = 0
    for index, digit in enumerate(reversed(digits)):
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def merge_overlapping(spans: list[RedactionSpan]) -> list[RedactionSpan]:
    """Resolve spans that overlap, keeping the more specific detection."""
    # TODO: sort by start offset, then drop or merge overlaps. Pattern matches
    # should generally win over NER guesses on the same stretch of text.
    raise NotImplementedError("span merging is not implemented yet")


def apply_placeholders(text: str, spans: list[RedactionSpan]) -> RedactionResult:
    """Replace each span with a stable placeholder such as [PERSON_1]."""
    # TODO: walk the spans back to front so earlier offsets stay valid, and
    # reuse the same placeholder for repeated values so the model can still
    # tell that two mentions refer to the same person.
    raise NotImplementedError("placeholder substitution is not implemented yet")
