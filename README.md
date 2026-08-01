# AnalyzeLocal

AnalyzeLocal analyzes sensitive personal documents like job offers and leases
entirely on your own machine. You never upload your documents to a cloud AI
service like ChatGPT or Claude. Every step runs locally, so your documents
never leave your computer.

It reads the document and produces a plain-language analysis and comparison,
all on-device.

## What it does

- Reads PDF, docx, and plain text documents.
- Analyzes the content with a local language model, including comparing two
  documents side by side.
- Lets you ask follow-up questions about the document in a simple chat box.

Because everything runs on your own machine, nothing is stripped out of the
document before analysis. The model sees the salary figures, the dates, and the
names, which is what makes the analysis useful.

## What it supports

AnalyzeLocal is built for short documents that are mostly prose.

- Job offers and leases work well. They fit in the model's context window
  whole, and the analysis quotes the document for every figure it reports.
- Other short documents, such as contracts, letters, and agreements, get a
  general checklist rather than a tailored one and otherwise work the same.
- Long documents are cut to fit. Anything past roughly 18,000 characters,
  about 3,000 words, is truncated. Only the first part is read, and the app
  says so on screen. Figures later in the document are not seen.
- Tax returns are not supported. A blank 1040 with its common schedules comes
  to about 54,000 characters, three times what fits, so most of it never
  reaches the model. The app recognizes a tax return and tells you it is
  unsupported rather than producing an analysis that looks complete. Handling
  them properly needs the document split into chunks and summarized in passes,
  which is not built.

Every figure the analysis reports is checked back against your document, and
anything it could not find is flagged. The app also reports how much of the
answer it was able to check, because an answer with nothing to check looks the
same as a verified one.

## Requirements

- An Apple Silicon Mac (M1 or newer). Intel Macs are not supported.
- macOS, with about 16GB of memory recommended.
- Python 3.10 or newer. Read the note in step 3, because the python3 that
  ships with macOS is usually older than this.
- Node.js, used to build the web interface. TypeScript and the other build
  tools install with it in the next step, so nothing needs to be set up
  globally.
- Ollama, used to run the local model. See https://ollama.com

Windows support is planned for a later version.

## Setup

1. Clone the repository.

```
git clone https://github.com/SumitPokhrel/AnalyzeLocal.git
cd AnalyzeLocal
```

2. Install and start Ollama, then pull the default model.

```
ollama pull qwen3:8b
```

3. Create a virtual environment, activate it, and install the backend
   dependencies.

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

Check the Python version inside the activated environment before you install:

```
python --version
```

That has to report 3.10 or newer. Check it here rather than checking python3
outside the environment, because the version that matters is the one the
environment was built with.

On macOS this is the step that usually goes wrong. The system python3 is
often 3.9, and a virtual environment built with it inherits that version. The
install still succeeds, and the failure only appears when you start the app:

```
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

That comes from the str | None annotation in backend/pipeline/model.py, which
is valid from Python 3.10 onward. If you see it, delete .venv, install a newer
Python, and rebuild the environment with that interpreter, for example
python3.12 -m venv .venv.

4. Build the web interface.

```
cd frontend
npm install
npm run build
cd ..
```

The build type checks the TypeScript first, so a type error stops it before
anything is bundled.

The virtual environment is only active in the shell you activated it in. In
every new terminal session, activate it again from the project root before
running the app or the tests.

```
source .venv/bin/activate
```

## Run

Start the app with a single command from the project root.

```
python backend/app.py
```

This starts the local server and serves the interface at
http://localhost:8000. Open that address in your browser, upload a document,
and read the analysis.

All traffic stays on your machine. The browser talks to the local backend over
localhost, which is loopback and never touches the internet.

## Tests

With the virtual environment active, install the test dependencies into it,
then run pytest from the project root.

```
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest
```

The test dependencies are separate from backend/requirements.txt, so running
the app does not install test tooling. They go into the same environment.

The test documents are generated while the tests run, so there are no binary
fixtures in the repository. Ollama does not need to be running.

## Changing the model

The model is set by one value in backend/config.py (default: qwen3:8b). To use
a different local model, change that value to another Ollama tag and pull it,
or set the environment variable instead of editing the file.

```
export ANALYZELOCAL_MODEL=phi4-mini
ollama pull phi4-mini
```

Some options that fit a 16GB Mac:

- qwen3:8b (default), Apache 2.0 license
- phi4-mini, lighter, MIT license
- mistral (Mistral 7B), Apache 2.0 license
- gemma3:4b, Google Gemma license
- llama3.1:8b, Meta Llama license

Ollama uses Q4_K_M quantization by default, which is the right balance on a
16GB machine.

## How it works

The pipeline has two steps: extract the text from the document, then analyze it
with the local model. The backend is Python and FastAPI. The interface is React
and TypeScript, built with Vite. In a normal run, FastAPI serves both the built
interface and the API on one local port.

The request and response types in frontend/src/api.ts are written by hand to
match the Pydantic models in backend/schemas.py. There is no code generation
step, so if you change a schema, change both files.

The backend talks to the model through the HTTP API that Ollama already
exposes on 127.0.0.1:11434, using httpx. There is no separate client library
in between, so the one address the app contacts is visible in plain sight in
backend/pipeline/model.py.

To work on the interface, run the Vite dev server alongside the backend. It
serves on port 5173 and proxies API calls to the backend on port 8000.

```
python backend/app.py
cd frontend && npm run dev
```

## Privacy

There are no cloud calls, no telemetry, and no analytics. Documents, and
everything derived from them, stay on your computer. The only network use is
loopback between your browser and the local backend.

## License

This project is licensed under the MIT License. You are free to use, copy,
modify, and distribute it, including for commercial purposes, with the only
condition being that you keep the copyright and license notice. The full text
is in the LICENSE file.

Copyright (c) 2026 Sumit Pokhrel
