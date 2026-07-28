"""Extract plain text from a document.

Parser packages are imported inside the functions that use them so the app
starts even before those packages are installed.
"""

import re
from pathlib import Path


def extract_text(path: Path) -> str:
    """Extract plain text from a PDF, docx, or plain text file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in (".txt", ".md"):
        return extract_plain_text(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_pdf(path: Path) -> str:
    """Extract text from a PDF file."""
    # TODO: read the pages with pypdf, pull text from each one, and join the
    # pages with blank lines. Decide what to do about scanned PDFs that have
    # no text layer, most likely a clear error rather than silent OCR.
    raise NotImplementedError("PDF extraction is not implemented yet")


def extract_docx(path: Path) -> str:
    """Extract text from a Word docx file."""
    # TODO: read paragraphs with python-docx. Tables carry salary and benefit
    # numbers in real offer letters, so pull those too.
    raise NotImplementedError("docx extraction is not implemented yet")


def extract_plain_text(path: Path) -> str:
    """Read a plain text or markdown file."""
    # TODO: decode as UTF-8 and fall back sensibly on other encodings.
    raise NotImplementedError("plain text extraction is not implemented yet")


def normalize_whitespace(text: str) -> str:
    """Collapse runs of blank lines and trailing spaces into a tidy form."""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
