# SCAFFOLD.md - AnalyzeLocal

Initial build plan for the repo. Use this together with CLAUDE.md. Point
Claude Code at both files, then ask it to scaffold the structure below. Do not
implement model, redaction, or analysis logic in this pass. Build the structure
and wiring only, so the app runs and the empty UI loads in the browser.

## Target structure

backend/                Python, FastAPI
  app.py                FastAPI app. Serves the API and the built frontend
                        static files on one localhost port.
  pipeline/
    __init__.py
    extract.py          Extract text from PDF, docx, and plain text.
    redact.py           Regex and checksum detectors, plus a GLiNER NER pass.
    analyze.py          Local LLM analysis and question answering over
                        redacted text.
    model.py            Load and run the local model. Default is Qwen3 8B at
                        Q4_K_M through Ollama, with the model name in config
                        so it can be swapped.
  requirements.txt
frontend/               React, built with Vite
  Minimal UI: file upload, a results view, and a question box.
README.md               Clone, install, download model, and run steps.

## Model and how to swap it

The model is set by one config value (default: qwen3:8b). To swap, change that
value to another Ollama tag and run ollama pull on it. No code changes needed.

Comparable local models that fit a 16GB M1 with headroom:

- qwen3:8b     Default. About 5GB at Q4_K_M. Apache 2.0 license.
- phi4-mini    Microsoft, about 3.8B, roughly 3GB. MIT license. US origin,
               strong reasoning, long context. Good lighter alternative.
- mistral      Mistral 7B, about 4.4GB. Apache 2.0 license.
- gemma3:4b    Google, about 3.3GB. Gemma license with some use restrictions.
- llama3.1:8b  Meta, about 4.7GB. Llama license restricts use above 700 million
               monthly active users, so it is slightly less clean for
               redistribution.

Ollama uses Q4_K_M by default, which is the right quantization here. Avoid 12B
and larger as the default on 16GB. They load, but leave little headroom next to
GLiNER, FastAPI, and the browser.

## How it should run

- One command starts the local backend and opens a browser tab at localhost.
- In development, run the Vite dev server and FastAPI side by side with a
  proxy. For a shipped build, FastAPI serves the built frontend and the API on
  the same port.
- All traffic is localhost only. No internet calls.

## Scaffolding rules

- Every Python function has full type hints on all parameters and the return
  type.
- No emojis, decorative symbols, or em dashes anywhere in code or docs.
- Leave clear TODO markers in each stub.
- Do not implement model logic, redaction rules, or analysis yet. Only build
  the structure and wiring so the app runs and the empty UI loads.

## Build order

1. Text extraction (extract.py).
2. Redaction (redact.py): regex and checksums first, then GLiNER.
3. Analysis and question answering (analyze.py) on redacted text.
4. Wire the frontend to the backend, then add the quick redaction review.
