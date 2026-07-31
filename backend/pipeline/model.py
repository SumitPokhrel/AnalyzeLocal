"""Local model runtime.

Talks to Ollama over its HTTP API on 127.0.0.1. Loopback is the only host
this module ever contacts. There is no cloud fallback and there should never
be one.

Generation is streamed. Callers see text as it is produced, and the reason
generation stopped, which is the only way to tell a finished answer from one
cut off at the output cap.
"""

import json
from collections.abc import Iterator
from typing import Any, NamedTuple

import httpx

import config


class ModelError(Exception):
    """Raised when the local model cannot produce an answer.

    Covers expected operational problems: Ollama not running, the model tag
    not pulled, a call that runs past the timeout. The message is shown to
    the user, so it should say what to do next.
    """


class ModelChunk(NamedTuple):
    """One piece of a streamed reply.

    done_reason is set only on the final chunk. Ollama reports "stop" for a
    normal finish and "length" when the num_predict cap was reached.
    """

    text: str
    done_reason: str | None


def build_timeout() -> httpx.Timeout:
    """Timeouts for a local model call.

    The httpx default of five seconds is far too short here. A cold start
    loads five gigabytes of weights, and a full context prompt takes tens of
    seconds to evaluate before the first token appears. Connect stays short
    because loopback either answers immediately or is not listening.
    """
    return httpx.Timeout(
        connect=5.0,
        read=config.OLLAMA_TIMEOUT,
        write=30.0,
        pool=5.0,
    )


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


def build_request_body(prompt: str, system: str | None) -> dict[str, Any]:
    """Build the JSON body for one generate call."""
    body: dict[str, Any] = {
        "model": config.MODEL_NAME,
        "prompt": prompt,
        "stream": True,
        # Sent explicitly. Left unset, Ollama enables thinking on qwen3 and
        # the reasoning tokens eat the answer budget. See config.OLLAMA_THINK.
        "think": config.OLLAMA_THINK,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "options": {
            "num_ctx": config.OLLAMA_NUM_CTX,
            "num_predict": config.OLLAMA_NUM_PREDICT,
            # Zero temperature. This tool reports figures out of a document,
            # so there is nothing to be gained from sampling variety.
            "temperature": 0,
        },
    }
    if system is not None:
        body["system"] = system
    return body


def describe_status(status_code: int, text: str) -> ModelError:
    """Turn a non-200 reply from Ollama into a message worth showing."""
    if status_code == 404:
        return ModelError(
            f"The model {config.MODEL_NAME} is not installed. "
            f"Run: ollama pull {config.MODEL_NAME}"
        )
    return ModelError(f"The local model returned an error: {text[:200]}")


def generate_stream(prompt: str, system: str | None = None) -> Iterator[ModelChunk]:
    """Stream a reply from the local model, one chunk at a time."""
    body = build_request_body(prompt, system)
    try:
        with httpx.stream(
            "POST",
            f"{config.OLLAMA_URL}/api/generate",
            json=body,
            timeout=build_timeout(),
        ) as response:
            if response.status_code != 200:
                response.read()
                raise describe_status(response.status_code, response.text)

            for line in response.iter_lines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as problem:
                    raise ModelError(
                        "The local model sent a reply that could not be read."
                    ) from problem

                if payload.get("error"):
                    raise ModelError(f"The local model reported: {payload['error']}")

                done = bool(payload.get("done"))
                yield ModelChunk(
                    text=str(payload.get("response") or ""),
                    done_reason=str(payload.get("done_reason") or "stop") if done else None,
                )
    except httpx.TimeoutException as problem:
        raise ModelError(
            "The local model did not finish in "
            f"{config.OLLAMA_TIMEOUT:.0f} seconds. A long document on a busy "
            "machine can take a while. Try again, or use a smaller model."
        ) from problem
    except httpx.HTTPError as problem:
        raise ModelError(
            "Could not reach the local model. Check that Ollama is running."
        ) from problem
