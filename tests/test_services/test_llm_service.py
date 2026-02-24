"""Tests for llm_service (Ollama wrapper)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.llm_service import generate_synthesis, list_ollama_models


class TestListOllamaModels:
    def test_returns_model_names(self, app):
        """list_ollama_models returns list of model name strings."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "models": [
                    {"name": "mistral:latest", "size": 4_000_000_000},
                    {"name": "llama3.1:8b", "size": 8_000_000_000},
                ]
            }

            with patch("app.services.llm_service.httpx.get", return_value=mock_response):
                models = list_ollama_models()
                assert models == ["mistral:latest", "llama3.1:8b"]

    def test_returns_empty_on_non_200(self, app):
        """Returns empty list when Ollama responds with non-200 status."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 503

            with patch("app.services.llm_service.httpx.get", return_value=mock_response):
                models = list_ollama_models()
                assert models == []

    def test_returns_empty_on_connection_error(self, app):
        """Returns empty list if Ollama is not running."""
        with app.app_context():
            with patch(
                "app.services.llm_service.httpx.get",
                side_effect=httpx.ConnectError("connection refused"),
            ):
                models = list_ollama_models()
                assert models == []

    def test_returns_empty_when_no_models(self, app):
        """Returns empty list when Ollama has no models installed."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"models": []}

            with patch("app.services.llm_service.httpx.get", return_value=mock_response):
                models = list_ollama_models()
                assert models == []


class TestGenerateSynthesis:
    def test_returns_generated_text(self, app):
        """generate_synthesis returns the LLM response text."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": "Points forts: confort. Points faibles: consommation."
            }

            with patch(
                "app.services.llm_service.httpx.post", return_value=mock_response
            ) as mock_post:
                result = generate_synthesis(
                    model="mistral",
                    prompt="Analyse ce vehicule",
                    transcripts="Transcript text here...",
                )
                assert "Points forts" in result

                # Verify the prompt is correctly assembled
                call_kwargs = mock_post.call_args
                body = call_kwargs.kwargs["json"]
                assert body["model"] == "mistral"
                assert body["stream"] is False
                assert "--- TRANSCRIPTS ---" in body["prompt"]
                assert "Transcript text here..." in body["prompt"]

    def test_raises_on_ollama_error(self, app):
        """Raises ConnectionError if Ollama returns non-200."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "internal error"

            with patch("app.services.llm_service.httpx.post", return_value=mock_response):
                with pytest.raises(ConnectionError, match="Ollama erreur 500"):
                    generate_synthesis(
                        model="mistral",
                        prompt="test",
                        transcripts="text",
                    )

    def test_raises_on_connection_failure(self, app):
        """Raises ConnectionError if Ollama is unreachable."""
        with app.app_context():
            with patch(
                "app.services.llm_service.httpx.post",
                side_effect=httpx.ConnectError("connection refused"),
            ):
                with pytest.raises(ConnectionError, match="Ollama injoignable"):
                    generate_synthesis(
                        model="mistral",
                        prompt="test",
                        transcripts="text",
                    )

    def test_returns_empty_string_when_response_key_missing(self, app):
        """Returns empty string if 'response' key is absent from JSON."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}

            with patch("app.services.llm_service.httpx.post", return_value=mock_response):
                result = generate_synthesis(
                    model="mistral",
                    prompt="test",
                    transcripts="text",
                )
                assert result == ""
