"""Tests for YouTube fine search admin routes (async pipeline)."""

import time
from unittest.mock import patch

import pytest
from werkzeug.security import generate_password_hash

from app.admin.routes import _synthesis_jobs
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


def _wait_for_job(job_id: str, timeout: float = 5.0) -> dict:
    """Wait for a background job to complete."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = _synthesis_jobs.get(job_id)
        if job and job["status"] in ("done", "error", "cancelled"):
            return job
        time.sleep(0.1)
    return _synthesis_jobs.get(job_id, {})


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
    """POST /admin/youtube/fine-search — async pipeline."""

    def test_missing_make_redirects(self, client, admin_user):
        _login(client)
        resp = client.post(
            "/admin/youtube/fine-search",
            data={"make": "", "model": "308"},
        )
        # Missing make → redirect back with flash
        assert resp.status_code == 302

    def test_post_creates_job_and_redirects(self, client, admin_user):
        _login(client)
        with (
            patch(
                "app.services.youtube_service.search_and_extract_custom",
                return_value={
                    "videos_found": 0,
                    "transcripts_ok": 0,
                    "transcripts_failed": 0,
                    "video_ids": [],
                },
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
                    "max_results": "3",
                    "llm_model": "mistral",
                    "prompt": "test",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert "job_id=" in resp.headers["Location"]

    def test_pipeline_stores_synthesis(self, app, client, admin_user):
        """Full pipeline with mocked search & LLM stores a VehicleSynthesis."""
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
                "app.services.youtube_service.search_and_extract_custom",
                return_value=mock_stats,
            ),
            patch(
                "app.services.llm_service.generate_synthesis",
                return_value="Points forts: confort. Points faibles: coffre.",
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
                    "max_results": "5",
                    "llm_model": "qwen3:8b",
                    "prompt": "test prompt",
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302
        # Extract job_id from redirect URL
        location = resp.headers["Location"]
        job_id = location.split("job_id=")[1]

        # Wait for background thread to finish
        job = _wait_for_job(job_id)
        assert job["status"] == "done"

        # Verify VehicleSynthesis was stored
        with app.app_context():
            synth = VehicleSynthesis.query.filter_by(
                make="Peugeot", model="308", llm_model="qwen3:8b"
            ).first()
            assert synth is not None
            assert synth.status == "draft"
            assert synth.raw_transcript_chars > 0

    def test_pipeline_no_transcripts(self, app, client, admin_user):
        """Pipeline with 0 transcripts finishes without synthesis."""
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
                follow_redirects=False,
            )

        job_id = resp.headers["Location"].split("job_id=")[1]
        job = _wait_for_job(job_id)
        assert job["status"] == "done"
        # No synthesis because no transcripts
        assert job["result"]["synthesis_text"] == ""


class TestYouTubeJobStatus:
    """GET /admin/youtube/job-status/<job_id>."""

    def test_nonexistent_job_returns_404(self, client, admin_user):
        _login(client)
        resp = client.get("/admin/youtube/job-status/nonexistent")
        assert resp.status_code == 404

    def test_returns_job_data(self, client, admin_user):
        """Inject a fake job and check status endpoint."""
        from app.admin.routes import _jobs_lock

        fake_job = {
            "id": "test123",
            "status": "done",
            "progress": 100,
            "progress_label": "Termine",
            "pipeline_log": [{"step": 1, "label": "Test", "status": "ok", "detail": "ok"}],
            "videos_detail": [],
            "result": {
                "synthesis_text": "test",
                "videos_found": 0,
                "transcripts_ok": 0,
                "total_chars": 0,
                "query": "q",
                "synthesis_id": None,
                "llm_model": "m",
                "llm_duration": 0,
                "search_duration": 0,
                "prompt_used": "p",
            },
            "form_data": {"make": "Test", "model": "T"},
        }
        with _jobs_lock:
            _synthesis_jobs["test123"] = fake_job

        _login(client)
        resp = client.get("/admin/youtube/job-status/test123")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "done"
        assert data["progress"] == 100

        # Cleanup
        with _jobs_lock:
            _synthesis_jobs.pop("test123", None)


class TestYouTubeJobStop:
    """POST /admin/youtube/job-stop/<job_id>."""

    def test_stop_nonexistent_returns_404(self, client, admin_user):
        _login(client)
        resp = client.post("/admin/youtube/job-stop/nonexistent")
        assert resp.status_code == 404

    def test_stop_sets_cancelled_flag(self, client, admin_user):
        from app.admin.routes import _jobs_lock

        fake_job = {
            "id": "stop1",
            "status": "running",
            "progress": 50,
            "progress_label": "En cours",
            "pipeline_log": [],
            "videos_detail": [],
            "result": None,
            "cancelled": False,
            "form_data": {},
        }
        with _jobs_lock:
            _synthesis_jobs["stop1"] = fake_job

        _login(client)
        resp = client.post("/admin/youtube/job-stop/stop1")
        assert resp.status_code == 200
        assert fake_job["cancelled"] is True

        # Cleanup
        with _jobs_lock:
            _synthesis_jobs.pop("stop1", None)


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
