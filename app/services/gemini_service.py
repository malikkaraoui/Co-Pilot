"""Service Gemini -- wrapper pour le SDK Google Gen AI."""

import logging
import uuid

from flask import current_app
from google import genai

from app.extensions import db
from app.models.llm_usage import LLMUsage

logger = logging.getLogger(__name__)

# Grille tarifaire Gemini 2.5 Flash (EUR, approx)
_COST_PER_1M_INPUT = 0.14
_COST_PER_1M_OUTPUT = 0.55


def _get_api_key() -> str:
    """Recupere la cle API Gemini depuis la config Flask."""
    return current_app.config.get("GEMINI_API_KEY", "")


def _get_model() -> str:
    """Nom du modele Gemini a utiliser."""
    return current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash")


def _get_client() -> genai.Client:
    """Cree un client Gemini avec la cle API."""
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Gemini API key non configuree")
    return genai.Client(api_key=api_key)


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estime le cout en EUR d'un appel Gemini."""
    input_cost = (prompt_tokens / 1_000_000) * _COST_PER_1M_INPUT
    output_cost = (completion_tokens / 1_000_000) * _COST_PER_1M_OUTPUT
    return round(input_cost + output_cost, 6)


def check_health() -> bool:
    """Verifie que l'API Gemini est accessible."""
    api_key = _get_api_key()
    if not api_key:
        return False
    try:
        client = _get_client()
        client.models.generate_content(
            model=_get_model(),
            contents="ping",
        )
        return True
    except Exception:
        logger.warning("Gemini health check echoue")
        return False


def generate_text(
    prompt: str,
    feature: str,
    system_prompt: str | None = None,
    temperature: float = 0.3,
    max_output_tokens: int = 500,
    top_p: float | None = None,
) -> str:
    """Envoie un prompt a Gemini et retourne le texte genere.

    Enregistre automatiquement un LLMUsage pour le suivi des couts.

    Raises:
        ValueError: Si la cle API n'est pas configuree.
        ConnectionError: Si l'API Gemini est injoignable.
    """
    api_key = _get_api_key()
    if not api_key:
        raise ValueError("Gemini API key non configuree")

    model = _get_model()
    request_id = str(uuid.uuid4())

    config_dict = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if top_p is not None:
        config_dict["top_p"] = top_p
    if system_prompt:
        config_dict["system_instruction"] = system_prompt

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config_dict,
        )
    except Exception as exc:
        raise ConnectionError(f"Gemini erreur: {exc}") from exc

    # Extraire les metriques de tokens
    usage = response.usage_metadata
    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
    completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
    total_tokens = getattr(usage, "total_token_count", 0) or 0

    # Persister le suivi des couts
    llm_usage = LLMUsage(
        request_id=request_id,
        provider="gemini",
        model=model,
        feature=feature,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_eur=_estimate_cost(prompt_tokens, completion_tokens),
    )
    db.session.add(llm_usage)
    db.session.commit()

    logger.info(
        "Gemini %s: %d tok (in=%d, out=%d) cost=%.6f EUR [%s]",
        feature,
        total_tokens,
        prompt_tokens,
        completion_tokens,
        llm_usage.estimated_cost_eur,
        request_id,
    )

    return response.text or ""
