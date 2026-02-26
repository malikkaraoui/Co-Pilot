"""Tests for gemini_service (Google Gemini wrapper)."""

from unittest.mock import MagicMock, patch

import pytest

from app.models.llm_usage import LLMUsage
from app.services.gemini_service import check_health, generate_text


class TestCheckHealth:
    def test_returns_true_when_api_reachable(self, app, db):
        """check_health returns True when Gemini API responds."""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.text = "OK"
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response

            with (
                patch("app.services.gemini_service._get_api_key", return_value="fake-key"),
                patch("app.services.gemini_service._get_client", return_value=mock_client),
            ):
                assert check_health() is True

    def test_returns_false_when_no_api_key(self, app, db):
        """check_health returns False when API key is empty."""
        with app.app_context():
            with patch("app.services.gemini_service._get_api_key", return_value=""):
                assert check_health() is False

    def test_returns_false_on_error(self, app, db):
        """check_health returns False when API raises."""
        with app.app_context():
            with (
                patch("app.services.gemini_service._get_api_key", return_value="fake-key"),
                patch(
                    "app.services.gemini_service._get_client",
                    side_effect=Exception("auth failed"),
                ),
            ):
                assert check_health() is False


class TestGenerateText:
    def test_returns_generated_text(self, app, db):
        """generate_text returns LLM response and logs usage."""
        with app.app_context():
            mock_usage = MagicMock()
            mock_usage.prompt_token_count = 100
            mock_usage.candidates_token_count = 50
            mock_usage.total_token_count = 150

            mock_response = MagicMock()
            mock_response.text = "Bonjour, je suis interesse par votre vehicule."
            mock_response.usage_metadata = mock_usage

            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response

            with (
                patch("app.services.gemini_service._get_api_key", return_value="fake-key"),
                patch("app.services.gemini_service._get_client", return_value=mock_client),
            ):
                text, tokens = generate_text(
                    prompt="Redige un email",
                    feature="email_draft",
                    temperature=0.3,
                    max_output_tokens=500,
                )

            assert "interesse" in text
            assert tokens == 150
            usage = LLMUsage.query.order_by(LLMUsage.id.desc()).first()
            assert usage is not None
            assert usage.provider == "gemini"
            assert usage.feature == "email_draft"
            assert usage.prompt_tokens == 100
            assert usage.completion_tokens == 50

    def test_raises_on_empty_api_key(self, app, db):
        """generate_text raises ValueError when no API key configured."""
        with app.app_context():
            with patch("app.services.gemini_service._get_api_key", return_value=""):
                with pytest.raises(ValueError, match="API key"):
                    generate_text(prompt="test", feature="test")

    def test_raises_on_api_error(self, app, db):
        """generate_text raises ConnectionError on API failure."""
        with app.app_context():
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = Exception("rate limited")

            with (
                patch("app.services.gemini_service._get_api_key", return_value="fake-key"),
                patch("app.services.gemini_service._get_client", return_value=mock_client),
            ):
                with pytest.raises(ConnectionError, match="Gemini"):
                    generate_text(prompt="test", feature="test")
