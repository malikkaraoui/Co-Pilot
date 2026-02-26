"""Tests for EmailDraft model."""

from app.models.email_draft import EmailDraft


class TestEmailDraft:
    def test_create_draft(self, app, db):
        """EmailDraft stores generated email with seller info."""
        with app.app_context():
            draft = EmailDraft(
                scan_id=1,
                listing_url="https://www.leboncoin.fr/voitures/12345.htm",
                vehicle_make="Peugeot",
                vehicle_model="308",
                seller_type="private",
                seller_name="Jean Dupont",
                seller_phone="0612345678",
                prompt_used="Tu es un acheteur averti...",
                generated_text="Bonjour, je suis interesse...",
                llm_model="gemini-2.5-flash",
                tokens_used=230,
            )
            db.session.add(draft)
            db.session.commit()

            saved = EmailDraft.query.first()
            assert saved.listing_url == "https://www.leboncoin.fr/voitures/12345.htm"
            assert saved.seller_type == "private"
            assert saved.status == "draft"
            assert saved.edited_text is None

    def test_status_transitions(self, app, db):
        """EmailDraft status can be updated."""
        with app.app_context():
            draft = EmailDraft(
                scan_id=1,
                listing_url="https://example.com",
                vehicle_make="Renault",
                vehicle_model="Clio",
                seller_type="pro",
                prompt_used="test",
                generated_text="Bonjour...",
                llm_model="gemini-2.5-flash",
                tokens_used=100,
            )
            db.session.add(draft)
            db.session.commit()

            draft.status = "approved"
            draft.edited_text = "Version editee..."
            db.session.commit()

            saved = db.session.get(EmailDraft, draft.id)
            assert saved.status == "approved"
            assert saved.edited_text == "Version editee..."
