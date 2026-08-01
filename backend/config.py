"""Configuration values for AnalyzeLocal.

Each value has a plain default and can be overridden with an environment
variable, so the model or the port can be changed without editing code.
"""

import os

# Ollama model tag used for analysis and question answering. To swap models,
# set ANALYZELOCAL_MODEL to another tag (phi4-mini, mistral, gemma3:4b) and
# run ollama pull on it first. No code changes are needed.
MODEL_NAME: str = os.environ.get("ANALYZELOCAL_MODEL", "qwen3:8b")

# Base URL of the local Ollama server. Loopback only, never a remote host.
OLLAMA_URL: str = os.environ.get("ANALYZELOCAL_OLLAMA_URL", "http://127.0.0.1:11434")

# Seconds to wait for a model response. Generation on an M1 can be slow, so
# this is deliberately generous. Used as the read timeout specifically.
OLLAMA_TIMEOUT: float = float(os.environ.get("ANALYZELOCAL_OLLAMA_TIMEOUT", "300"))

# Context window requested on every call. Keep this constant. Changing it
# between requests makes Ollama reload the model, measured at 2.4 seconds,
# and throws away the prompt cache that makes follow-up questions fast.
OLLAMA_NUM_CTX: int = int(os.environ.get("ANALYZELOCAL_NUM_CTX", "8192"))

# Cap on tokens generated per call. Costs no memory: the KV cache is sized
# from num_ctx alone, measured identical at 800, 1600, and 2400. At 1200 the
# prompt and the answer still fit inside num_ctx with room to spare, so this
# comes out of slack rather than out of the document budget.
OLLAMA_NUM_PREDICT: int = int(os.environ.get("ANALYZELOCAL_NUM_PREDICT", "1200"))

# How long Ollama keeps the model resident after a call. Keeping it loaded
# avoids paying the cold start again on the next question.
OLLAMA_KEEP_ALIVE: str = os.environ.get("ANALYZELOCAL_KEEP_ALIVE", "5m")

# Qwen3 is a hybrid reasoning model, and Ollama turns thinking on by default
# for any model that supports it. Thinking tokens come out of the same budget
# as the answer. Measured on qwen3:8b at num_ctx 8192: the same analysis took
# 615 tokens and 37.4 seconds with thinking on, and 151 tokens and 8.3
# seconds with it off. Worse, a small budget can be spent entirely on
# reasoning, which returns an empty answer with done_reason "length".
# Leave this off unless you are deliberately measuring it.
OLLAMA_THINK: bool = os.environ.get("ANALYZELOCAL_THINK", "false").lower() == "true"

# Tokens of the context window set aside for the document itself. The rest
# covers the system prompt, the answer, and follow-up history.
DOCUMENT_TOKEN_BUDGET: int = int(os.environ.get("ANALYZELOCAL_DOCUMENT_TOKENS", "6400"))

# Question and answer pairs kept per document for follow-up context.
HISTORY_TURNS: int = 3

# Address the backend binds to. Loopback only. Do not change this to 0.0.0.0,
# which would expose uploaded documents to the local network.
HOST: str = "127.0.0.1"
PORT: int = int(os.environ.get("ANALYZELOCAL_PORT", "8000"))

# Largest upload accepted, in bytes.
MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

# File extensions the extractor understands.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".txt", ".md")
