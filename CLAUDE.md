# CLAUDE.md - AnalyzeLocal

Project instructions for Claude Code. Read this before making changes.

## What this project is

AnalyzeLocal is an open-source desktop tool that analyzes sensitive personal
documents (job offers, leases, and other short documents) entirely on the
user's machine.
The whole point is privacy: you never upload your documents to a cloud AI
service like ChatGPT or Claude. Everything stays on your laptop, and no
document, and no data derived from a document, ever leaves the computer. It
extracts the text and produces a plain-language analysis and comparison
locally.

## Hard constraints (do not violate)

- On-device only. The shipped application must make zero network calls. No
  cloud APIs, no telemetry, no analytics, no update pings, no crash reporting
  that transmits data.
- All models run locally. The model is downloaded once and runs offline
  afterward.
- Apple Silicon macOS only for the first version. Target M1 and newer. Do not
  add Windows, Linux, or Intel Mac code paths yet. Structure the code so a
  Windows port is possible later, but do not build it now.
- Fits in 16GB RAM. Assume an M1 with 16GB shared memory running alongside the
  OS and a browser. Model plus app must leave comfortable headroom. Prefer
  small models (roughly 8B parameters or fewer, quantized) over large ones.
- Python is the primary language.

## Keep it simple

- Do not add abstractions, config systems, or plugin frameworks until they are
  actually needed.
- Prefer a small number of well-understood dependencies.
- No virtual environment gymnastics. A single requirements.txt is enough. If a
  venv is used, keep it optional and documented in one line.
- Favor the standard library and mature packages over exotic ones.

## Pipeline (extract, then analyze)

Two steps. Keep the flow simple and the steps light.

1. Extract text from the input document (PDF, docx, plain text).
2. Analyze the extracted text with a local LLM, including comparing two
   documents and answering follow-up questions about one.

## On redaction (deliberately deferred, not forgotten)

An earlier version of this plan redacted PII between those two steps. That was
cut by decision, for two reasons. Privacy here comes from locality, so
redacting before handing text to a model running on the same machine protects
against nothing. And redaction actively degrades the analysis, because the
salary figures, employer names, dates, and addresses are the substance of what
the user wants reasoned about.

It may come back later as an optional feature attached to an export or copy
action, for the case where someone wants to paste a sanitized version into a
cloud model for a second opinion. That is a real workflow and the reason the
door is left open. It is not part of the core pipeline, and it should not be
reintroduced as one.

## On tax returns (deliberately out of scope)

An earlier version of this listed tax returns alongside job offers and leases.
That claim is withdrawn. A blank 1040 with its common schedules extracts to
about 54,000 characters, roughly three times what fits in the context window,
so most of it is dropped before the model sees anything. The schedules that
carry the interesting figures, capital gains, business income, and rental
income, sit at the end and are the first to go.

Detection stays, and must not be removed. Someone will upload a 1040 whatever
the documentation says, and the app tells them it is unsupported rather than
producing a confident analysis of the first 40 percent. Recognizing a document
and quietly doing a poor job of it is the failure mode this project keeps
designing against.

What would change this is chunking: splitting a long document into pieces,
summarizing each, then reasoning over the summaries. That is not built. Until
it is, tax returns stay out of scope.

## On the quote check (standing rule, both halves)

The analysis has to quote the document for every figure it reports, and
verify_quotes checks each quote back against the source. When a quote fails
that check, there are two opposite explanations, and telling them apart is
the whole job. Getting it backwards breaks the tool in one direction or the
other.

A normalization gap that makes a substantively verbatim quote fail to match
is a bug in the checker, not a finding. This has already happened three times
from different directions: collapsed whitespace, typographic quotes, and the
dot leaders on a form line. In each case the quote said what the document
says and a layout difference defeated the string match. Fix the matcher.
False warnings are expensive because they teach people to ignore warnings,
and a warning nobody reads protects nobody.

Quote stitching is the opposite case and must not be treated the same way.
When the model joins two passages that are each verbatim but sit apart in the
document, the combined quote is a false claim: presenting them as one
quotation asserts that the text between them does not exist. The flag is
correct. Loosening the matcher to let stitched quotes through would make the
checker endorse a claim the document does not support, which is worse than
the false positives the first half is about.

The test that separates them: is the quote verbatim as one contiguous span,
ignoring layout? A formatting difference does not change what the document
says. Omitted text does.

Status as of the last measured run: stitching is watch-only. One occurrence,
on an offer letter, where the two halves sat 96 characters apart with an
unrelated sentence between them. That is not enough to act on. If it becomes
common, the fix is a prompt clause requiring quotes to be contiguous, or
split into separate quotations. The fix is never a looser match.

## Model runtime

- Default model: Qwen3 8B, quantized to Q4_K_M, run through Ollama. Chosen for
  its permissive Apache 2.0 license and good quality at a size that fits 16GB
  with headroom.
- Keep the model name in config so a user can swap in another local model (for
  example Gemma or Phi-4) without code changes.
- Use a Mac-native local runtime. Ollama is the default for easy setup. MLX is
  an option later if more speed is wanted.
- Download model weights on first run. Never bundle anything that phones home.

## Interface

A simple local web dashboard. Not fancy.

- React frontend written in TypeScript, built with Vite. The user can upload a
  PDF, docx, or text file, read the analysis, and ask follow-up questions about
  the document in a basic chat box.
- A local Python backend (for example FastAPI) exposes the pipeline to the
  frontend. The frontend talks to it over localhost only.
- Localhost traffic stays on the machine, so this does not break the on-device
  rule. There are still no calls to the internet.
- Keep the UI minimal: an upload area, a results view for the analysis, and a
  question box. No accounts, no settings sprawl, no styling beyond clean and
  readable.

## Coding conventions

- Plain, readable Python.
- Type hints are mandatory on every function, covering all parameters and the
  return type.
- Short, direct docstrings.
- No decorative symbols, em dashes, or emojis anywhere in the code, comments,
  or docs. Use plain ASCII and hyphens.
- Keep functions small and testable.

Frontend:

- TypeScript runs in strict mode. No implicit any, and no use of the any type
  to get past a type error.
- The API types in frontend/src/api.ts mirror the Pydantic models in
  backend/schemas.py by hand. When a schema changes on one side, change it on
  the other in the same commit.
- Component props get a named interface rather than an inline type.
- npm run build type checks before it bundles, so a type error fails the
  build.

## Tests

- pytest. Run it from the project root with a bare pytest command.
- Test dependencies live in backend/requirements-dev.txt, kept separate from
  requirements.txt so running the app does not install test tooling.
- Test documents are generated in backend/tests/conftest.py rather than
  committed as binary files, so a contributor can read what is in each one
  and add a case without needing a Word licence or a scanner.
- When a bug is fixed, add a test that fails without the fix and say in the
  docstring what the bug was.
- Do not assert on the responses of stubbed routes. Those change as the
  pipeline is filled in, and tests that track them are noise.

## For contributors

- MIT licensed. Keep it easy for others to clone, install, and run on their
  own Mac.
- Setup should be: clone, install dependencies, download the model, run.
  Document each step in the README.
