"""Tests du service YouTube (recherche + extraction sous-titres)."""

from unittest.mock import MagicMock, patch

import pytest

from app.extensions import db as _db
from app.models.vehicle import Vehicle
from app.models.youtube import YouTubeTranscript, YouTubeVideo
from app.services.youtube_service import (
    extract_and_store_transcript,
    fetch_transcript,
    get_featured_video,
    search_and_extract_for_vehicle,
    search_videos,
    store_video,
)


class TestSearchVideos:
    """Tests de la recherche YouTube via yt-dlp."""

    @patch("app.services.youtube_service.yt_dlp.YoutubeDL")
    def test_search_returns_videos(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Essai Peugeot 208",
                    "channel": "AutoMoto",
                    "duration": 600,
                },
                {"id": "def456", "title": "Test 208", "channel": "TurboFR", "duration": 420},
            ]
        }
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        results = search_videos("Peugeot 208 essai", max_results=2)
        assert len(results) == 2
        assert results[0]["id"] == "abc123"
        assert results[0]["title"] == "Essai Peugeot 208"
        assert results[0]["channel"] == "AutoMoto"
        assert results[0]["duration"] == 600

    @patch("app.services.youtube_service.yt_dlp.YoutubeDL")
    def test_search_empty_results(self, mock_ydl_cls):
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {"entries": []}
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        results = search_videos("vehicule introuvable xyz", max_results=5)
        assert results == []


class TestFetchTranscript:
    """Tests de l'extraction de transcripts."""

    @patch("app.services.youtube_service.YouTubeTranscriptApi")
    def test_fetch_french_transcript(self, mock_api_cls):
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_transcript = MagicMock()
        mock_transcript.language_code = "fr"
        mock_transcript.is_generated = True
        mock_transcript.to_raw_data.return_value = [
            {"text": "Bonjour", "start": 0.0, "duration": 2.0},
            {"text": "je teste", "start": 2.0, "duration": 1.5},
        ]
        mock_api.fetch.return_value = mock_transcript

        result = fetch_transcript("abc123")
        assert result is not None
        assert result["language"] == "fr"
        assert result["is_generated"] is True
        assert result["snippet_count"] == 2
        assert result["char_count"] == len("Bonjour je teste")
        assert "Bonjour" in result["full_text"]

    @patch("app.services.youtube_service.YouTubeTranscriptApi")
    def test_fetch_no_transcript_returns_none(self, mock_api_cls):
        from youtube_transcript_api._errors import NoTranscriptFound

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.fetch.side_effect = NoTranscriptFound("abc123", ["fr"], [])

        # Also mock list() to return empty (no translatable)
        mock_list = MagicMock()
        mock_list.__iter__ = MagicMock(return_value=iter([]))
        mock_api.list.return_value = mock_list

        result = fetch_transcript("abc123")
        assert result is None

    @patch("app.services.youtube_service.YouTubeTranscriptApi")
    def test_fetch_transcripts_disabled_returns_none(self, mock_api_cls):
        from youtube_transcript_api._errors import TranscriptsDisabled

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.fetch.side_effect = TranscriptsDisabled("abc123")

        result = fetch_transcript("abc123")
        assert result is None

    @patch("app.services.youtube_service.YouTubeTranscriptApi")
    def test_fetch_request_blocked_raises(self, mock_api_cls):
        from youtube_transcript_api._errors import RequestBlocked

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.fetch.side_effect = RequestBlocked("abc123")

        with pytest.raises(RequestBlocked):
            fetch_transcript("abc123")


class TestStoreVideo:
    """Tests du stockage de videos en base."""

    def test_store_new_video(self, app):
        with app.app_context():
            video_data = {
                "id": "STORE_01",
                "title": "Store test",
                "channel": "Chan",
                "duration": 300,
            }
            video = store_video(video_data)
            assert video.id is not None
            assert video.video_id == "STORE_01"
            assert video.title == "Store test"

            _db.session.delete(video)
            _db.session.commit()

    def test_store_idempotent(self, app):
        with app.app_context():
            video_data = {"id": "IDEMP_01", "title": "First", "channel": "Ch", "duration": 100}
            v1 = store_video(video_data)
            v2 = store_video(video_data)
            assert v1.id == v2.id

            _db.session.delete(v1)
            _db.session.commit()

    def test_store_with_vehicle_id(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="StoreBrand", model="StoreModel")
            _db.session.add(vehicle)
            _db.session.commit()

            video_data = {
                "id": "VEH_STORE",
                "title": "With vehicle",
                "channel": "",
                "duration": 200,
            }
            video = store_video(video_data, vehicle_id=vehicle.id, search_query="test query")
            assert video.vehicle_id == vehicle.id
            assert video.search_query == "test query"

            _db.session.delete(video)
            _db.session.delete(vehicle)
            _db.session.commit()


class TestExtractAndStoreTranscript:
    """Tests de l'extraction et stockage de transcripts."""

    @patch("app.services.youtube_service.fetch_transcript")
    def test_extract_success(self, mock_fetch, app):
        with app.app_context():
            video = YouTubeVideo(video_id="EXT_OK_01", title="Extract OK")
            _db.session.add(video)
            _db.session.commit()

            mock_fetch.return_value = {
                "language": "fr",
                "is_generated": True,
                "full_text": "Bonjour ceci est un test de transcript",
                "snippets": [{"text": "Bonjour", "start": 0, "duration": 2}],
                "snippet_count": 1,
                "char_count": 38,
            }

            transcript = extract_and_store_transcript(video)
            assert transcript.status == "extracted"
            assert transcript.char_count == 38
            assert transcript.language == "fr"

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()

    @patch("app.services.youtube_service.fetch_transcript")
    def test_extract_no_subtitles(self, mock_fetch, app):
        with app.app_context():
            video = YouTubeVideo(video_id="EXT_NO_01", title="No subs")
            _db.session.add(video)
            _db.session.commit()

            mock_fetch.return_value = None

            transcript = extract_and_store_transcript(video)
            assert transcript.status == "no_subtitles"

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()

    @patch("app.services.youtube_service.fetch_transcript")
    def test_extract_skips_already_extracted(self, mock_fetch, app):
        with app.app_context():
            video = YouTubeVideo(video_id="EXT_SKIP1", title="Already done")
            _db.session.add(video)
            _db.session.commit()

            transcript = YouTubeTranscript(
                video_db_id=video.id,
                language="fr",
                full_text="Already extracted",
                status="extracted",
                char_count=17,
            )
            _db.session.add(transcript)
            _db.session.commit()

            result = extract_and_store_transcript(video)
            assert result.id == transcript.id
            mock_fetch.assert_not_called()

            _db.session.delete(transcript)
            _db.session.delete(video)
            _db.session.commit()


class TestSearchAndExtractForVehicle:
    """Tests du pipeline complet pour un vehicule."""

    @patch("app.services.youtube_service.extract_and_store_transcript")
    @patch("app.services.youtube_service.search_videos")
    @patch("app.services.youtube_service.time")
    def test_full_pipeline(self, mock_time, mock_search, mock_extract, app):
        with app.app_context():
            vehicle = Vehicle(brand="PipelineBrand", model="PipelineModel")
            _db.session.add(vehicle)
            _db.session.commit()

            mock_search.return_value = [
                {"id": "PIPE_V1", "title": "Video 1", "channel": "Ch1", "duration": 300},
                {"id": "PIPE_V2", "title": "Video 2", "channel": "Ch2", "duration": 400},
            ]

            mock_transcript = MagicMock()
            mock_transcript.status = "extracted"
            mock_extract.return_value = mock_transcript

            stats = search_and_extract_for_vehicle(vehicle, max_videos=2)

            assert stats["videos_found"] == 2
            assert stats["transcripts_ok"] == 2
            assert stats["transcripts_failed"] == 0

            # Cleanup
            for v in YouTubeVideo.query.filter(
                YouTubeVideo.video_id.in_(["PIPE_V1", "PIPE_V2"])
            ).all():
                _db.session.delete(v)
            _db.session.delete(vehicle)
            _db.session.commit()

    @patch("app.services.youtube_service.search_videos")
    def test_search_failure(self, mock_search, app):
        with app.app_context():
            vehicle = Vehicle(brand="FailBrand", model="FailModel")
            _db.session.add(vehicle)
            _db.session.commit()

            mock_search.side_effect = OSError("Network error")

            stats = search_and_extract_for_vehicle(vehicle, max_videos=5)
            assert stats["videos_found"] == 0
            assert stats["transcripts_ok"] == 0

            _db.session.delete(vehicle)
            _db.session.commit()


class TestGetFeaturedVideo:
    """Tests de la recherche de video featured."""

    def test_returns_featured_video(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="FeatBrand", model="FeatModel")
            _db.session.add(vehicle)
            _db.session.commit()

            video = YouTubeVideo(
                video_id="FEAT_01",
                title="Featured test video",
                channel_name="TestChannel",
                vehicle_id=vehicle.id,
                is_featured=True,
            )
            _db.session.add(video)
            _db.session.commit()

            result = get_featured_video("FeatBrand", "FeatModel")
            assert result is not None
            assert result["video_id"] == "FEAT_01"
            assert "youtube.com" in result["url"]
            assert result["title"] == "Featured test video"

            _db.session.delete(video)
            _db.session.delete(vehicle)
            _db.session.commit()

    def test_returns_none_when_no_featured(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="NoFeatBrand", model="NoFeatModel")
            _db.session.add(vehicle)
            _db.session.commit()

            video = YouTubeVideo(
                video_id="NOFEAT_01",
                title="Not featured",
                vehicle_id=vehicle.id,
                is_featured=False,
            )
            _db.session.add(video)
            _db.session.commit()

            result = get_featured_video("NoFeatBrand", "NoFeatModel")
            assert result is None

            _db.session.delete(video)
            _db.session.delete(vehicle)
            _db.session.commit()

    def test_returns_none_for_unknown_vehicle(self, app):
        with app.app_context():
            result = get_featured_video("UnknownBrand", "UnknownModel")
            assert result is None

    def test_case_insensitive_lookup(self, app):
        with app.app_context():
            vehicle = Vehicle(brand="Peugeot", model="208CI")
            _db.session.add(vehicle)
            _db.session.commit()

            video = YouTubeVideo(
                video_id="CASE_01",
                title="Essai 208CI",
                vehicle_id=vehicle.id,
                is_featured=True,
            )
            _db.session.add(video)
            _db.session.commit()

            result = get_featured_video("peugeot", "208CI")
            assert result is not None

            _db.session.delete(video)
            _db.session.delete(vehicle)
            _db.session.commit()
