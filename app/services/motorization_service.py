"""Service de motorisations observees -- tracking + promotion automatique en VehicleSpec.

Chaque annonce (collecte marche ou scan individuel) contribue des specs observees.
Quand une combinaison (fuel + transmission + puissance) est vue sur N annonces
distinctes, elle est promue en VehicleSpec confirmee.

L'interet : on enrichit le referentiel automatiquement a partir des donnees terrain.
Pas besoin de saisir manuellement les motorisations, les annonces font le travail.
Le seuil de 3 sources distinctes evite de creer des specs a partir d'une seule
annonce potentiellement erronnee.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db

logger = logging.getLogger(__name__)

# Nombre minimum de sources distinctes pour promouvoir une motorisation en VehicleSpec.
# 3 = bonne balance entre reactivite et fiabilite (evite les faux positifs
# d'une annonce isolee avec des donnees erronees).
PROMOTION_THRESHOLD = 3


# --- Normalisation ---
# Tables de mapping pour harmoniser les valeurs brutes des annonces (lowercase, accents varies)
# vers des formes propres pour VehicleSpec.

FUEL_DISPLAY = {
    "essence": "Essence",
    "diesel": "Diesel",
    "hybride": "Hybride",
    "hybride rechargeable": "Hybride rechargeable",
    "electrique": "Electrique",
    "électrique": "Electrique",
    "gpl": "GPL",
    "gnv": "GNV",
}

TRANSMISSION_DISPLAY = {
    "manuelle": "Manuelle",
    "automatique": "Automatique",
    "manual": "Manuelle",
    "automatic": "Automatique",
}


def capitalize_fuel(fuel: str) -> str:
    """Normalise le type de carburant pour VehicleSpec (title case).

    Passe par la table de mapping pour les cas connus, sinon .title() en fallback.
    """
    return FUEL_DISPLAY.get(fuel.strip().lower(), fuel.strip().title())


def capitalize_transmission(trans: str) -> str:
    """Normalise la transmission pour VehicleSpec.

    Gere les variantes anglais/francais (manual/manuelle, automatic/automatique).
    """
    return TRANSMISSION_DISPLAY.get(trans.strip().lower(), trans.strip().title())


def build_engine_name(fuel: str, transmission: str, hp: int) -> str:
    """Construit un nom lisible de motorisation.

    Ce nom est stocke dans VehicleSpec.engine pour l'affichage
    dans l'extension et le rapport PDF.

    Ex: "Diesel 130ch Automatique", "Essence 110ch Manuelle".
    """
    return f"{capitalize_fuel(fuel)} {hp}ch {capitalize_transmission(transmission)}"


# --- Deduplication ---


def _ad_hash(detail: dict) -> str:
    """Hash stable d'un detail d'annonce pour deduplication.

    Utilise price+year+km comme empreinte unique d'une annonce.
    Deux collectes de la meme annonce produiront le meme hash,
    ce qui evite de gonfler artificiellement le compteur distinct_sources.
    """
    key = f"{detail.get('price', 0)}:{detail.get('year', 0)}:{detail.get('km', 0)}"
    return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest()[:12]


# --- Enrichissement ---


def enrich_observed_motorizations(
    vehicle_id: int,
    details: list[dict],
) -> list[int]:
    """Enrichit les motorisations observees depuis des details d'annonces.

    C'est le coeur du systeme d'auto-enrichissement. Pour chaque annonce
    contenant fuel + gearbox + horse_power, on cree ou met a jour un
    ObservedMotorization. Si le nombre de sources distinctes atteint le
    seuil, on "promeut" la motorisation en VehicleSpec officielle.

    Args:
        vehicle_id: ID du vehicule dans le referentiel.
        details: Liste de dicts avec {fuel, gearbox, horse_power, seats?, price?, year?, km?}.

    Returns:
        Liste des IDs de VehicleSpec nouvellement promues.
    """
    from app.models.observed_motorization import ObservedMotorization

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    promoted_ids: list[int] = []

    # Phase 1 : grouper les combos par (fuel, gearbox, hp) avec dedup par hash d'annonce
    combos: dict[tuple[str, str, int], dict] = {}
    for detail in details:
        if not isinstance(detail, dict):
            continue

        fuel = (str(detail.get("fuel") or "")).strip().lower()
        gearbox = (str(detail.get("gearbox") or "")).strip().lower()
        hp_raw = detail.get("horse_power") or detail.get("power_din_hp")
        try:
            hp = int(hp_raw) if hp_raw else 0
        except (ValueError, TypeError):
            hp = 0

        if not fuel or not gearbox or not hp:
            continue  # Combo incomplete, on skip

        seats_raw = detail.get("seats")
        try:
            seats = int(seats_raw) if seats_raw else None
        except (ValueError, TypeError):
            seats = None

        fiscal_raw = detail.get("power_fiscal_cv")
        try:
            fiscal = int(fiscal_raw) if fiscal_raw else None
        except (ValueError, TypeError):
            fiscal = None

        key = (fuel, gearbox, hp)
        ad_h = _ad_hash(detail)
        if key not in combos:
            combos[key] = {"hashes": [], "seats": seats, "fiscal": fiscal}
        combos[key]["hashes"].append(ad_h)
        # Garder la premiere valeur de seats/fiscal non-None
        if seats and not combos[key]["seats"]:
            combos[key]["seats"] = seats
        if fiscal and not combos[key]["fiscal"]:
            combos[key]["fiscal"] = fiscal

    # Phase 2 : pour chaque combo, creer ou mettre a jour l'ObservedMotorization
    for (fuel, transmission, power_hp), info in combos.items():
        ad_hashes = info["hashes"]
        seats = info["seats"]
        fiscal = info["fiscal"]

        existing = ObservedMotorization.query.filter_by(
            vehicle_id=vehicle_id,
            fuel=fuel,
            transmission=transmission,
            power_din_hp=power_hp,
        ).first()

        if existing:
            # Charger les hashes existants pour dedup
            existing_hashes = set(json.loads(existing.source_ids or "[]"))
            new_hashes = [h for h in ad_hashes if h not in existing_hashes]

            existing.count += len(ad_hashes)
            existing.distinct_sources += len(new_hashes)
            all_hashes = list(existing_hashes | set(ad_hashes))
            # Limiter a 200 hashes pour ne pas exploser la colonne TEXT
            existing.source_ids = json.dumps(all_hashes[-200:])
            existing.last_seen_at = now
            if seats and not existing.seats:
                existing.seats = seats
            if fiscal and not existing.power_fiscal_cv:
                existing.power_fiscal_cv = fiscal

            # Verifier si la motorisation a atteint le seuil de promotion
            if not existing.promoted and existing.distinct_sources >= PROMOTION_THRESHOLD:
                spec_id = _promote_to_vehicle_spec(existing)
                if spec_id:
                    existing.promoted = True
                    existing.promoted_at = now
                    promoted_ids.append(spec_id)
        else:
            # Premiere observation de cette combinaison pour ce vehicule
            moto = ObservedMotorization(
                vehicle_id=vehicle_id,
                fuel=fuel,
                transmission=transmission,
                power_din_hp=power_hp,
                seats=seats,
                power_fiscal_cv=fiscal,
                count=len(ad_hashes),
                distinct_sources=len(set(ad_hashes)),
                source_ids=json.dumps(list(set(ad_hashes))),
                last_seen_at=now,
            )
            db.session.add(moto)
            db.session.flush()  # Obtenir l'ID avant possible promotion

            # Cas rare mais possible : batch initial avec 3+ annonces distinctes
            if moto.distinct_sources >= PROMOTION_THRESHOLD:
                spec_id = _promote_to_vehicle_spec(moto)
                if spec_id:
                    moto.promoted = True
                    moto.promoted_at = now
                    promoted_ids.append(spec_id)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        logger.warning(
            "IntegrityError during motorization enrichment for vehicle_id=%d",
            vehicle_id,
        )

    if promoted_ids:
        logger.info(
            "Promoted %d motorization(s) to VehicleSpec for vehicle_id=%d",
            len(promoted_ids),
            vehicle_id,
        )
        # Mettre a jour le status d'enrichissement du vehicule
        _maybe_update_enrichment_status(vehicle_id)

    return promoted_ids


# --- Promotion ---


def _promote_to_vehicle_spec(moto) -> int | None:
    """Cree un VehicleSpec a partir d'une motorisation observee confirmee.

    C'est l'etape finale du pipeline : une motorisation vue sur assez de sources
    devient une spec officielle du vehicule. On verifie d'abord qu'un doublon
    n'existe pas deja (race condition possible avec des imports paralleles).

    Returns:
        L'ID du VehicleSpec cree, ou None si doublon.
    """
    from app.models.vehicle import VehicleSpec

    # Check doublon (meme vehicule, fuel, transmission, puissance)
    existing_spec = VehicleSpec.query.filter_by(
        vehicle_id=moto.vehicle_id,
        fuel_type=capitalize_fuel(moto.fuel),
        transmission=capitalize_transmission(moto.transmission),
        power_hp=moto.power_din_hp,
    ).first()

    if existing_spec:
        logger.debug(
            "VehicleSpec already exists for vehicle_id=%d %s/%s/%dch",
            moto.vehicle_id,
            moto.fuel,
            moto.transmission,
            moto.power_din_hp,
        )
        return None

    engine_name = build_engine_name(moto.fuel, moto.transmission, moto.power_din_hp)

    spec = VehicleSpec(
        vehicle_id=moto.vehicle_id,
        fuel_type=capitalize_fuel(moto.fuel),
        transmission=capitalize_transmission(moto.transmission),
        power_hp=moto.power_din_hp,
        number_of_seats=moto.seats,
        engine=engine_name,
    )
    db.session.add(spec)
    db.session.flush()

    logger.info(
        "Created VehicleSpec id=%d for vehicle_id=%d: %s",
        spec.id,
        moto.vehicle_id,
        engine_name,
    )
    return spec.id


def _maybe_update_enrichment_status(vehicle_id: int) -> None:
    """Met a jour enrichment_status du vehicule si des specs ont ete promues.

    Le status passe de "partial" a "complete" des qu'il y a au moins une VehicleSpec.
    Ca permet a l'admin de voir quels vehicules sont prets pour le scan.
    """
    from app.models.vehicle import Vehicle, VehicleSpec

    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        return

    spec_count = VehicleSpec.query.filter_by(vehicle_id=vehicle_id).count()
    if spec_count > 0 and vehicle.enrichment_status != "complete":
        vehicle.enrichment_status = "complete"
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.debug("Failed to update enrichment_status for vehicle_id=%d", vehicle_id)
            return
        logger.info(
            "Vehicle %s %s enrichment_status -> complete (%d specs)",
            vehicle.brand,
            vehicle.model,
            spec_count,
        )
