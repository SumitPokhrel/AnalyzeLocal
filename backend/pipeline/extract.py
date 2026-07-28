"""Extract plain text from a document.

Parser packages are imported inside the functions that use them so the app
starts even before those packages are installed.
"""

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ExtractionError(Exception):
    """Raised when a document cannot be turned into plain text.

    This covers expected user problems, such as a scanned PDF or a password
    protected file, rather than bugs. The message is shown to the user, so
    keep it plain and say what to do next.
    """


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
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
    except PdfReadError as problem:
        raise ExtractionError(f"This PDF could not be read: {problem}") from problem

    if reader.is_encrypted:
        # Payroll and bank PDFs are often encrypted with an empty password,
        # which opens without asking the user for anything. A real password
        # cannot be recovered, so say so plainly.
        try:
            opened = reader.decrypt("")
        except (PdfReadError, NotImplementedError) as problem:
            raise ExtractionError(
                f"This PDF uses an encryption that cannot be opened: {problem}"
            ) from problem
        if not opened:
            raise ExtractionError(
                "This PDF is password protected. Remove the password, then "
                "try again."
            )

    pages: list[str] = []
    try:
        for page in reader.pages:
            pages.append(page.extract_text() or "")
    except (PdfReadError, NotImplementedError) as problem:
        raise ExtractionError(f"This PDF could not be read: {problem}") from problem

    text = normalize_whitespace("\n\n".join(pages))
    if not text:
        raise ExtractionError(
            "No text was found in this PDF. It is most likely a scan, and "
            "AnalyzeLocal does not read text from images."
        )
    return text


def extract_docx(path: Path) -> str:
    """Extract text from a Word docx file, including table contents."""
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(str(path))
    except (PackageNotFoundError, ValueError, KeyError) as problem:
        raise ExtractionError(
            "This file could not be opened as a Word document."
        ) from problem

    blocks = [block for block in iter_docx_blocks(document) if block]
    text = normalize_whitespace("\n\n".join(blocks))
    if not text:
        raise ExtractionError("No text was found in this Word document.")
    return text


def iter_docx_blocks(document: Any) -> Iterator[str]:
    """Yield paragraph and table text from a docx in document order.

    python-docx exposes paragraphs and tables as separate collections, which
    loses their order. Offer letters put pay and start dates in tables between
    paragraphs, so the body is walked directly instead.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document).text.strip()
        elif child.tag.endswith("}tbl"):
            yield format_table(Table(child, document))


def format_table(table: Any) -> str:
    """Render a docx table as one tab separated row per line."""
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
        if any(cells):
            rows.append("\t".join(cells))
    return "\n".join(rows)


def extract_plain_text(path: Path) -> str:
    """Read a plain text or markdown file."""
    data = path.read_bytes()

    # utf-16 is only tried when a byte order mark says so. Without a mark it
    # decodes almost any even length file into silent garbage rather than
    # raising, so it cannot sit in the fallback chain below.
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return finish_plain_text(data.decode("utf-16"))
        except UnicodeDecodeError:
            pass

    # utf-8-sig reads plain utf-8 and also strips the byte order mark that
    # Windows editors add.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            decoded = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return finish_plain_text(decoded)

    # latin-1 maps every possible byte, so this cannot fail. It is the last
    # resort for a file that is none of the above.
    return finish_plain_text(data.decode("latin-1"))


def finish_plain_text(decoded: str) -> str:
    """Normalize decoded text and reject an empty file."""
    text = normalize_whitespace(decoded)
    if not text:
        raise ExtractionError("This file is empty.")
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse runs of blank lines and trailing spaces into a tidy form."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
