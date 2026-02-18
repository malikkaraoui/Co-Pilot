"""Tests des routes admin YouTube."""

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db as _db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.youtube import YouTubeTranscript, YouTubeVideo


@pytest.fixture()
def admin_user(app):
    """Cree un utilisateur admin pour les tests."""
    with app.app_context():
        user = User.query.filter_by(username="testadmin").first()
        if not user:
            user = User(
                username="testadmin",
                password_hash=generate_password_hash("testpass"),
                is_admin=True,
            )
            _db.session.add(user)
            _db.session.commit()
    return user


def _login(client, username="testadmin", password="testpass"):
    return client.post(
        "/admin/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


@pytest.fixture()
def _sample_data(app):
    """Cree des donnees YouTube de test."""
    with app.app_context():
        vehicle = Vehicle(brand="TestYT", model="Model1")
        _db.session.add(vehicle)
        _db.session.commit()

        video1 = YouTubeVideo(
            video_id="ADMIN_YT_1",
            title="Essai TestYT Model1",
            channel_name="AutoTest",
            duration_seconds=600,
            vehicle_id=vehicle.id,
        )
        video2 = YouTubeVideo(
            video_id="ADMIN_YT_2",
            title="Test TestYT Model1 2024",
            channel_name="CarReview",
            vehicle_id=vehicle.id,
        )
        _db.session.add_all([video1, video2])
        _db.session.commit()

        transcript1 = YouTubeTranscript(
            video_db_id=video1.id,
            language="fr",
            is_generated=True,
            full_text="Bonjour nous allons tester le TestYT Model1",
            snippet_count=5,
            char_count=45,
            status="extracted",
        )
        transcript2 = YouTubeTranscript(
            video_db_id=video2.id,
            language="fr",
            full_text="",
            status="no_subtitles",
        )
        _db.session.add_all([transcript1, transcript2])
        _db.session.commit()

        yield {
            "vehicle": vehicle,
            "video1": video1,
            "video2": video2,
            "transcript1": transcript1,
            "transcript2": transcript2,
        }

        # Cleanup
        _db.session.delete(transcript1)
        _db.session.delete(transcript2)
        _db.session.delete(video1)
        _db.session.delete(video2)
        _db.session.delete(vehicle)
        _db.session.commit()


class TestYouTubeListPage:
    """Tests de la page liste YouTube."""

    def test_youtube_page_requires_login(self, client):
        client.get("/admin/logout")  # Ensure logged out
        resp = client.get("/admin/youtube")
        assert resp.status_code == 302
        assert "/admin/login" in resp.headers["Location"]

    def test_youtube_page_renders(self, client, admin_user, _sample_data):
        _login(client)
        resp = client.get("/admin/youtube")
        assert resp.status_code == 200
        assert b"YouTube Tests" in resp.data

    def test_youtube_stat_cards(self, client, admin_user, _sample_data):
        _login(client)
        resp = client.get("/admin/youtube")
        assert resp.status_code == 200
        # Should contain video count and transcript stats
        assert b"Videos en base" in resp.data
        assert b"Transcripts extraits" in resp.data
        assert b"Couverture vehicules" in resp.data

    def test_youtube_shows_videos(self, client, admin_user, _sample_data):
        _login(client)
        resp = client.get("/admin/youtube")
        assert b"Essai TestYT Model1" in resp.data
        assert b"ADMIN_YT_1" in resp.data

    def test_youtube_filter_by_status(self, client, admin_user, _sample_data):
        _login(client)
        resp = client.get("/admin/youtube?status=extracted")
        assert resp.status_code == 200
        assert b"ADMIN_YT_1" in resp.data

    def test_youtube_filter_by_vehicle(self, client, admin_user, _sample_data):
        _login(client)
        vehicle = _sample_data["vehicle"]
        resp = client.get(f"/admin/youtube?vehicle_id={vehicle.id}")
        assert resp.status_code == 200
        assert b"Essai TestYT Model1" in resp.data

    def test_youtube_empty_page(self, client, admin_user):
        _login(client)
        resp = client.get("/admin/youtube")
        assert resp.status_code == 200
        assert b"Aucune video" in resp.data


class TestYouTubeDetailPage:
    """Tests de la page detail video."""

    def test_detail_page_renders(self, client, admin_user, _sample_data):
        _login(client)
        video = _sample_data["video1"]
        resp = client.get(f"/admin/youtube/{video.id}")
        assert resp.status_code == 200
        assert b"Essai TestYT Model1" in resp.data
        assert b"Bonjour nous allons tester" in resp.data

    def test_detail_404_for_nonexistent(self, client, admin_user):
        _login(client)
        resp = client.get("/admin/youtube/99999")
        assert resp.status_code == 404


class TestYouTubeArchive:
    """Tests de l'archivage de videos."""

    def test_archive_toggle(self, client, admin_user, _sample_data):
        _login(client)
        video = _sample_data["video1"]

        # Archive
        resp = client.post(f"/admin/youtube/{video.id}/archive", follow_redirects=True)
        assert resp.status_code == 200
        assert b"archivee" in resp.data

        # Desarchive
        resp = client.post(f"/admin/youtube/{video.id}/archive", follow_redirects=True)
        assert resp.status_code == 200
        assert b"restauree" in resp.data


class TestYouTubeFeatured:
    """Tests du toggle featured."""

    def test_featured_toggle(self, client, admin_user, _sample_data):
        _login(client)
        video = _sample_data["video1"]

        # Marquer featured
        resp = client.post(f"/admin/youtube/{video.id}/featured", follow_redirects=True)
        assert resp.status_code == 200
        assert b"Video featured" in resp.data

        # Retirer featured
        resp = client.post(f"/admin/youtube/{video.id}/featured", follow_redirects=True)
        assert resp.status_code == 200
        assert b"retiree du featured" in resp.data

    def test_featured_exclusive_per_vehicle(self, client, admin_user, _sample_data, app):
        """Une seule video featured par vehicule."""
        _login(client)
        video1 = _sample_data["video1"]
        video2 = _sample_data["video2"]

        # Marquer video1 featured
        client.post(f"/admin/youtube/{video1.id}/featured", follow_redirects=True)

        # Marquer video2 featured → video1 perd son featured
        client.post(f"/admin/youtube/{video2.id}/featured", follow_redirects=True)

        with app.app_context():
            v1 = YouTubeVideo.query.get(video1.id)
            v2 = YouTubeVideo.query.get(video2.id)
            assert v1.is_featured is False
            assert v2.is_featured is True
