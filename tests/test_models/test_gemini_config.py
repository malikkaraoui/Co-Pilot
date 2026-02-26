"""Tests for GeminiConfig and GeminiPromptConfig models."""

from app.models.gemini_config import GeminiConfig, GeminiPromptConfig


class TestGeminiConfig:
    def test_create_config(self, app, db):
        """GeminiConfig stores API settings."""
        with app.app_context():
            cfg = GeminiConfig(
                api_key_encrypted="encrypted-key-here",
                model_name="gemini-2.5-flash",
                max_daily_requests=500,
                max_daily_cost_eur=1.0,
                is_active=True,
            )
            db.session.add(cfg)
            db.session.commit()

            saved = GeminiConfig.query.first()
            assert saved.model_name == "gemini-2.5-flash"
            assert saved.is_active is True
            assert saved.max_daily_requests == 500


class TestGeminiPromptConfig:
    def test_create_prompt_config(self, app, db):
        """GeminiPromptConfig stores prompt templates with parameters."""
        with app.app_context():
            prompt = GeminiPromptConfig(
                name="email_vendeur_v1",
                system_prompt="Tu es un acheteur averti et direct.",
                task_prompt_template="Vehicule: {make} {model}\nPrix: {price}",
                max_output_tokens=500,
                temperature=0.3,
                top_p=0.9,
                hallucination_guard="Ne mentionne que les faits issus des donnees fournies.",
                is_active=True,
                version=1,
            )
            db.session.add(prompt)
            db.session.commit()

            saved = GeminiPromptConfig.query.first()
            assert saved.name == "email_vendeur_v1"
            assert saved.temperature == 0.3
            assert saved.is_active is True
            assert saved.version == 1

    def test_multiple_active_prompts_allowed_at_db_level(self, app, db):
        """Both can be active at DB level (business logic enforces single active)."""
        with app.app_context():
            p1 = GeminiPromptConfig(
                name="v1",
                system_prompt="a",
                task_prompt_template="b",
                max_output_tokens=100,
                temperature=0.5,
                is_active=True,
                version=1,
            )
            p2 = GeminiPromptConfig(
                name="v2",
                system_prompt="c",
                task_prompt_template="d",
                max_output_tokens=200,
                temperature=0.7,
                is_active=True,
                version=2,
            )
            db.session.add_all([p1, p2])
            db.session.commit()

            saved_p1 = db.session.get(GeminiPromptConfig, p1.id)
            saved_p2 = db.session.get(GeminiPromptConfig, p2.id)
            assert saved_p1.is_active is True
            assert saved_p2.is_active is True
