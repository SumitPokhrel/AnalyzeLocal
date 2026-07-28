"""Tests for pipeline/extract.py."""

from pathlib import Path

import pytest

from pipeline.extract import ExtractionError, extract_text, normalize_whitespace


def test_utf8_text(documents: dict[str, Path]) -> None:
    """A plain UTF-8 file comes through with its content intact."""
    text = extract_text(documents["utf8"])
    assert "Base salary: 145000 USD" in text
    assert text == text.strip()


def test_utf16_text_with_byte_order_mark(documents: dict[str, Path]) -> None:
    """A UTF-16 file with a byte order mark is decoded correctly."""
    assert "Base: 145000" in extract_text(documents["utf16"])


def test_cp1252_is_not_decoded_as_utf16(documents: dict[str, Path]) -> None:
    """A cp1252 file is not silently mangled by a utf-16 attempt.

    Regression test. utf-16 without a byte order mark decodes almost any even
    length file into garbage rather than raising, so it must not sit in the
    plain fallback chain.
    """
    text = extract_text(documents["cp1252"])
    assert "Bonus" in text
    assert "target" in text
    assert "15%" in text


def test_utf8_byte_order_mark_is_stripped(documents: dict[str, Path]) -> None:
    """A UTF-8 byte order mark does not survive into the extracted text."""
    text = extract_text(documents["utf8_bom"])
    assert text.startswith("Salary")


def test_line_endings_and_blank_runs_normalized(documents: dict[str, Path]) -> None:
    """Carriage returns, trailing spaces, and blank line runs are cleaned up."""
    text = extract_text(documents["crlf"])
    assert "\r" not in text
    assert "\n\n\n" not in text
    assert "one   \n" not in text


def test_empty_text_file_rejected(documents: dict[str, Path]) -> None:
    """A file with nothing but whitespace is reported, not returned empty."""
    with pytest.raises(ExtractionError, match="empty"):
        extract_text(documents["empty_text"])


def test_pdf_text_layer(documents: dict[str, Path]) -> None:
    """Text is pulled from every page of a PDF."""
    text = extract_text(documents["pdf"])
    assert "base salary 145000 USD" in text
    assert "equity 4000 RSUs" in text


def test_pdf_pages_stay_in_order(documents: dict[str, Path]) -> None:
    """Pages are joined in reading order."""
    text = extract_text(documents["pdf"])
    assert text.index("Page one") < text.index("Page two")


def test_pdf_with_empty_password_opens(documents: dict[str, Path]) -> None:
    """A PDF encrypted with an empty password opens without prompting."""
    assert "145000" in extract_text(documents["empty_password_pdf"])


def test_scanned_pdf_rejected(documents: dict[str, Path]) -> None:
    """A PDF with no text layer says so instead of returning nothing."""
    with pytest.raises(ExtractionError, match="scan"):
        extract_text(documents["scanned_pdf"])


def test_password_protected_pdf_rejected(documents: dict[str, Path]) -> None:
    """A PDF with a real password gives a readable reason."""
    with pytest.raises(ExtractionError, match="password"):
        extract_text(documents["locked_pdf"])


def test_docx_paragraphs_and_tables(documents: dict[str, Path]) -> None:
    """Both paragraph text and table cells are extracted."""
    text = extract_text(documents["docx"])
    assert "Dear candidate," in text
    assert "145000 USD" in text
    assert "20000 USD" in text


def test_docx_keeps_document_order(documents: dict[str, Path]) -> None:
    """A table between two paragraphs stays between them.

    Regression test. python-docx exposes paragraphs and tables as separate
    collections, so reading them in sequence moves every table to the end.
    """
    text = extract_text(documents["docx"])
    assert (
        text.index("pleased to offer")
        < text.index("Base salary")
        < text.index("Please sign")
    )


def test_empty_docx_rejected(documents: dict[str, Path]) -> None:
    """A Word document with no content is reported."""
    with pytest.raises(ExtractionError, match="No text"):
        extract_text(documents["empty_docx"])


def test_invalid_docx_rejected(documents: dict[str, Path]) -> None:
    """A file that is not really a docx gives a readable reason."""
    with pytest.raises(ExtractionError, match="Word document"):
        extract_text(documents["fake_docx"])


def test_unsupported_extension_rejected() -> None:
    """An extension the pipeline does not handle raises ValueError."""
    with pytest.raises(ValueError, match="rtf"):
        extract_text(Path("something.rtf"))


def test_normalize_whitespace_is_idempotent() -> None:
    """Normalizing already normalized text changes nothing."""
    once = normalize_whitespace("a  \r\n\r\n\r\n\r\nb\n")
    assert normalize_whitespace(once) == once
