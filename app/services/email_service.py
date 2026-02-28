"""Service email -- generation d'emails vendeur via Gemini."""

import logging

from app.extensions import db
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services import gemini_service
from app.services.extraction import extract_ad_data

logger = logging.getLogger(__name__)

# Mapping filter_id -> nom lisible pour le prompt (par defaut FR)
_FILTER_NAMES = {
    "L1": "Completude annonce",
    "L2": "Identification vehicule",
    "L3": "Coherence donnees",
    "L4": "Prix vs marche",
    "L5": "Statistiques marche",
    "L6": "Telephone vendeur",
    "L7": "Verification SIRET",
    "L8": "Detection import",
    "L9": "Qualite annonce",
    "L10": "Anciennete annonce",
}

# Overrides par pays
_FILTER_NAMES_CH = {**_FILTER_NAMES, "L7": "Verification UID"}
_FILTER_NAMES_BY_COUNTRY = {"CH": _FILTER_NAMES_CH}

_SYSTEM_PROMPT_TEMPLATE = """\
Tu es un acheteur automobile averti qui redige un email au vendeur \
d'un vehicule d'occasion sur {site_name}.

REGLES ABSOLUES:
- Ecris en francais courant, sans fautes, sans emojis, sans markdown
- Ton: direct, poli, competent. Tu sais de quoi tu parles.
- NE MENTIONNE JAMAIS que tu utilises un outil d'analyse ou une IA
- NE FABRIQUE AUCUNE information: utilise UNIQUEMENT les donnees fournies
- Si une donnee est manquante (vide ou '?'), ne la mentionne pas
- Structure: objet, salutation, corps (3-5 paragraphes), proposition RDV, signature
- Commence par "Objet : " sur la premiere ligne"""

# Mapping source → site display name
_SOURCE_NAMES = {
    "leboncoin": "Le Bon Coin",
    "autoscout24": "AutoScout24",
}


def _detect_source(scan_url: str, raw_data: dict) -> str:
    """Detecte la source (leboncoin/autoscout24) depuis l'URL ou le raw_data."""
    if "autoscout24" in (scan_url or ""):
        return "autoscout24"
    if raw_data.get("source") == "autoscout24":
        return "autoscout24"
    return "leboncoin"


def _build_signals_block(filters: list[dict], country: str = "FR") -> str:
    """Construit un bloc de texte decrivant les signaux d'analyse."""
    alerts = []
    positives = []
    names = _FILTER_NAMES_BY_COUNTRY.get(country, _FILTER_NAMES)

    for f in filters:
        fid = f.get("filter_id", "")
        status = f.get("status", "")
        message = f.get("message", "")
        details = f.get("details") or {}
        name = names.get(fid, fid)

        if status == "fail":
            detail_text = _extract_detail_text(fid, details)
            alerts.append(f"[ALERTE] {name}: {message}{detail_text}")
        elif status == "warning":
            detail_text = _extract_detail_text(fid, details)
            alerts.append(f"[ATTENTION] {name}: {message}{detail_text}")
        elif status == "pass":
            positives.append(f"[OK] {name}: {message}")

    parts = []
    if alerts:
        parts.append("Points d'attention a mentionner dans l'email:\n" + "\n".join(alerts))
    if positives:
        parts.append(
            "Points positifs (utilise-les pour montrer que tu connais le vehicule):\n"
            + "\n".join(positives)
        )
    return "\n\n".join(parts) if parts else "Aucun signal particulier."


def _extract_detail_text(filter_id: str, details: dict) -> str:
    """Extrait les details pertinents d'un filtre pour le prompt."""
    parts = []

    if filter_id == "L4":
        ref_price = details.get("reference_price") or details.get("argus_mid")
        if ref_price:
            parts.append(f"prix reference: {ref_price} EUR")
        deviation = details.get("deviation_pct") or details.get("price_deviation_pct")
        if deviation is not None:
            if isinstance(deviation, (int, float)):
                parts.append(f"ecart: {deviation:+.0f}%")
            else:
                parts.append(f"ecart: {deviation}")
        days = details.get("days_online")
        if days:
            parts.append(f"{days}j en ligne")

    elif filter_id == "L7":
        # France: etat_administratif / nom_complet
        etat = details.get("etat_administratif") or details.get("etat")
        if etat:
            parts.append(f"etat entreprise: {etat}")
        nom = details.get("nom_complet") or details.get("denomination") or details.get("name")
        if nom:
            parts.append(f"societe: {nom}")
        # Suisse: UID + status Zefix
        uid = details.get("formatted") or details.get("uid")
        if uid and uid.startswith("CHE"):
            parts.append(f"UID: {uid}")
        zefix_status = details.get("status")
        if zefix_status:
            parts.append(f"statut: {zefix_status}")
        # Dealer rating (AS24 etc.)
        dealer_rating = details.get("dealer_rating")
        dealer_review_count = details.get("dealer_review_count")
        if dealer_rating:
            parts.append(f"note vendeur: {dealer_rating}/5 ({dealer_review_count} avis)")

    elif filter_id == "L8":
        signals = details.get("signals") or []
        if signals:
            parts.append(f"signaux import: {', '.join(str(s) for s in signals)}")

    elif filter_id == "L10":
        days = details.get("days_online")
        if days:
            parts.append(f"{days}j en ligne")
        republished = details.get("republished")
        if republished:
            parts.append("republication detectee")

    elif filter_id == "L3":
        incoherences = details.get("incoherences") or details.get("issues") or []
        if incoherences:
            parts.append(f"incoherences: {', '.join(str(i) for i in incoherences[:3])}")

    return f" ({', '.join(parts)})" if parts else ""


def _import_consigne(country: str) -> str:
    """Retourne la consigne import adaptee au pays."""
    if country == "CH":
        return "Si import detecte, demande le permis de circulation et le dedouanement (formulaire 13.20A)"
    return "Si import detecte, demande COC et carte grise"


def _detect_country_from_source(source: str, scan_url: str = "") -> str:
    """Detecte le pays depuis la source et l'URL pour le prompt email."""
    url_lower = (scan_url or "").lower()
    if ".ch" in url_lower:
        return "CH"
    if ".de" in url_lower:
        return "DE"
    if ".at" in url_lower:
        return "AT"
    if ".it" in url_lower:
        return "IT"
    return "FR"


def build_email_prompt(scan_data: dict, filters: list[dict], source: str = "leboncoin") -> str:
    """Construit le prompt pour Gemini a partir des donnees d'analyse."""
    site_name = _SOURCE_NAMES.get(source, source)
    country = _detect_country_from_source(source, scan_data.get("url", ""))
    make = scan_data.get("make") or "?"
    model = scan_data.get("model") or "?"

    # Prix: afficher dans la devise originale si disponible
    price_original = scan_data.get("price_original")
    currency_original = scan_data.get("currency_original")
    if price_original and currency_original:
        price = f"{price_original} {currency_original}"
    else:
        price = str(scan_data.get("price_eur") or scan_data.get("price") or "?") + " EUR"

    year = scan_data.get("year_model") or scan_data.get("year") or ""
    mileage = scan_data.get("mileage_km") or ""
    fuel = scan_data.get("fuel") or ""
    gearbox = scan_data.get("gearbox") or ""
    color = scan_data.get("color") or ""
    owner_type = scan_data.get("owner_type") or "private"
    owner_name = scan_data.get("owner_name") or ""
    days_online = scan_data.get("days_online") or ""
    url = scan_data.get("url") or ""
    image_count = scan_data.get("image_count") or ""
    city = ""
    loc = scan_data.get("location")
    if isinstance(loc, dict):
        city = loc.get("city") or loc.get("department") or ""
    description = scan_data.get("description") or ""
    if len(description) > 500:
        description = description[:500] + "..."

    signals_block = _build_signals_block(filters, country=country)

    # Contexte vendeur adapte au pays
    if owner_type == "pro":
        if country == "CH":
            seller_context = (
                "VENDEUR PROFESSIONNEL (Suisse). Pose des questions precises: "
                "historique du vehicule, carnet d'entretien complet, "
                "garanties professionnelles, possibilite de facture. "
                "Demande le permis de circulation et le rapport d'expertise MFK. "
                "Mentionne que tu veux voir les documents en personne."
            )
        else:
            seller_context = (
                "VENDEUR PROFESSIONNEL. Pose des questions precises: "
                "historique du vehicule en parc, carnet d'entretien complet, "
                "garanties professionnelles, possibilite de facture. "
                "Mentionne que tu veux voir les documents en personne."
            )
    elif country == "CH":
        seller_context = (
            "VENDEUR PARTICULIER (Suisse). Sois cordial mais direct. "
            "Demande les factures d'entretien, le rapport d'expertise MFK, "
            "les raisons de la vente, et si le vehicule a eu des sinistres."
        )
    else:
        seller_context = (
            "VENDEUR PARTICULIER. Sois cordial mais direct. "
            "Demande les factures d'entretien, le controle technique, "
            "les raisons de la vente, et si le vehicule a eu des sinistres."
        )

    example = f"""\
--- EXEMPLE DE BON EMAIL ---
Objet : Demande d'informations - Peugeot 308 2019 - {site_name}

Bonjour,

Votre Peugeot 308 de 2019 affichee a 14 500 EUR a 85 000 km a retenu \
mon attention. Je cherche activement ce type de vehicule et j'ai quelques \
questions avant de me deplacer.

J'ai remarque que l'annonce est en ligne depuis plus de 45 jours. \
Le prix est-il negociable ? Par ailleurs, le vehicule etant potentiellement \
immatricule a l'etranger, pourriez-vous me confirmer son origine et me \
fournir le certificat de conformite ?

Pourriez-vous egalement me transmettre :
- Le dernier rapport de controle technique
- Les factures d'entretien recentes (vidange, freins, distribution)
- Le nombre de proprietaires precedents

Je suis disponible en semaine apres 18h et le week-end pour venir voir \
le vehicule et effectuer un essai. N'hesitez pas a me proposer un creneau.

Cordialement,
[Votre prenom]
--- FIN EXEMPLE ---"""

    prompt = f"""{example}

Maintenant, redige un email similaire pour CE vehicule:

VEHICULE:
- Marque: {make}
- Modele: {model}
- Annee: {year}
- Carburant: {fuel}
- Boite: {gearbox}
- Couleur: {color}
- Kilometrage: {mileage} km
- Prix demande: {price}
- Localisation: {city}
- En ligne depuis: {days_online} jours
- Nombre de photos: {image_count}
- URL: {url}

VENDEUR:
- Type: {owner_type}
- Nom: {owner_name}

DESCRIPTION ANNONCE (extrait):
{description}

ANALYSE DU VEHICULE:
{signals_block}

CONTEXTE:
{seller_context}

CONSIGNES FINALES:
- Integre naturellement les signaux d'analyse comme des questions \
pertinentes d'acheteur averti
- Si le vehicule est en ligne depuis longtemps, mentionne-le pour negocier
- Si peu de photos ({image_count}), demande des photos supplementaires
- {_import_consigne(country)}
- Si entreprise radiee/fermee, pose la question de la garantie
- Termine par une proposition de rendez-vous concret
- Signe "[Votre prenom]"
- 8 a 15 phrases maximum dans le corps de l'email
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

    # Reextraire les donnees structurees depuis le raw_data.
    # Pour LBC: raw_data est un next_data qu'on re-extrait.
    # Pour AS24+: raw_data est deja un ad_data normalise.
    raw_data = scan.raw_data or {}
    source = _detect_source(scan.url, raw_data)

    if source != "leboncoin" and raw_data.get("make"):
        # Pre-normalized ad_data (AutoScout24, etc.)
        ad_data = raw_data
    else:
        # Legacy LBC path
        try:
            ad_data = extract_ad_data(raw_data)
        except Exception:
            logger.warning("extract_ad_data failed for scan %d, fallback minimal", scan_id)
            ad_data = {}

    # Enrichir avec les champs du ScanLog (plus fiables car normalises)
    scan_data = {**ad_data}
    if scan.vehicle_make:
        scan_data["make"] = scan.vehicle_make
    if scan.vehicle_model:
        scan_data["model"] = scan.vehicle_model
    if scan.price_eur:
        scan_data["price_eur"] = scan.price_eur
    if scan.days_online is not None:
        scan_data["days_online"] = scan.days_online
    if scan.url:
        scan_data["url"] = scan.url

    # Recuperer les resultats de filtres avec details
    filter_results = FilterResultDB.query.filter_by(scan_id=scan_id).all()
    filters = [
        {
            "filter_id": fr.filter_id,
            "status": fr.status,
            "message": fr.message,
            "details": fr.details,
        }
        for fr in filter_results
    ]

    prompt = build_email_prompt(scan_data, filters, source=source)

    # Appel Gemini avec system prompt adapte a la source
    site_name = _SOURCE_NAMES.get(source, source)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(site_name=site_name)
    generated_text, total_tokens = gemini_service.generate_text(
        prompt=prompt,
        feature="email_draft",
        system_prompt=system_prompt,
        max_output_tokens=1024,
        temperature=0.4,
    )

    # Creer le brouillon
    owner_type = scan_data.get("owner_type") or "private"
    owner_name = scan_data.get("owner_name") or ""
    draft = EmailDraft(
        scan_id=scan_id,
        listing_url=scan.url or "",
        vehicle_make=scan_data.get("make", ""),
        vehicle_model=scan_data.get("model", ""),
        seller_type=owner_type,
        seller_name=owner_name,
        seller_phone=scan_data.get("phone") or "",
        seller_email="",
        prompt_used=prompt,
        generated_text=generated_text,
        llm_model=gemini_service._get_model(),
        tokens_used=total_tokens,
    )
    db.session.add(draft)
    db.session.commit()

    logger.info(
        "Email draft #%d cree pour scan #%d (%d tokens)",
        draft.id,
        scan_id,
        total_tokens,
    )
    return draft
