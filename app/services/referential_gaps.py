"""Agregation metier du referentiel vehicule pour l'admin et futurs services API.

Ce module construit une vue synthetique du referentiel : pour chaque vehicule,
on sait s'il a des specs, des pneus, des prix marche, des scans, etc.
Ca permet a l'admin d'identifier les "trous" dans la couverture et de prioriser
les enrichissements.

Deux niveaux de detail :
- build_referential_compact_profiles : profils legers pour la liste admin (1 query/source)
- build_vehicle_business_snapshot : fiche detaillee pour un vehicule (toutes les jointures)
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_

from app.extensions import db
from app.models.argus import ArgusPrice
from app.models.collection_job_as24 import CollectionJobAS24
from app.models.collection_job_lacentrale import CollectionJobLacentrale
from app.models.market_price import MarketPrice
from app.models.scan import ScanLog
from app.models.tire_size import TireSize
from app.models.vehicle import Vehicle, VehicleSpec
from app.models.vehicle_synthesis import VehicleSynthesis
from app.models.youtube import YouTubeTranscript, YouTubeVideo
from app.services.market_service import get_min_sample_count, market_text_key, market_text_key_expr

# Fenetres temporelles pour les stats de scans dans le snapshot vehicule
_LOOKBACK_DAY = timedelta(days=1)
_LOOKBACK_WEEK = timedelta(days=7)
_LOOKBACK_MONTH = timedelta(days=30)


def vehicle_pair_key(brand: str | None, model: str | None) -> tuple[str, str]:
    """Retourne une cle stable make/model pour joindre les sources metier.

    On normalise via market_text_key pour que "Mercedes-Benz" et "mercedes benz"
    produisent la meme cle. Indispensable car chaque source (LBC, AS24, CSV)
    ecrit les noms differemment.
    """
    return market_text_key(brand or ""), market_text_key(model or "")


def _matching_pair_filters(
    model_cls, make_column: str, model_column: str, vehicle: Vehicle
) -> list:
    """Construit des filtres SQLAlchemy robustes make/model pour un véhicule."""
    make_attr = getattr(model_cls, make_column)
    model_attr = getattr(model_cls, model_column)
    return [
        market_text_key_expr(make_attr) == market_text_key(vehicle.brand),
        market_text_key_expr(model_attr) == market_text_key(vehicle.model),
    ]


def _compact_status(gap_count: int, has_market: bool, has_scans: bool) -> str:
    """Convertit un nombre de gaps en niveau lisible pour l'admin.

    3 niveaux : critical (rouge), attention (jaune), healthy (vert).
    Un vehicule sans aucun prix marche ni scan est directement critical.
    """
    if gap_count >= 5 or (not has_market and not has_scans):
        return "critical"
    if gap_count >= 2:
        return "attention"
    return "healthy"


def build_referential_compact_profiles(vehicles: list[Vehicle]) -> dict[int, dict]:
    """Construit des profils compacts pour toute la base, en lecture rapide.

    Strategie : on charge en batch les IDs/paires de chaque source (1 query par source)
    puis on itere sur les vehicules pour calculer leur profil. O(n_vehicules) en memoire
    mais O(n_sources) en queries, bien mieux que de faire une query par vehicule.
    """
    spec_vehicle_ids = {vid for (vid,) in db.session.query(VehicleSpec.vehicle_id).distinct().all()}
    argus_vehicle_ids = {vid for (vid,) in db.session.query(ArgusPrice.vehicle_id).distinct().all()}
    transcript_vehicle_ids = {
        vid
        for (vid,) in (
            db.session.query(YouTubeVideo.vehicle_id)
            .join(YouTubeVideo.transcript)
            .filter(
                YouTubeVideo.vehicle_id.isnot(None),
                YouTubeTranscript.status == "extracted",
            )
            .distinct()
            .all()
        )
    }
    synthesis_vehicle_ids = {
        vid
        for (vid,) in db.session.query(VehicleSynthesis.vehicle_id)
        .filter(VehicleSynthesis.vehicle_id.isnot(None))
        .distinct()
        .all()
    }

    tire_pairs = {
        vehicle_pair_key(make, model)
        for make, model in db.session.query(TireSize.make, TireSize.model).distinct().all()
    }
    market_pairs = {
        vehicle_pair_key(make, model)
        for make, model in db.session.query(MarketPrice.make, MarketPrice.model).distinct().all()
    }
    market_lbc_pairs = {
        vehicle_pair_key(make, model)
        for make, model in (
            db.session.query(MarketPrice.make, MarketPrice.model)
            .filter(
                MarketPrice.lbc_estimate_low.isnot(None),
                MarketPrice.lbc_estimate_high.isnot(None),
            )
            .distinct()
            .all()
        )
    }
    market_non_fr_pairs = {
        vehicle_pair_key(make, model)
        for make, model in (
            db.session.query(MarketPrice.make, MarketPrice.model)
            .filter(func.coalesce(MarketPrice.country, "FR") != "FR")
            .distinct()
            .all()
        )
    }
    scan_pairs = {
        vehicle_pair_key(make, model)
        for make, model in (
            db.session.query(ScanLog.vehicle_make, ScanLog.vehicle_model)
            .filter(ScanLog.vehicle_make.isnot(None), ScanLog.vehicle_model.isnot(None))
            .distinct()
            .all()
        )
    }
    as24_job_pairs = {
        vehicle_pair_key(make, model)
        for make, model in db.session.query(CollectionJobAS24.make, CollectionJobAS24.model)
        .distinct()
        .all()
    }
    lc_job_pairs = {
        vehicle_pair_key(make, model)
        for make, model in db.session.query(
            CollectionJobLacentrale.make, CollectionJobLacentrale.model
        )
        .distinct()
        .all()
    }

    # Pour chaque vehicule, on calcule son profil en O(1) grace aux sets precharges
    profiles: dict[int, dict] = {}
    for vehicle in vehicles:
        pair = vehicle_pair_key(vehicle.brand, vehicle.model)
        has_specs = vehicle.id in spec_vehicle_ids
        has_tires = pair in tire_pairs
        has_market = pair in market_pairs
        has_seed_argus = vehicle.id in argus_vehicle_ids
        has_youtube = vehicle.id in transcript_vehicle_ids or vehicle.id in synthesis_vehicle_ids
        has_scans = pair in scan_pairs
        has_lbc_signal = pair in market_lbc_pairs
        has_as24_signal = pair in market_non_fr_pairs or pair in as24_job_pairs
        has_lc_signal = has_seed_argus or pair in lc_job_pairs
        has_lbc_tokens = bool(vehicle.site_brand_token and vehicle.site_model_token)
        has_as24_tokens = bool(vehicle.as24_slug_make and vehicle.as24_slug_model)

        # Le readiness score est base sur 8 criteres binaires.
        # Chaque critere manquant est un "gap" qui fait baisser le pourcentage.
        gap_count = sum(
            int(not flag)
            for flag in [
                has_specs,
                has_tires,
                has_market,
                has_lbc_signal,
                has_youtube,
                has_scans,
                has_lbc_tokens,
                has_as24_tokens,
            ]
        )
        readiness_pct = round(100 * (8 - gap_count) / 8)

        profiles[vehicle.id] = {
            "has_specs": has_specs,
            "has_tires": has_tires,
            "has_market": has_market,
            "has_seed_argus": has_seed_argus,
            "has_youtube": has_youtube,
            "has_scans": has_scans,
            "has_lbc_signal": has_lbc_signal,
            "has_as24_signal": has_as24_signal,
            "has_lc_signal": has_lc_signal,
            "has_lbc_tokens": has_lbc_tokens,
            "has_as24_tokens": has_as24_tokens,
            "gap_count": gap_count,
            "readiness_pct": readiness_pct,
            "status": _compact_status(gap_count, has_market=has_market, has_scans=has_scans),
        }

    return profiles


def build_referential_summary(vehicles: list[Vehicle], profiles: dict[int, dict]) -> dict:
    """Synthese globale de la base pour la page admin.

    Agregation des profils individuels : combien de vehicules ont des specs,
    des pneus, etc. Plus la moyenne de readiness pour jauger la sante globale.
    """
    total = len(vehicles)
    status_counter = Counter(profile["status"] for profile in profiles.values())

    def _count(flag: str) -> int:
        return sum(1 for profile in profiles.values() if profile[flag])

    return {
        "total_vehicles": total,
        "with_specs": _count("has_specs"),
        "with_tires": _count("has_tires"),
        "with_market": _count("has_market"),
        "with_youtube": _count("has_youtube"),
        "with_scans": _count("has_scans"),
        "with_lbc_tokens": _count("has_lbc_tokens"),
        "with_as24_tokens": _count("has_as24_tokens"),
        "critical_count": status_counter.get("critical", 0),
        "attention_count": status_counter.get("attention", 0),
        "healthy_count": status_counter.get("healthy", 0),
        "avg_readiness_pct": round(
            sum(profile["readiness_pct"] for profile in profiles.values()) / total,
        )
        if total
        else 0,
    }


def _job_status_counts(model_cls, vehicle: Vehicle) -> dict[str, int]:
    """Compte les jobs de collecte par status pour un vehicule donne."""
    rows = (
        db.session.query(model_cls.status, func.count(model_cls.id))
        .filter(*_matching_pair_filters(model_cls, "make", "model", vehicle))
        .group_by(model_cls.status)
        .all()
    )
    counts = {"pending": 0, "assigned": 0, "done": 0, "failed": 0}
    for status, count in rows:
        counts[status] = count
    counts["total"] = sum(counts.values())
    return counts


def build_vehicle_business_snapshot(vehicle: Vehicle, now: datetime | None = None) -> dict:
    """Construit la fiche metier detaillee d'un vehicule.

    C'est la vue complete utilisee par la page admin vehicule :
    specs, pneus, prix marche, argus seeds, YouTube, scans, jobs de collecte.
    Tout est charge en memoire pour eviter les N+1 queries dans le template.

    Le dict retourne contient aussi les "gaps" (donnees manquantes) et
    un status readiness pour l'admin.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)

    spec_rows = (
        VehicleSpec.query.filter_by(vehicle_id=vehicle.id)
        .order_by(
            VehicleSpec.fuel_type.asc().nullslast(),
            VehicleSpec.power_hp.asc().nullslast(),
            VehicleSpec.engine.asc().nullslast(),
        )
        .all()
    )
    tire_rows = (
        TireSize.query.filter(*_matching_pair_filters(TireSize, "make", "model", vehicle))
        .order_by(TireSize.collected_at.desc())
        .all()
    )
    market_rows = (
        MarketPrice.query.filter(*_matching_pair_filters(MarketPrice, "make", "model", vehicle))
        .order_by(
            func.coalesce(MarketPrice.country, "FR").asc(),
            MarketPrice.region.asc(),
            MarketPrice.year.desc(),
            MarketPrice.collected_at.desc(),
        )
        .all()
    )
    seed_rows = (
        ArgusPrice.query.filter_by(vehicle_id=vehicle.id)
        .order_by(
            ArgusPrice.region.asc(),
            ArgusPrice.year.desc(),
        )
        .all()
    )
    video_rows = (
        YouTubeVideo.query.filter_by(vehicle_id=vehicle.id)
        .order_by(YouTubeVideo.created_at.desc())
        .all()
    )
    synthesis_rows = (
        VehicleSynthesis.query.filter(
            or_(
                VehicleSynthesis.vehicle_id == vehicle.id,
                and_(
                    VehicleSynthesis.vehicle_id.is_(None),
                    func.lower(VehicleSynthesis.make) == vehicle.brand.lower(),
                    func.lower(VehicleSynthesis.model) == vehicle.model.lower(),
                ),
            )
        )
        .order_by(VehicleSynthesis.created_at.desc())
        .all()
    )
    scan_rows = (
        ScanLog.query.filter(
            *(_matching_pair_filters(ScanLog, "vehicle_make", "vehicle_model", vehicle))
        )
        .order_by(ScanLog.created_at.desc())
        .all()
    )

    fuel_values = sorted({row.fuel_type for row in spec_rows if row.fuel_type})
    transmission_values = sorted({row.transmission for row in spec_rows if row.transmission})
    max_hp = max((row.power_hp for row in spec_rows if row.power_hp is not None), default=None)
    reliability_values = [
        row.reliability_rating for row in spec_rows if row.reliability_rating is not None
    ]
    avg_reliability = (
        round(sum(reliability_values) / len(reliability_values), 1) if reliability_values else None
    )

    tire_dimensions: list[str] = []
    tire_sources: set[str] = set()
    for row in tire_rows:
        tire_sources.add(row.source)
        for dim in row.get_dimensions_list():
            size = (dim or {}).get("size")
            if size and size not in tire_dimensions:
                tire_dimensions.append(size)
    tire_dimensions_preview = tire_dimensions[:8]

    market_regions = sorted({f"{(row.country or 'FR')} · {row.region}" for row in market_rows})
    market_countries = sorted({row.country or "FR" for row in market_rows})
    total_market_samples = sum(row.sample_count or 0 for row in market_rows)
    fresh_market_count = sum(
        1 for row in market_rows if row.refresh_after and row.refresh_after > now
    )
    lbc_estimate_count = sum(
        1
        for row in market_rows
        if row.lbc_estimate_low is not None and row.lbc_estimate_high is not None
    )
    non_fr_market_count = sum(1 for row in market_rows if (row.country or "FR") != "FR")
    insufficient_market_count = 0
    for row in market_rows:
        row._min_required = get_min_sample_count(vehicle.brand, vehicle.model, row.country or "FR")
        row._is_fresh = bool(row.refresh_after and row.refresh_after > now)
        row._has_lbc_estimate = bool(
            row.lbc_estimate_low is not None and row.lbc_estimate_high is not None
        )
        row._sample_gap = max((row._min_required or 0) - (row.sample_count or 0), 0)
        if (row.sample_count or 0) < row._min_required:
            insufficient_market_count += 1

    transcript_count = sum(
        1 for row in video_rows if row.transcript and row.transcript.status == "extracted"
    )
    total_transcript_chars = sum(
        (row.transcript.char_count or 0)
        for row in video_rows
        if row.transcript and row.transcript.status == "extracted"
    )

    by_source_counter = Counter((row.source or "unknown") for row in scan_rows)
    ordered_sources = ["leboncoin", "autoscout24", "lacentrale"]
    scan_sources = [
        {"source": source, "count": by_source_counter.get(source, 0)} for source in ordered_sources
    ]
    for source, count in by_source_counter.items():
        if source not in ordered_sources:
            scan_sources.append({"source": source, "count": count})

    day_cutoff = now - _LOOKBACK_DAY
    week_cutoff = now - _LOOKBACK_WEEK
    month_cutoff = now - _LOOKBACK_MONTH
    scans_day = sum(1 for row in scan_rows if row.created_at and row.created_at >= day_cutoff)
    scans_week = sum(1 for row in scan_rows if row.created_at and row.created_at >= week_cutoff)
    scans_month = sum(1 for row in scan_rows if row.created_at and row.created_at >= month_cutoff)

    as24_jobs = _job_status_counts(CollectionJobAS24, vehicle)
    lc_jobs = _job_status_counts(CollectionJobLacentrale, vehicle)

    # Identification des lacunes : chaque gap est un texte explicite
    # affiche dans la page admin comme un warning
    gap_items: list[str] = []
    if not spec_rows:
        gap_items.append("Specs techniques absentes")
    if not tire_rows:
        gap_items.append("Dimensions pneus absentes")
    if not market_rows:
        gap_items.append("Argus maison absent")
    elif insufficient_market_count == len(market_rows):
        gap_items.append("Argus maison trop fragile")
    if not seed_rows:
        gap_items.append("Aucune cote seed / locale")
    if lbc_estimate_count == 0:
        gap_items.append("Aucune estimation LBC en base")
    if non_fr_market_count == 0:
        gap_items.append("Aucune couverture AS24 hors FR")
    if transcript_count == 0 and not synthesis_rows:
        gap_items.append("Aucune matière YouTube / fiabilité")
    if not scan_rows:
        gap_items.append("Aucun scan historique")
    if not (vehicle.site_brand_token and vehicle.site_model_token):
        gap_items.append("Tokens LBC manquants")
    if not (vehicle.as24_slug_make and vehicle.as24_slug_model):
        gap_items.append("Slugs AS24 manquants")

    status = _compact_status(
        len(gap_items), has_market=bool(market_rows), has_scans=bool(scan_rows)
    )
    readiness_pct = round(100 * (10 - len(gap_items)) / 10)

    latest_synthesis = synthesis_rows[0] if synthesis_rows else None

    return {
        "vehicle": vehicle,
        "status": status,
        "readiness_pct": readiness_pct,
        "gap_count": len(gap_items),
        "gap_items": gap_items,
        "specs": {
            "count": len(spec_rows),
            "rows": spec_rows[:12],
            "fuel_values": fuel_values,
            "transmission_values": transmission_values,
            "max_hp": max_hp,
            "avg_reliability": avg_reliability,
            "known_issues_count": sum(1 for row in spec_rows if row.known_issues),
        },
        "tires": {
            "count": len(tire_rows),
            "rows": tire_rows[:10],
            "source_values": sorted(tire_sources),
            "dimension_count": len(tire_dimensions),
            "dimensions_preview": tire_dimensions_preview,
            "has_data": bool(tire_rows),
        },
        "market": {
            "count": len(market_rows),
            "rows": market_rows[:20],
            "total_samples": total_market_samples,
            "fresh_count": fresh_market_count,
            "countries": market_countries,
            "regions": market_regions,
            "lbc_estimate_count": lbc_estimate_count,
            "non_fr_count": non_fr_market_count,
            "insufficient_count": insufficient_market_count,
            "has_data": bool(market_rows),
        },
        "seed_argus": {
            "count": len(seed_rows),
            "rows": seed_rows[:20],
            "has_data": bool(seed_rows),
        },
        "youtube": {
            "video_count": len(video_rows),
            "transcript_count": transcript_count,
            "transcript_chars": total_transcript_chars,
            "synthesis_count": len(synthesis_rows),
            "videos": video_rows[:10],
            "syntheses": synthesis_rows[:10],
            "latest_synthesis": latest_synthesis,
            "has_data": bool(transcript_count or synthesis_rows),
        },
        "scans": {
            "total": len(scan_rows),
            "day": scans_day,
            "week": scans_week,
            "month": scans_month,
            "rows": scan_rows[:20],
            "by_source": scan_sources,
            "last_seen": scan_rows[0].created_at if scan_rows else None,
            "has_data": bool(scan_rows),
        },
        "tokens": {
            "lbc_ready": bool(vehicle.site_brand_token and vehicle.site_model_token),
            "as24_ready": bool(vehicle.as24_slug_make and vehicle.as24_slug_model),
            "site_brand_token": vehicle.site_brand_token,
            "site_model_token": vehicle.site_model_token,
            "as24_slug_make": vehicle.as24_slug_make,
            "as24_slug_model": vehicle.as24_slug_model,
        },
        "jobs": {
            "as24": as24_jobs,
            "lacentrale": lc_jobs,
        },
    }
