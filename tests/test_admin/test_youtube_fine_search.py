"""Tests for YouTube fine search admin routes."""

from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_synthesis import VehicleSynthesis
from app.models.youtube import YouTubeTranscript, YouTubeVideo


@pytest.fixture()
def admin_user(app):
    """Create an admin user for testing."""
    with app.app_context():
        user = User.query.filter_by(username="testadmin").first()
        if not user:
            user = User(
                username="testadmin",
                password_hash=generate_password_hash("testpass"),
                is_admin=True,
            )
            db.session.add(user)
            db.session.commit()
    return user


def _login(client, username="testadmin", password="testpass"):
    return client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def _ensure_vehicle(app, brand="Peugeot", model="308"):
    """Ensure a vehicle exists, handling potential duplicates from seed data."""
    with app.app_context():
        v = Vehicle.query.filter_by(brand=brand, model=model).first()
        if not v:
            v = Vehicle(brand=brand, model=model, year_start=2013)
            db.session.add(v)
            db.session.commit()
        return v.id


def _create_video_with_transcript(app, vehicle_id, video_id_str="abc123"):
    """Create a YouTubeVideo with an extracted transcript for testing."""
    with app.app_context():
        existing = YouTubeVideo.query.filter_by(video_id=video_id_str).first()
        if existing:
            return existing.id
        video = YouTubeVideo(
            video_id=video_id_str,
            title="Test Video Peugeot 308",
            channel_name="Auto Plus",
            vehicle_id=vehicle_id,
            search_query="test",
        )
        db.session.add(video)
        db.session.flush()
        transcript = YouTubeTranscript(
            video_db_id=video.id,
            language="fr",
            is_generated=False,
            full_text="La Peugeot 308 est une voiture confortable et bien equipee.",
            status="extracted",
            snippet_count=1,
            char_count=58,
        )
        db.session.add(transcript)
        db.session.commit()
        return video.id


class TestYouTubeFineSearchGet:
    """GET /admin/youtube/fine-search page."""

    def test_page_loads(self, client, admin_user):
        _login(client)
        with patch(
            "app.services.llm_service.list_ollama_models",
            return_value=["qwen3:8b"],
        ):
            resp = client.get("/admin/youtube/fine-search")
        assert resp.status_code == 200
        assert b"YouTube Recherche Fine" in resp.data

    def test_shows_brand_select(self, app, client, admin_user):
        _ensure_vehicle(app)
        _login(client)
        with patch(
            "app.services.llm_service.list_ollama_models",
            return_value=["mistral"],
        ):
            resp = client.get("/admin/youtube/fine-search")
        assert b"Peugeot" in resp.data

    def test_shows_ollama_models(self, client, admin_user):
        _login(client)
        with patch(
            "app.services.llm_service.list_ollama_models",
            return_value=["qwen3:8b", "mistral"],
        ):
            resp = client.get("/admin/youtube/fine-search")
        assert b"qwen3:8b" in resp.data
        assert b"mistral" in resp.data


class TestYouTubeFineSearchPost:
    """POST /admin/youtube/fine-search pipeline."""

    def test_missing_make_shows_error(self, client, admin_user):
        _login(client)
        with patch(
            "app.services.llm_service.list_ollama_models",
            return_value=["mistral"],
        ):
            resp = client.post(
                "/admin/youtube/fine-search",
                data={"make": "", "model": "308"},
            )
        assert resp.status_code == 200
        assert b"Marque et modele sont requis" in resp.data

    def test_pipeline_stores_synthesis(self, app, client, admin_user):
        """Full pipeline with real video DB records + mocked search & LLM."""
        vid_vehicle_id = _ensure_vehicle(app)
        vid_db_id = _create_video_with_transcript(app, vid_vehicle_id)

        _login(client)

        mock_stats = {
            "videos_found": 1,
            "transcripts_ok": 1,
            "transcripts_failed": 0,
            "transcripts_skipped": 0,
            "video_ids": [vid_db_id],
        }

        with (
            patch(
                "app.services.llm_service.list_ollama_models",
                return_value=["qwen3:8b"],
            ),
            patch(
                "app.services.youtube_service.search_and_extract_custom",
                return_value=mock_stats,
            ),
            patch(
                "app.services.llm_service.generate_synthesis",
                return_value="Points forts: confort, design. Points faibles: coffre petit.",
            ),
            patch(
                "app.services.youtube_service.build_search_query",
                return_value="Peugeot 308 2019 diesel",
            ),
        ):
            resp = client.post(
                "/admin/youtube/fine-search",
                data={
                    "make": "Peugeot",
                    "model": "308",
                    "year": "2019",
                    "fuel": "diesel",
                    "hp": "",
                    "keywords": "",
                    "max_results": "5",
                    "llm_model": "qwen3:8b",
                    "prompt": "test prompt",
                },
            )

        assert resp.status_code == 200
        assert b"Points forts: confort, design" in resp.data

        # Verify VehicleSynthesis was stored
        with app.app_context():
            synth = VehicleSynthesis.query.filter_by(
                make="Peugeot", model="308", llm_model="qwen3:8b"
            ).first()
            assert synth is not None
            assert synth.status == "draft"
            assert synth.raw_transcript_chars > 0

    def test_pipeline_no_transcripts_shows_warning(self, app, client, admin_user):
        """Pipeline with 0 transcripts shows warning."""
        _ensure_vehicle(app)
        _login(client)

        mock_stats = {
            "videos_found": 2,
            "transcripts_ok": 0,
            "transcripts_failed": 2,
            "transcripts_skipped": 0,
            "video_ids": [],
        }

        with (
            patch(
                "app.services.llm_service.list_ollama_models",
                return_value=["qwen3:8b"],
            ),
            patch(
                "app.services.youtube_service.search_and_extract_custom",
                return_value=mock_stats,
            ),
            patch(
                "app.services.youtube_service.build_search_query",
                return_value="Peugeot 308",
            ),
        ):
            resp = client.post(
                "/admin/youtube/fine-search",
                data={
                    "make": "Peugeot",
                    "model": "308",
                    "max_results": "5",
                    "llm_model": "qwen3:8b",
                    "prompt": "test",
                },
            )

        assert resp.status_code == 200
        assert b"Aucun transcript extrait" in resp.data


class TestYouTubeSynthesisValidate:
    """POST validate route."""

    def test_validate_draft_synthesis(self, app, client, admin_user):
        with app.app_context():
            synth = VehicleSynthesis(
                make="Renault",
                model="Clio",
                llm_model="mistral",
                prompt_used="test",
                synthesis_text="synthese test",
                status="draft",
            )
            db.session.add(synth)
            db.session.commit()
            synth_id = synth.id

        _login(client)
        resp = client.post(
            f"/admin/youtube/synthesis/{synth_id}/validate",
            follow_redirects=False,
        )
        assert resp.status_code == 302

        with app.app_context():
            updated = db.session.get(VehicleSynthesis, synth_id)
            assert updated.status == "validated"

    def test_validate_nonexistent_returns_404(self, client, admin_user):
        _login(client)
        resp = client.post("/admin/youtube/synthesis/9999/validate")
        assert resp.status_code == 404
