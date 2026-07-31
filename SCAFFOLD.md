# SCAFFOLD.md - AnalyzeLocal

Build plan for the repo. Use this together with CLAUDE.md. The pipeline is two
steps, extract then analyze. Redaction was considered and deliberately cut, for
the reasons recorded in CLAUDE.md.

## Target structure

backend/                Python, FastAPI
  app.py                FastAPI app. Serves the API and the built frontend
                        static files on one localhost port.
  pipeline/
    __init__.py
    extract.py          Extract text from PDF, docx, and plain text.
    analyze.py          Local LLM analysis, comparison, and question
                        answering over the extracted text.
    model.py            Load and run the local model. Default is Qwen3 8B at
                        Q4_K_M through Ollama, with the model name in config
                        so it can be swapped.
  config.py             Model name, Ollama URL, host and port, upload limits.
                        Every value has an environment variable override.
  schemas.py            Pydantic request and response models, shared by the
                        routes and the pipeline.
  tests/
    conftest.py         Builds the test documents at run time. Nothing binary
                        is committed, so each fixture can be read and changed.
    test_extract.py     Extraction, including the encoding and document order
                        cases that have already caused bugs.
    test_api.py         Route behavior that does not change as the pipeline
                        is filled in.
  requirements.txt
  requirements-dev.txt  Test only. Keeps pytest out of the shipped install.
pytest.ini              Points pytest at backend/tests, with backend on the
                        import path.
frontend/               React and TypeScript, built with Vite
  tsconfig.json         Strict mode. Type checking runs before the bundle.
  vite.config.ts        Dev server on 5173, proxying /api to the backend.
  index.html
  src/
    main.tsx            Entry point.
    App.tsx             Layout and top level state.
    api.ts              Typed fetch wrappers. The interfaces here mirror the
                        Pydantic models in backend/schemas.py by hand.
    styles.css
    components/
      UploadArea.tsx    File picker.
      ResultsView.tsx   Analysis panes.
      QuestionBox.tsx   Follow-up question input.
README.md               Clone, install, download model, and run steps.

## Architecture

Data flows in one direction, top to bottom. The thing worth reading off this
diagram is the loopback boundary at the bottom. Every address in the whole
system is 127.0.0.1, and no arrow leaves the machine. That is the property the
privacy claim rests on, so it is the one to check when reviewing a change.

```
+----------------------------------------------------------------------+
|  Browser at http://127.0.0.1:8000                                    |
|                                                                      |
|  React and TypeScript UI, built by Vite into frontend/dist           |
|  UploadArea.tsx    ResultsView.tsx    QuestionBox.tsx                |
|  api.ts, types mirroring backend/schemas.py                          |
+----------------------------------------------------------------------+
      |
      |  fetch /api/analyze, /api/question
      |  loopback only, never leaves the machine
      v
+----------------------------------------------------------------------+
|  FastAPI at 127.0.0.1:8000, backend/app.py                           |
|                                                                      |
|  Serves the built frontend and the API on one port                   |
|  DOCUMENTS: extracted text held in memory for follow-up              |
|  questions, never written to disk                                    |
+----------------------------------------------------------------------+
      |
      v
+----------------------------------------------------------------------+
|  pipeline/extract.py                                                 |
|  PDF, docx, and plain text to text, using pypdf and python-docx      |
+----------------------------------------------------------------------+
      |
      v
+----------------------------------------------------------------------+
|  pipeline/analyze.py                                                 |
|  Builds prompts for analysis, comparison, and follow-up questions    |
+----------------------------------------------------------------------+
      |
      v
+----------------------------------------------------------------------+
|  pipeline/model.py                                                   |
|  httpx to the Ollama HTTP API at 127.0.0.1:11434                     |
|  Default model qwen3:8b at Q4_K_M, swappable in config.py            |
+----------------------------------------------------------------------+
      |
      |  loopback boundary
      |  every address above is 127.0.0.1, and there is no box below
      |  this line. Nothing in the shipped app crosses to the internet.
      v
     none
```

Uploads are written to a temporary file, read once by the extractor, and
deleted in a finally block. The Ollama model is the only download, one time,
and it runs offline afterwards.

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
FastAPI and the browser.

## How it should run

- One command starts the local backend and opens a browser tab at localhost.
- In development, run the Vite dev server and FastAPI side by side with a
  proxy. For a shipped build, FastAPI serves the built frontend and the API on
  the same port.
- All traffic is localhost only. No internet calls.

## Scaffolding rules

- Every Python function has full type hints on all parameters and the return
  type.
- TypeScript runs in strict mode on the frontend. Component props get a named
  interface, and the any type is not an escape hatch for a type error.
- The interfaces in api.ts are kept in step with backend/schemas.py by hand.
  There is no code generation between them, so both sides change together.
- No emojis, decorative symbols, or em dashes anywhere in code or docs.
- Leave clear TODO markers in anything left as a stub.
- Do not reintroduce a redaction stage into the core pipeline. See CLAUDE.md
  for why it was cut and the one form in which it could come back.

## Build order

1. Text extraction (extract.py). Done, covered by backend/tests.
2. Analysis, comparison, and question answering (analyze.py). Done, covered
   by backend/tests.
3. Wire the frontend to the backend so results and follow-up questions
   render. Done, covered by backend/tests and frontend/src/api.test.ts. The
   analyze, compare, and question routes stream newline delimited JSON, so
   text starts arriving in about a second rather than after the full run.

Each step lands with tests. A bug that gets fixed gets a test that fails
without the fix, so the same mistake cannot come back quietly.
