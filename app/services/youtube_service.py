"""Service d'extraction de sous-titres YouTube."""

import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    IpBlocked,
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


def build_search_query(
    make: str,
    model: str,
    year: int | None = None,
    fuel: str | None = None,
    hp: str | None = None,
    keywords: str | None = None,
) -> str:
    """Construit une query YouTube precise a partir des parametres vehicule.

    Exemples:
        ("Peugeot", "308", 2019, "diesel", "130", "fiabilite") ->
        "Peugeot 308 2019 diesel 130ch fiabilite"

        ("Renault", "Clio") -> "Renault Clio essai test avis"
    """
    parts = [make.strip(), model.strip()]

    if year:
        parts.append(str(year))
    if fuel:
        parts.append(fuel.strip())
    if hp:
        parts.append(f"{hp.strip()}ch")
    if keywords:
        parts.append(keywords.strip())

    if not keywords and not fuel and not hp and not year:
        parts.extend(["essai", "test", "avis"])

    return " ".join(parts)


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


def _parse_vtt_to_text(vtt_content: str) -> str:
    """Parse un fichier VTT et extrait le texte brut sans timestamps ni doublons."""
    lines = vtt_content.splitlines()
    seen: set[str] = set()
    text_parts: list[str] = []

    for line in lines:
        line = line.strip()
        # Skip header, empty lines, timestamps, NOTE/STYLE blocks
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:"):
            continue
        if line.startswith("Language:") or line.startswith("NOTE"):
            continue
        if "-->" in line:
            continue
        # Skip pure numeric cue identifiers
        if re.match(r"^\d+$", line):
            continue
        # Strip HTML-like tags (<c>, </c>, <b>, etc.)
        clean = re.sub(r"<[^>]+>", "", line)
        clean = clean.strip()
        if clean and clean not in seen:
            seen.add(clean)
            text_parts.append(clean)

    return " ".join(text_parts)


def _fetch_transcript_ytdlp(video_id: str) -> dict | None:
    """Extrait les sous-titres via yt-dlp (fallback quand youtube-transcript-api est bloque).

    Telecharge les fichiers VTT dans un dossier temporaire, parse le texte.
    Priorite : FR manual > FR auto > EN manual > EN auto.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["fr", "en"],
            "subtitlesformat": "vtt",
            "skip_download": True,
            "outtmpl": os.path.join(tmpdir, "%(id)s"),
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            # 429 ou autre erreur partielle — des VTT ont pu etre ecrits avant l'echec
            logger.warning("yt-dlp subtitle download error for %s: %s", video_id, exc)

        # Chercher les fichiers VTT generes (priorite FR > EN)
        vtt_files = sorted(Path(tmpdir).glob("*.vtt"))
        if not vtt_files:
            logger.info("yt-dlp: aucun sous-titre trouve pour %s", video_id)
            return None

        # Trier par priorite: fr > en, manual > auto
        best_file = None
        best_lang = ""
        is_generated = True
        for vtt_path in vtt_files:
            name = vtt_path.name.lower()
            if ".fr." in name and best_lang != "fr":
                best_file = vtt_path
                best_lang = "fr"
                is_generated = "auto" in name or best_lang != "fr"
            elif ".en." in name and not best_lang:
                best_file = vtt_path
                best_lang = "en"
                is_generated = True

        if best_file is None:
            best_file = vtt_files[0]
            best_lang = "unknown"

        vtt_content = best_file.read_text(encoding="utf-8")
        full_text = _parse_vtt_to_text(vtt_content)

        if not full_text or len(full_text) < 50:
            logger.info(
                "yt-dlp: transcript trop court pour %s (%d chars)", video_id, len(full_text)
            )
            return None

        logger.info(
            "yt-dlp: transcript extrait pour %s (%d chars, lang=%s)",
            video_id,
            len(full_text),
            best_lang,
        )
        return {
            "language": f"{best_lang} (yt-dlp)",
            "is_generated": is_generated,
            "full_text": full_text,
            "snippets": [],
            "snippet_count": 0,
            "char_count": len(full_text),
        }


def _make_transcript_result(transcript, language_override: str | None = None) -> dict:
    """Construit le dict resultat a partir d'un transcript fetch."""
    snippets = transcript.to_raw_data()
    full_text = " ".join(s["text"] for s in snippets)
    return {
        "language": language_override or transcript.language_code,
        "is_generated": transcript.is_generated,
        "full_text": full_text,
        "snippets": snippets,
        "snippet_count": len(snippets),
        "char_count": len(full_text),
    }


def fetch_transcript(video_id: str) -> dict | None:
    """Extrait le transcript d'une video YouTube.

    Strategie (du plus fiable au moins fiable) :
    1. Sous-titres FR directs (youtube-transcript-api)
    2. Sous-titres EN directs (youtube-transcript-api)
    3. Traduction vers FR (youtube-transcript-api)
    4. Fallback yt-dlp (telecharge VTT, resilient chemin different)
    Retourne None si aucun sous-titre disponible.
    """
    ytt_api = YouTubeTranscriptApi()

    # 1. Essai FR direct
    try:
        transcript = ytt_api.fetch(video_id, languages=["fr"])
        return _make_transcript_result(transcript)
    except NoTranscriptFound:
        pass
    except TranscriptsDisabled:
        logger.info("Sous-titres desactives pour %s", video_id)
        return None
    except VideoUnavailable:
        logger.info("Video indisponible : %s", video_id)
        return None
    except (RequestBlocked, IpBlocked):
        logger.warning("youtube-transcript-api bloque pour %s, fallback yt-dlp...", video_id)
        return _fetch_transcript_ytdlp(video_id)

    # 2. Essai EN direct (beaucoup de videos auto ont des sous-titres EN)
    try:
        transcript = ytt_api.fetch(video_id, languages=["en"])
        return _make_transcript_result(transcript)
    except NoTranscriptFound:
        pass
    except (RequestBlocked, IpBlocked):
        logger.warning("youtube-transcript-api bloque (EN) pour %s, fallback yt-dlp...", video_id)
        return _fetch_transcript_ytdlp(video_id)

    # 3. Fallback : traduction depuis une autre langue vers FR
    try:
        transcript_list = ytt_api.list(video_id)
        for t in transcript_list:
            if t.is_translatable:
                translated = t.translate("fr")
                fetched = translated.fetch()
                return _make_transcript_result(fetched, language_override="fr (translated)")
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound):
        pass
    except (RequestBlocked, IpBlocked):
        logger.warning(
            "youtube-transcript-api bloque (translate) pour %s, fallback yt-dlp...", video_id
        )
        return _fetch_transcript_ytdlp(video_id)

    # 4. Dernier recours : yt-dlp directement
    return _fetch_transcript_ytdlp(video_id)


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

    result = fetch_transcript(video.video_id)

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

        transcript = extract_and_store_transcript(video)
        if transcript.status == "extracted":
            stats["transcripts_ok"] += 1
        else:
            stats["transcripts_failed"] += 1

        time.sleep(DELAY_BETWEEN_VIDEOS)

    return stats


def search_and_extract_custom(
    query: str,
    vehicle_id: int | None,
    max_results: int = 10,
) -> dict:
    """Pipeline de recherche avec query custom : search -> store -> extract.

    Retourne {videos_found, transcripts_ok, transcripts_failed, transcripts_skipped, video_ids}.
    """
    stats = {
        "videos_found": 0,
        "transcripts_ok": 0,
        "transcripts_failed": 0,
        "transcripts_skipped": 0,
        "video_ids": [],
    }

    try:
        videos_data = search_videos(query, max_results=max_results)
    except OSError as exc:
        logger.error("YouTube search failed for query '%s': %s", query, exc)
        return stats

    stats["videos_found"] = len(videos_data)

    for vdata in videos_data:
        video = store_video(vdata, vehicle_id=vehicle_id, search_query=query)
        stats["video_ids"].append(video.id)

        if video.transcript and video.transcript.status == "extracted":
            stats["transcripts_skipped"] += 1
            continue

        transcript = extract_and_store_transcript(video)
        if transcript.status == "extracted":
            stats["transcripts_ok"] += 1
        else:
            stats["transcripts_failed"] += 1

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
