"""Local model runtime.

Talks to Ollama over its HTTP API on 127.0.0.1. Loopback is the only host
this module ever contacts. There is no cloud fallback and there should never
be one.
"""

import httpx

import config


def is_available() -> bool:
    """Report whether the local Ollama server is reachable."""
    try:
        response = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=2.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return False
    return True


def installed_models() -> list[str]:
    """List the model tags Ollama has already pulled on this machine."""
    try:
        response = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    payload = response.json()
    return [entry["name"] for entry in payload.get("models", [])]


def generate(prompt: str, system: str | None = None) -> str:
    """Send a prompt to the local model and return the complete reply."""
    # TODO: post to /api/generate with stream set to false, using
    # config.MODEL_NAME and config.OLLAMA_TIMEOUT, and return the response
    # field. Raise a clear error when the model tag has not been pulled yet.
    raise NotImplementedError("model generation is not implemented yet")
