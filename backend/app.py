"""FastAPI backend for AnalyzeLocal.

Serves the API and the built frontend on one loopback port. The only network
traffic is between the browser, this server, and the local Ollama process,
all on 127.0.0.1.

Run it with: python backend/app.py
"""

import tempfile
import uuid
import webbrowser
from collections.abc import Iterable, Iterator
from pathlib import Path
from threading import Timer
from typing import NamedTuple

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
from pipeline import analyze as analysis
from pipeline import extract, model
from schemas import (
    DoneEvent,
    HealthResponse,
    QuestionRequest,
    StreamEvent,
    TokenEvent,
)

# Newline delimited JSON. One event per line, so the frontend can act on each
# as it arrives instead of waiting for a complete body.
NDJSON_MEDIA_TYPE = "application/x-ndjson"

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Extracted documents from this run, keyed by document id. Held in memory only,
# never written to disk, and dropped when the process exits. This is what the
# follow-up question route reads from.
DOCUMENTS: dict[str, str] = {}

# Recent question and answer pairs per document, so a follow-up like "and the
# bonus?" has something to refer back to. Capped at config.HISTORY_TURNS,
# because history competes with the document for the context window.
HISTORY: dict[str, list[tuple[str, str]]] = {}


class ExtractedDocument(NamedTuple):
    """One upload after extraction.

    Both fields are strings, so they are named rather than returned as a bare
    tuple. Transposing them would otherwise type check quietly.
    """

    document_id: str
    text: str

# The interactive docs are disabled on purpose. FastAPI loads the Swagger UI
# assets from a public CDN, which would be an outbound network call.
app = FastAPI(title="AnalyzeLocal", docs_url=None, redoc_url=None)

# Only needed during development, when the Vite dev server runs on its own
# port. In a normal run the frontend is served from this same origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(extract.ExtractionError)
async def handle_extraction_error(
    request: Request, exc: extract.ExtractionError
) -> JSONResponse:
    """Show the extractor message to the user instead of a server error.

    A scanned or password protected document is an expected input, not a bug,
    so it gets a readable reason rather than a 500.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(NotImplementedError)
async def handle_not_implemented(
    request: Request, exc: NotImplementedError
) -> JSONResponse:
    """Return a clear 501 while the pipeline is still stubbed out."""
    detail = str(exc) or "This part of the pipeline is not implemented yet."
    return JSONResponse(status_code=501, content={"detail": detail})


def save_upload(upload: UploadFile) -> Path:
    """Write an upload to a temporary file and return its path."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in config.SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix or 'unknown'}",
        )

    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    path = Path(handle.name)
    size = 0
    with handle:
        while chunk := upload.file.read(1024 * 1024):
            size += len(chunk)
            if size > config.MAX_UPLOAD_BYTES:
                path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File is too large.")
            handle.write(chunk)
    return path


def extract_upload(upload: UploadFile) -> ExtractedDocument:
    """Extract text from one upload and remember it for follow-up questions."""
    path = save_upload(upload)
    try:
        text = extract.extract_text(path)
    finally:
        path.unlink(missing_ok=True)

    document_id = uuid.uuid4().hex
    DOCUMENTS[document_id] = text
    return ExtractedDocument(document_id=document_id, text=text)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report server status and whether the local model runtime is reachable."""
    return HealthResponse(
        status="ok",
        configured_model=config.MODEL_NAME,
        ollama_available=model.is_available(),
    )


def ndjson(events: Iterable[StreamEvent]) -> Iterator[str]:
    """Serialize pipeline events as newline delimited JSON."""
    for event in events:
        yield event.model_dump_json() + "\n"


def stream(events: Iterable[StreamEvent]) -> StreamingResponse:
    """Wrap pipeline events in a streaming HTTP response."""
    return StreamingResponse(ndjson(events), media_type=NDJSON_MEDIA_TYPE)


@app.post("/api/analyze")
def analyze_document(file: UploadFile = File(...)) -> StreamingResponse:
    """Extract and analyze one document, streaming the answer.

    Extraction runs here rather than inside the stream, so an unsupported
    file, an oversized upload, or a scanned PDF still gets a real status
    code instead of a 200 carrying an error event.
    """
    document = extract_upload(file)
    return stream(analysis.stream_analysis(document.text, [document.document_id]))


@app.post("/api/compare")
def compare_documents(
    first: UploadFile = File(...), second: UploadFile = File(...)
) -> StreamingResponse:
    """Extract and compare two documents, streaming all three model calls."""
    first_document = extract_upload(first)
    second_document = extract_upload(second)
    return stream(
        analysis.stream_comparison(
            first_document.text,
            second_document.text,
            [first_document.document_id, second_document.document_id],
        )
    )


@app.post("/api/question")
def ask_question(request: QuestionRequest) -> StreamingResponse:
    """Answer a follow-up question about a document already extracted."""
    text = DOCUMENTS.get(request.document_id)
    if text is None:
        raise HTTPException(
            status_code=404,
            detail="Unknown document id. Upload the document again.",
        )

    history = HISTORY.get(request.document_id, [])

    def events() -> Iterator[StreamEvent]:
        """Forward the answer, recording it only if it finished cleanly."""
        collected: list[str] = []
        for event in analysis.stream_answer(text, request.question, history):
            if isinstance(event, TokenEvent):
                collected.append(event.text)
            elif isinstance(event, DoneEvent):
                # An interrupted or cut off answer is not kept. Feeding a
                # half finished answer back as context poisons later turns.
                HISTORY[request.document_id] = [
                    *history,
                    (request.question, "".join(collected)),
                ][-config.HISTORY_TURNS :]
            yield event

    return stream(events())


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}")
    def serve_frontend(path: str) -> FileResponse:
        """Serve the built frontend, falling back to index.html for routes."""
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = FRONTEND_DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")

else:

    @app.get("/")
    def missing_frontend() -> JSONResponse:
        """Explain how to build the frontend when the build is missing."""
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Frontend build not found. Run 'npm install' and "
                    "'npm run build' in the frontend directory."
                )
            },
        )


def open_browser() -> None:
    """Open the local dashboard in the default browser."""
    webbrowser.open(f"http://{config.HOST}:{config.PORT}")


def main() -> None:
    """Start the local server and open the dashboard."""
    if not FRONTEND_DIST.is_dir():
        print(
            "Frontend build not found. Run 'npm install' and 'npm run build' "
            "in the frontend directory."
        )
    Timer(1.0, open_browser).start()
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
