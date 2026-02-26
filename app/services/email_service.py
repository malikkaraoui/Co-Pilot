"""Service email -- generation d'emails vendeur via Gemini."""

import logging

from app.extensions import db
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services import gemini_service

logger = logging.getLogger(__name__)


def build_email_prompt(scan_data: dict, filters: list[dict]) -> str:
    """Construit le prompt pour Gemini a partir des donnees d'analyse."""
    make = scan_data.get("make", "?")
    model = scan_data.get("model", "?")
    price = scan_data.get("price", "?")
    year = scan_data.get("year", "")
    mileage = scan_data.get("mileage_km", "")
    fuel = scan_data.get("fuel", "")
    owner_type = scan_data.get("owner_type", "private")
    owner_name = scan_data.get("owner_name", "")
    days_online = scan_data.get("days_online", "")
    url = scan_data.get("url", "")

    # Signaux d'alerte (filtres warning/fail)
    signals = []
    for f in filters:
        if f.get("status") in ("warning", "fail"):
            signals.append(f"- {f['filter_id']}: {f.get('message', 'Signal detecte')}")

    signals_text = "\n".join(signals) if signals else "Aucun signal d'alerte majeur."

    # Adapter le contexte vendeur
    if owner_type == "pro":
        seller_context = (
            "Le vendeur est un professionnel. "
            "Adapte le ton en consequence: pose des questions precises sur l'historique "
            "du vehicule en flotte, le carnet d'entretien, et les garanties professionnelles."
        )
    else:
        seller_context = (
            "Le vendeur est un particulier. "
            "Sois cordial mais direct. Pose des questions concretes sur l'utilisation "
            "quotidienne, les factures d'entretien, et les raisons de la vente."
        )

    prompt = f"""Redige un email a un vendeur pour le vehicule suivant.

VEHICULE:
- Marque: {make}
- Modele: {model}
- Annee: {year}
- Carburant: {fuel}
- Kilometrage: {mileage} km
- Prix demande: {price} EUR
- En ligne depuis: {days_online} jours
- URL: {url}

VENDEUR:
- Type: {owner_type}
- Nom: {owner_name}

SIGNAUX D'ANALYSE:
{signals_text}

CONTEXTE VENDEUR:
{seller_context}

CONSIGNES:
- Ton: acheteur averti et direct, sans etre agressif
- Pose des questions precises basees sur les signaux d'analyse
- Si le prix est bas + annonce ancienne, mentionne-le subtilement
- Si peu de photos, demande des photos supplementaires
- Termine par une proposition de rendez-vous ou appel
- NE MENTIONNE PAS que tu utilises un outil d'analyse
- NE FABRIQUE PAS d'informations: utilise uniquement les donnees fournies ci-dessus
"""
    return prompt


def generate_email_draft(scan_id: int) -> EmailDraft:
    """Genere un brouillon d'email vendeur a partir d'un scan.

    Raises:
        ValueError: Si le scan_id n'existe pas.
        ConnectionError: Si Gemini est injoignable.
    """
    scan = db.session.get(ScanLog, scan_id)
    if not scan:
        raise ValueError(f"Scan introuvable: {scan_id}")

    raw = scan.raw_data or {}

    # Recuperer les resultats de filtres
    filter_results = FilterResultDB.query.filter_by(scan_id=scan_id).all()
    filters = [
        {
            "filter_id": fr.filter_id,
            "status": fr.status,
            "message": fr.message,
        }
        for fr in filter_results
    ]

    # Construire les donnees pour le prompt
    scan_data = {
        "make": scan.vehicle_make or raw.get("make", ""),
        "model": scan.vehicle_model or raw.get("model", ""),
        "price": scan.price_eur or raw.get("price", ""),
        "year": raw.get("year", ""),
        "mileage_km": raw.get("mileage_km", ""),
        "fuel": raw.get("fuel", ""),
        "owner_type": raw.get("owner_type", "private"),
        "owner_name": raw.get("owner_name", ""),
        "days_online": scan.days_online or raw.get("days_online", ""),
        "url": scan.url or "",
    }

    prompt = build_email_prompt(scan_data, filters)

    # Appel Gemini
    generated_text = gemini_service.generate_text(
        prompt=prompt,
        feature="email_draft",
    )

    # Creer le brouillon
    draft = EmailDraft(
        scan_id=scan_id,
        listing_url=scan.url or "",
        vehicle_make=scan_data["make"],
        vehicle_model=scan_data["model"],
        seller_type=scan_data["owner_type"],
        seller_name=scan_data["owner_name"],
        seller_phone=raw.get("phone", ""),
        seller_email=raw.get("email", ""),
        prompt_used=prompt,
        generated_text=generated_text,
        llm_model=gemini_service._get_model(),
        tokens_used=0,
    )
    db.session.add(draft)
    db.session.commit()

    logger.info("Email draft #%d cree pour scan #%d", draft.id, scan_id)
    return draft
