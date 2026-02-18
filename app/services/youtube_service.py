"""Service d'extraction de sous-titres YouTube."""

import logging
import time
from datetime import datetime, timezone

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.extensions import db
from app.models.youtube import YouTubeTranscript, YouTubeVideo

logger = logging.getLogger(__name__)

# Delais entre requetes pour eviter le blocage IP
DELAY_BETWEEN_VIDEOS = 2.0  # secondes
DELAY_BETWEEN_MODELS = 5.0  # secondes


def search_videos(query: str, max_results: int = 5) -> list[dict]:
    """Recherche YouTube via yt-dlp.

    Retourne une liste de dicts : [{id, title, channel, duration}, ...].
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(
            f"ytsearch{max_results}:{query}",
            download=False,
        )

    videos = []
    for entry in result.get("entries", []):
        videos.append(
            {
                "id": entry["id"],
                "title": entry.get("title", ""),
                "channel": entry.get("channel", entry.get("uploader", "")),
                "duration": entry.get("duration"),
            }
        )
    return videos


def fetch_transcript(video_id: str) -> dict | None:
    """Extrait le transcript francais d'une video YouTube.

    Tente d'abord les sous-titres FR directs, puis la traduction vers FR.
    Retourne None si aucun sous-titre disponible.
    """
    ytt_api = YouTubeTranscriptApi()

    try:
        transcript = ytt_api.fetch(video_id, languages=["fr"])
        snippets = transcript.to_raw_data()
        full_text = " ".join(s["text"] for s in snippets)
        return {
            "language": transcript.language_code,
            "is_generated": transcript.is_generated,
            "full_text": full_text,
            "snippets": snippets,
            "snippet_count": len(snippets),
            "char_count": len(full_text),
        }
    except NoTranscriptFound:
        pass
    except TranscriptsDisabled:
        logger.info("Sous-titres desactives pour %s", video_id)
        return None
    except VideoUnavailable:
        logger.info("Video indisponible : %s", video_id)
        return None
    except RequestBlocked:
        logger.error("Requete bloquee par YouTube pour %s", video_id)
        raise

    # Fallback : traduction depuis une autre langue
    try:
        transcript_list = ytt_api.list(video_id)
        for t in transcript_list:
            if t.is_translatable:
                translated = t.translate("fr")
                fetched = translated.fetch()
                snippets = fetched.to_raw_data()
                full_text = " ".join(s["text"] for s in snippets)
                return {
                    "language": "fr (translated)",
                    "is_generated": True,
                    "full_text": full_text,
                    "snippets": snippets,
                    "snippet_count": len(snippets),
                    "char_count": len(full_text),
                }
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound):
        pass
    except RequestBlocked:
        raise

    return None


def store_video(
    video_data: dict, vehicle_id: int | None = None, search_query: str = ""
) -> YouTubeVideo:
    """Cree ou recupere un YouTubeVideo. Idempotent sur video_id."""
    existing = YouTubeVideo.query.filter_by(video_id=video_data["id"]).first()
    if existing:
        return existing

    video = YouTubeVideo(
        video_id=video_data["id"],
        title=video_data.get("title", ""),
        channel_name=video_data.get("channel", ""),
        duration_seconds=video_data.get("duration"),
        vehicle_id=vehicle_id,
        search_query=search_query,
    )
    db.session.add(video)
    db.session.commit()
    return video


def extract_and_store_transcript(video: YouTubeVideo) -> YouTubeTranscript:
    """Fetch et stocke le transcript pour une video.

    Met a jour le status du transcript (extracted / no_subtitles / error).
    """
    # Si un transcript existe deja avec status extracted, on le retourne
    if video.transcript and video.transcript.status == "extracted":
        return video.transcript

    # Creer ou recuperer le transcript record
    transcript_record = video.transcript
    if transcript_record is None:
        transcript_record = YouTubeTranscript(
            video_db_id=video.id,
            language="",
            full_text="",
            status="pending",
        )
        db.session.add(transcript_record)
        db.session.commit()

    try:
        result = fetch_transcript(video.video_id)
    except RequestBlocked:
        transcript_record.status = "error"
        transcript_record.error_message = "Requete bloquee par YouTube"
        db.session.commit()
        raise

    if result is None:
        transcript_record.status = "no_subtitles"
        transcript_record.error_message = "Aucun sous-titre francais disponible"
        db.session.commit()
        return transcript_record

    transcript_record.language = result["language"]
    transcript_record.is_generated = result["is_generated"]
    transcript_record.full_text = result["full_text"]
    transcript_record.snippets_json = result["snippets"]
    transcript_record.snippet_count = result["snippet_count"]
    transcript_record.char_count = result["char_count"]
    transcript_record.status = "extracted"
    transcript_record.error_message = None
    transcript_record.extracted_at = datetime.now(timezone.utc)
    db.session.commit()

    logger.info(
        "Transcript extrait pour %s (%d chars, %s)",
        video.video_id,
        result["char_count"],
        result["language"],
    )
    return transcript_record


def search_and_extract_for_vehicle(vehicle, max_videos: int = 5) -> dict:
    """Pipeline complet pour un vehicule : search → store → extract.

    Retourne {videos_found, transcripts_ok, transcripts_failed, transcripts_skipped}.
    """
    query = f"{vehicle.brand} {vehicle.model} essai test avis"
    stats = {
        "videos_found": 0,
        "transcripts_ok": 0,
        "transcripts_failed": 0,
        "transcripts_skipped": 0,
    }

    try:
        videos_data = search_videos(query, max_results=max_videos)
    except OSError as exc:
        logger.error("Recherche YouTube echouee pour %s %s: %s", vehicle.brand, vehicle.model, exc)
        return stats

    stats["videos_found"] = len(videos_data)

    for vdata in videos_data:
        video = store_video(vdata, vehicle_id=vehicle.id, search_query=query)

        # Skip si deja extrait
        if video.transcript and video.transcript.status == "extracted":
            stats["transcripts_skipped"] += 1
            continue

        try:
            transcript = extract_and_store_transcript(video)
            if transcript.status == "extracted":
                stats["transcripts_ok"] += 1
            else:
                stats["transcripts_failed"] += 1
        except RequestBlocked:
            stats["transcripts_failed"] += 1
            raise

        time.sleep(DELAY_BETWEEN_VIDEOS)

    return stats


def get_featured_video(make: str, model: str) -> dict | None:
    """Retourne la video featured pour un vehicule, ou None.

    Cherche par vehicle_id via la table Vehicle, fallback sur brand/model.
    """
    from app.models.vehicle import Vehicle

    vehicle = Vehicle.query.filter(
        Vehicle.brand.ilike(make),
        Vehicle.model.ilike(model),
    ).first()

    if not vehicle:
        return None

    video = YouTubeVideo.query.filter_by(
        vehicle_id=vehicle.id,
        is_featured=True,
        is_archived=False,
    ).first()

    if not video:
        return None

    return {
        "video_id": video.video_id,
        "title": video.title,
        "channel": video.channel_name,
        "url": f"https://www.youtube.com/watch?v={video.video_id}",
    }
