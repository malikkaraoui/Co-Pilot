"""Tests for LLMUsage model."""

from app.models.llm_usage import LLMUsage


class TestLLMUsage:
    def test_create_usage_record(self, app, db):
        """LLMUsage stores token counts and cost."""
        with app.app_context():
            usage = LLMUsage(
                request_id="req-abc-123",
                provider="gemini",
                model="gemini-2.5-flash",
                feature="email_draft",
                prompt_tokens=150,
                completion_tokens=80,
                total_tokens=230,
                estimated_cost_eur=0.0001,
            )
            db.session.add(usage)
            db.session.commit()

            saved = LLMUsage.query.first()
            assert saved.request_id == "req-abc-123"
            assert saved.provider == "gemini"
            assert saved.total_tokens == 230
            assert saved.estimated_cost_eur == 0.0001
            assert saved.created_at is not None

    def test_repr(self, app, db):
        """LLMUsage repr includes provider and feature."""
        with app.app_context():
            usage = LLMUsage(
                request_id="req-1",
                provider="gemini",
                model="gemini-2.5-flash",
                feature="email_draft",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                estimated_cost_eur=0.0,
            )
            assert "gemini" in repr(usage)
