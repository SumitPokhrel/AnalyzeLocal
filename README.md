# AnalyzeLocal

AnalyzeLocal analyzes sensitive personal documents like job offers, leases, and
tax returns entirely on your own machine. You never upload your documents to a
cloud AI service like ChatGPT or Claude. Every step runs locally, so your
documents never leave your computer.

It detects and redacts personal information, then produces a plain-language
analysis and comparison, all on-device.

## What it does

- Reads PDF, docx, and plain text documents.
- Redacts personal information. Structured items like SSNs, account numbers,
  emails, and phone numbers are caught by pattern matching. Unstructured items
  like names, addresses, and employers are caught by a local NER model.
- Lets you review and confirm the redactions.
- Analyzes the redacted content with a local language model, including
  comparing two documents side by side.
- Lets you ask follow-up questions about the document in a simple chat box.

## Requirements

- An Apple Silicon Mac (M1 or newer). Intel Macs are not supported. Supporting windows is the next step. 
- macOS, with about 16GB of memory recommended.
- Python 3.10 or newer.
- Node.js, used to build the web interface. TypeScript and the other build
  tools install with it in the next step, so nothing needs to be set up
  globally.
- Ollama, used to run the local model. See https://ollama.com

Windows support is planned for a later version.

## Setup

1. Clone the repository.

```
git clone https://github.com/<your-username>/AnalyzeLocal.git
cd AnalyzeLocal
```

2. Install and start Ollama, then pull the default model.

```
ollama pull qwen3:8b
```

3. Install the Python backend dependencies.

```
pip install -r backend/requirements.txt
```

If you prefer to isolate dependencies, create a virtual environment first.

4. Build the web interface.

```
cd frontend
npm install
npm run build
cd ..
```

The build type checks the TypeScript first, so a type error stops it before
anything is bundled.

## Run

Start the app with a single command from the project root.

```
python backend/app.py
```

This starts the local server and serves the interface at
http://localhost:8000. Open that address in your browser, upload a document,
review the redactions, and read the analysis.

All traffic stays on your machine. The browser talks to the local backend over
localhost, which is loopback and never touches the internet.

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

The pipeline runs in this order: extract text, redact personal information,
quick review, then analyze the redacted text. The analysis step only ever sees
redacted content. The backend is Python and FastAPI. The interface is React and
TypeScript, built with Vite. In a normal run, FastAPI serves both the built
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
