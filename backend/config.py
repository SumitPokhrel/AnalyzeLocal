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
# this is deliberately generous.
OLLAMA_TIMEOUT: float = float(os.environ.get("ANALYZELOCAL_OLLAMA_TIMEOUT", "300"))

# Local NER model used for unstructured PII. Downloaded once on first use,
# then runs offline.
NER_MODEL_NAME: str = os.environ.get(
    "ANALYZELOCAL_NER_MODEL", "urchade/gliner_multi_pii-v1"
)

# Address the backend binds to. Loopback only. Do not change this to 0.0.0.0,
# which would expose uploaded documents to the local network.
HOST: str = "127.0.0.1"
PORT: int = int(os.environ.get("ANALYZELOCAL_PORT", "8000"))

# Largest upload accepted, in bytes.
MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

# File extensions the extractor understands.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (".pdf", ".docx", ".txt", ".md")
