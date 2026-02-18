"""Tests des modeles YouTubeVideo et YouTubeTranscript."""

import pytest

from app.extensions import db as _db
from app.models.vehicle import Vehicle
from app.models.youtube import YouTubeTranscript, YouTubeVideo


class TestYouTubeVideoModel:
    """Tests du modele YouTubeVideo."""

    def test_create_video(self, app):
        with app.app_context():
            video = YouTubeVideo(
                video_id="dQw4w9WgXc",
                title="Test video",
                channel_name="Test Channel",
                duration_seconds=300,
            )
            _db.session.add(video)
            _db.session.commit()

            assert video.id is not None
            assert video.video_id == "dQw4w9WgXc"
            assert video.is_archived is False
            assert video.created_at is not None

            _db.session.delete(video)
            _db.session.commit()

    def test_unique_video_id(self, app):
        with app.app_context():
            v1 = YouTubeVideo(video_id="UNIQUE_ID_1", title="Video 1")
            _db.session.add(v1)
            _db.session.commit()

            v2 = YouTubeVideo(video_id="UNIQUE_ID_1", title="Video 2")
            _db.session.add(v2)
            with pytest.raises(Exception):
                _db.session.commit()
            _db.session.rollback()

            _db.session.delete(v1)
            _db.session.commit()

    def test_vehicle_relationship(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="TestBrand", model="TestModel")
            _db.session.add(vehicle)
            _db.session.commit()

            video = YouTubeVideo(
                video_id="VEH_REL_01",
                title="Vehicle test video",
                vehicle_id=vehicle.id,
            )
            _db.session.add(video)
            _db.session.commit()

            assert video.vehicle is not None
            assert video.vehicle.brand == "TestBrand"
            assert video in vehicle.youtube_videos

            _db.session.delete(video)
            _db.session.delete(vehicle)
            _db.session.commit()

    def test_vehicle_id_nullable(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="NO_VEH_01", title="No vehicle video")
            _db.session.add(video)
            _db.session.commit()

            assert video.vehicle_id is None
            assert video.vehicle is None

            _db.session.delete(video)
            _db.session.commit()

    def test_repr(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="REPR_TEST1", title="A long title for repr testing")
            assert "REPR_TEST1" in repr(video)


class TestYouTubeTranscriptModel:
    """Tests du modele YouTubeTranscript."""

    def test_create_transcript(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="TRANS_01", title="Transcript test")
            _db.session.add(video)
            _db.session.commit()

            transcript = YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                is_generated=True,
                full_text="Bonjour ceci est un test",
                snippet_count=1,
                char_count=25,
                status="extracted",
            )
            _db.session.add(transcript)
            _db.session.commit()

            assert transcript.id is not None
            assert transcript.status == "extracted"
            assert transcript.char_count == 25

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()

    def test_default_status_pending(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="PEND_01", title="Pending test")
            _db.session.add(video)
            _db.session.commit()

            transcript = YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                full_text="",
            )
            _db.session.add(transcript)
            _db.session.commit()

            assert transcript.status == "pending"

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()

    def test_one_to_one_relationship(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="OTO_01", title="One to one")
            _db.session.add(video)
            _db.session.commit()

            transcript = YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                full_text="Test",
                status="extracted",
            )
            _db.session.add(transcript)
            _db.session.commit()

            assert video.transcript is not None
            assert video.transcript.id == transcript.id
            assert transcript.video.id == video.id

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()

    def test_cascade_delete(self, app):
        with app.app_context():
            video = YouTubeVideo(video_id="CASCADE_01", title="Cascade test")
            _db.session.add(video)
            _db.session.commit()

            transcript = YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                full_text="Will be deleted",
                status="extracted",
            )
            _db.session.add(transcript)
            _db.session.commit()
            transcript_id = transcript.id

            _db.session.delete(video)
            _db.session.commit()

            assert YouTubeTranscript.query.get(transcript_id) is None
