#!/usr/bin/env python3
"""Seed YouTube -- recherche de videos de tests et extraction des sous-titres.

Script idempotent : ne re-telecharge pas les transcripts deja extraits.
Usage : python data/seeds/seed_youtube.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402
from app.models.youtube import YouTubeTranscript, YouTubeVideo  # noqa: E402
from app.services.pipeline_tracker import track_pipeline  # noqa: E402
from app.services.youtube_service import (  # noqa: E402
    DELAY_BETWEEN_MODELS,
    search_and_extract_for_vehicle,
)


def seed_youtube():
    """Recherche et extrait les sous-titres YouTube pour tous les vehicules."""
    vehicles = Vehicle.query.order_by(Vehicle.brand, Vehicle.model).all()
    total = len(vehicles)

    if total == 0:
        print("[!] Aucun vehicule en base -- lancez seed_vehicles.py d'abord")
        return 0

    print(f"[*] Extraction YouTube pour {total} vehicules")

    total_ok = 0
    total_failed = 0
    total_skipped = 0

    with track_pipeline("youtube_transcripts") as tracker:
        for i, vehicle in enumerate(vehicles, 1):
            label = f"{vehicle.brand} {vehicle.model}"

            # Compter les videos deja extraites pour ce vehicule
            existing = (
                YouTubeVideo.query.filter_by(vehicle_id=vehicle.id)
                .join(YouTubeVideo.transcript)
                .filter(
                    db.or_(
                        YouTubeTranscript.status == "extracted",
                        YouTubeTranscript.status == "no_subtitles",
                    )
                )
                .count()
            )
            if existing >= 5:
                print(f"  [skip] [{i}/{total}] {label} : {existing} videos deja traitees")
                total_skipped += existing
                continue

            try:
                stats = search_and_extract_for_vehicle(vehicle, max_videos=5)
            except Exception as exc:
                print(f"  [ERR]  [{i}/{total}] {label} : {exc}")
                total_failed += 1
                continue

            ok = stats["transcripts_ok"]
            failed = stats["transcripts_failed"]
            skipped = stats["transcripts_skipped"]
            found = stats["videos_found"]
            total_ok += ok + skipped
            total_failed += failed
            total_skipped += skipped

            print(
                f"  [{'+' if ok else '-'}]    [{i}/{total}] {label} : "
                f"{ok}/{found} transcripts OK"
                f"{f', {skipped} deja en base' if skipped else ''}"
                f"{f', {failed} echecs' if failed else ''}"
            )

            if i < total:
                time.sleep(DELAY_BETWEEN_MODELS)

        tracker.count = total_ok

    print(f"\n[*] Termine : {total_ok} transcripts OK, {total_failed} echecs, {total_skipped} skip")
    return total_ok


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        seed_youtube()
