"""Service LLM -- wrapper pour l'API Ollama locale."""

import logging

import httpx
from flask import current_app

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=5.0, pool=5.0)


def _ollama_url() -> str:
    """URL de base Ollama depuis la config Flask."""
    return current_app.config.get("OLLAMA_URL", "http://localhost:11434")


def list_ollama_models() -> list[str]:
    """Liste les modeles disponibles sur le serveur Ollama.

    GET {OLLAMA_URL}/api/tags
    Retourne une liste de noms. Retourne [] si Ollama est injoignable.
    """
    try:
        resp = httpx.get(f"{_ollama_url()}/api/tags", timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning("Ollama /api/tags returned %d", resp.status_code)
            return []
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except httpx.HTTPError:
        logger.info("Ollama injoignable a %s", _ollama_url())
        return []


def generate_synthesis(model: str, prompt: str, transcripts: str) -> str:
    """Envoie les transcripts au LLM et retourne la synthese.

    POST {OLLAMA_URL}/api/generate
    Body: {"model": ..., "prompt": ..., "stream": false}

    Raises ConnectionError si Ollama repond en erreur.
    """
    full_prompt = f"{prompt}\n\n--- TRANSCRIPTS ---\n\n{transcripts}"

    try:
        resp = httpx.post(
            f"{_ollama_url()}/api/generate",
            json={"model": model, "prompt": full_prompt, "stream": False},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise ConnectionError(f"Ollama injoignable: {exc}") from exc

    if resp.status_code != 200:
        raise ConnectionError(f"Ollama erreur {resp.status_code}: {resp.text}")

    return resp.json().get("response", "")
