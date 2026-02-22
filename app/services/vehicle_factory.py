"""Factory d'auto-creation de vehicules depuis les donnees LBC.

Utilise les scans (ScanLog) et les prix marche (MarketPrice) pour creer
automatiquement les vehicules qui ne sont pas encore dans le referentiel.
Evite les "coquilles vides" : un vehicule n'est cree que s'il a des donnees.
"""

import logging

from sqlalchemy import func

from app.extensions import db
from app.models.market_price import MarketPrice
from app.models.scan import ScanLog
from app.models.vehicle import Vehicle
from app.services.csv_enrichment import lookup_specs
from app.services.market_service import market_text_key, market_text_key_expr
from app.services.vehicle_lookup import find_vehicle, is_generic_model

logger = logging.getLogger(__name__)

# Seuils d'auto-creation
MIN_SCANS_WITH_CSV = 1  # 1 scan suffit si le CSV confirme le vehicule
MIN_SCANS_WITHOUT_CSV = 3  # 3 scans si pas de CSV (confirmation par repetition)
MIN_MARKET_SAMPLES = 20  # Nombre minimum d'annonces marche collectees


def can_auto_create(make: str, model: str) -> dict:
    """Evalue si un vehicule a assez de donnees pour etre cree automatiquement.

    Args:
        make: Marque du vehicule (ex. "DS").
        model: Modele (ex. "DS 3").

    Returns:
        Dict avec les champs:
        - eligible (bool): True si le vehicule peut etre cree
        - reason (str): Raison du refus ou validation
        - scan_count (int): Nombre de scans trouves
        - market_samples (int): Nombre d'annonces marche
        - csv_available (bool): Specs CSV disponibles
    """
    result = {
        "eligible": False,
        "reason": "",
        "scan_count": 0,
        "market_samples": 0,
        "csv_available": False,
    }

    # 1. Pas un modele generique
    if is_generic_model(model):
        result["reason"] = "Modele generique"
        return result

    # 2. Pas deja dans le referentiel
    if find_vehicle(make, model):
        result["reason"] = "Deja dans le referentiel"
        return result

    # 3. Verifier CSV en avance pour adapter le seuil de scans
    csv_available = bool(lookup_specs(make, model))
    result["csv_available"] = csv_available

    # 4. Compter les scans (seuil adaptatif selon CSV)
    scan_count = (
        db.session.query(func.count(ScanLog.id))
        .filter(
            func.lower(ScanLog.vehicle_make) == make.strip().lower(),
            func.lower(ScanLog.vehicle_model) == model.strip().lower(),
        )
        .scalar()
        or 0
    )
    result["scan_count"] = scan_count
    min_scans = MIN_SCANS_WITH_CSV if csv_available else MIN_SCANS_WITHOUT_CSV

    if scan_count < min_scans:
        result["reason"] = f"Pas assez de scans ({scan_count}/{min_scans})"
        return result

    # 5. Verifier les sources de donnees
    market_records = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
    ).all()
    market_samples = sum(r.sample_count for r in market_records) if market_records else 0
    result["market_samples"] = market_samples

    if not csv_available and market_samples < MIN_MARKET_SAMPLES:
        result["reason"] = (
            f"Donnees insuffisantes (CSV={csv_available}, marche={market_samples}/{MIN_MARKET_SAMPLES})"
        )
        return result

    result["eligible"] = True
    sources = []
    if csv_available:
        sources.append("CSV")
    if market_samples >= MIN_MARKET_SAMPLES:
        sources.append(f"marche ({market_samples} annonces)")
    result["reason"] = f"Eligible ({', '.join(sources)})"
    return result


def auto_create_vehicle(make: str, model: str) -> Vehicle | None:
    """Cree automatiquement un vehicule si les conditions sont remplies.

    Verifie l'eligibilite, cree le Vehicle, enrichit depuis le CSV si possible,
    et determine les annees depuis les donnees marche + scans.

    Args:
        make: Marque du vehicule.
        model: Modele du vehicule.

    Returns:
        Le Vehicle cree, ou None si les conditions ne sont pas remplies.
    """
    check = can_auto_create(make, model)
    if not check["eligible"]:
        logger.info(
            "Auto-create rejected %s %s: %s",
            make,
            model,
            check["reason"],
        )
        return None

    # Normalisation canonique (memes fonctions que l'extraction et quick-add)
    from app.services.vehicle_lookup import (
        display_brand,
        display_model,
        normalize_brand,
        normalize_model,
    )

    brand_clean = display_brand(make)
    model_clean = display_model(model)

    # Dedup check (race condition) -- via normalisation canonique
    existing = Vehicle.query.filter(
        func.lower(Vehicle.brand) == normalize_brand(make),
        func.lower(Vehicle.model) == normalize_model(model),
    ).first()
    if existing:
        logger.info("Auto-create skipped (dedup): %s %s already exists", brand_clean, model_clean)
        return existing

    # Determiner year_start/year_end depuis MarketPrice + ScanLog
    market_records = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
    ).all()
    market_years = [r.year for r in market_records if r.year]

    year_start = min(market_years) if market_years else None
    year_end = max(market_years) if market_years else None

    # Creer le vehicule
    vehicle = Vehicle(
        brand=brand_clean,
        model=model_clean,
        year_start=year_start,
        year_end=year_end,
        enrichment_status="partial",
    )
    db.session.add(vehicle)
    db.session.flush()  # Obtenir l'ID pour les specs

    # Enrichir depuis le CSV si disponible
    specs_created = 0
    csv_specs = lookup_specs(make, model)
    if csv_specs:
        from app.models.vehicle import VehicleSpec

        years_from = [s["year_from"] for s in csv_specs if s.get("year_from")]
        years_to = [s["year_to"] for s in csv_specs if s.get("year_to")]

        for spec_data in csv_specs:
            spec_data.pop("generation", None)
            spec_data.pop("year_from", None)
            spec_data.pop("year_to", None)
            db.session.add(VehicleSpec(vehicle_id=vehicle.id, **spec_data))
            specs_created += 1

        if years_from:
            vehicle.year_start = min(years_from)
        if years_to:
            vehicle.year_end = max(years_to)

    db.session.commit()

    sources = []
    if specs_created:
        sources.append(f"CSV ({specs_created} fiches)")
    if check["market_samples"] >= MIN_MARKET_SAMPLES:
        sources.append(f"marche ({check['market_samples']} annonces)")
    logger.info(
        "Auto-created %s %s (id=%d, years=%s-%s, sources=%s)",
        brand_clean,
        model_clean,
        vehicle.id,
        vehicle.year_start,
        vehicle.year_end,
        " + ".join(sources),
    )
    return vehicle
