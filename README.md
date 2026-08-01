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

Qwen3 8B is the default for its permissive license and its quality at a size
that leaves headroom on a 16GB machine. Ollama uses Q4_K_M quantization by
default, which is the right balance here.

## How it works

The pipeline has two steps: extract the text from the document, then analyze
it with the local model. There is nothing in between.

The backend is Python and FastAPI. The interface is React and TypeScript,
built with Vite. In a normal run, FastAPI serves both the built interface and
the API on one local port.

The analyze, compare, and question routes stream newline delimited JSON, so
text appears as the model produces it rather than after the whole run. A first
analysis takes about 30 seconds and a comparison about 80, which is too long
to show nothing.

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

## Contributing

### Constraints that do not bend

- On-device only. The shipped application makes zero network calls: no cloud
  APIs, no telemetry, no analytics, no update pings, no crash reporting that
  transmits data. Loopback traffic between the browser, the backend, and
  Ollama does not count, because it never leaves the machine.
- All models run locally. Weights are downloaded once on first use and run
  offline afterwards. Never bundle anything that phones home.
- Apple Silicon macOS only for now. Target M1 and newer. Do not add Windows,
  Linux, or Intel Mac code paths yet, but structure the code so a Windows port
  stays possible.
- Fits in 16GB. Assume an M1 running the OS and a browser alongside. Prefer
  small quantized models, roughly 8B parameters or fewer.
- Python is the primary language.

### Keep it simple

- No abstractions, config systems, or plugin frameworks until they are
  actually needed.
- Few, well understood dependencies. Favor the standard library and mature
  packages over exotic ones.
- Runtime dependencies live in backend/requirements.txt, test tooling in
  backend/requirements-dev.txt, so running the app does not install pytest.
- Keep the UI minimal: an upload area, a results view, and a question box. No
  accounts, no settings sprawl, no styling beyond clean and readable.

### Coding conventions

- Plain, readable Python. Short, direct docstrings. Small, testable functions.
- Type hints are mandatory on every function, covering all parameters and the
  return type.
- No decorative symbols, em dashes, or emojis anywhere in code, comments, or
  docs. Plain ASCII and hyphens.
- TypeScript runs in strict mode. No implicit any, and the any type is not an
  escape hatch for a type error.
- The API types in frontend/src/api.ts mirror the Pydantic models in
  backend/schemas.py by hand. When a schema changes on one side, change the
  other in the same commit.
- Component props get a named interface rather than an inline type.
- npm run build type checks before it bundles, so a type error fails the build.

### Test conventions

- pytest, run from the project root with a bare pytest command.
- Test documents are generated in backend/tests/conftest.py rather than
  committed as binary files, so a contributor can read what is in each one and
  add a case without needing a Word licence or a scanner.
- When a bug is fixed, add a test that fails without the fix and say in the
  docstring what the bug was.

## Design decisions

Three decisions that are easy to reverse by accident. The reasoning is
recorded so it does not have to be rediscovered.

### Why there is no redaction step

An earlier plan redacted personal information between extraction and analysis.
That was cut deliberately, for two reasons. Privacy here comes from locality,
so redacting before handing text to a model running on the same machine
protects against nothing. And redaction actively degrades the analysis,
because the salary figures, employer names, dates, and addresses are the
substance of what the user wants reasoned about.

It may come back as an optional feature attached to an export or copy action,
for someone who wants to paste a sanitized version into a cloud model for a
second opinion. That is a real workflow and the reason the door is left open.
It is not part of the core pipeline and should not be reintroduced as one.

### Why tax returns are out of scope

An earlier version listed tax returns alongside job offers and leases. That
claim is withdrawn. A blank 1040 with its common schedules extracts to about
54,000 characters, roughly three times what fits in the context window, so
most of it is dropped before the model sees anything. The schedules carrying
the interesting figures, capital gains, business income, and rental income,
sit at the end and are the first to go.

Detection stays, and must not be removed. Someone will upload a 1040 whatever
the documentation says, and the app tells them it is unsupported rather than
producing a confident analysis of the first 40 percent. Recognizing a document
and quietly doing a poor job of it is the failure mode this project keeps
designing against.

Chunking would change this: splitting a long document into pieces, summarizing
each, then reasoning over the summaries. That is not built. Until it is, tax
returns stay out of scope.

### The quote check, and how to read a failed quote

The analysis has to quote the document for every figure it reports, and
verify_quotes checks each quote back against the source. When a quote fails
that check there are two opposite explanations, and telling them apart is the
whole job. Getting it backwards breaks the tool in one direction or the other.

A normalization gap that makes a substantively verbatim quote fail to match is
a bug in the checker, not a finding. This has already happened three times
from different directions: collapsed whitespace, typographic quotes, and the
dot leaders on a form line. In each case the quote said what the document says
and a layout difference defeated the string match. Fix the matcher. False
warnings are expensive because they teach people to ignore warnings, and a
warning nobody reads protects nobody.

Quote stitching is the opposite case and must not be treated the same way.
When the model joins two passages that are each verbatim but sit apart in the
document, the combined quote is a false claim: presenting them as one
quotation asserts that the text between them does not exist. The flag is
correct. Loosening the matcher to let stitched quotes through would make the
checker endorse a claim the document does not support, which is worse than the
false positives the first half is about.

The test that separates them: is the quote verbatim as one contiguous span,
ignoring layout? A formatting difference does not change what the document
says. Omitted text does.

Status as of the last measured run: stitching is watch-only. One occurrence,
on an offer letter, where the two halves sat 96 characters apart with an
unrelated sentence between them. That is not enough to act on. If it becomes
common, the fix is a prompt clause requiring quotes to be contiguous or split
into separate quotations. The fix is never a looser match.

## License

This project is licensed under the MIT License. You are free to use, copy,
modify, and distribute it, including for commercial purposes, with the only
condition being that you keep the copyright and license notice. The full text
is in the LICENSE file.

Copyright (c) 2026 Sumit Pokhrel
