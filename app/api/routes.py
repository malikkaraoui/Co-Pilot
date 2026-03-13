"""Definitions des routes API.

Ce module contient les endpoints principaux consommes par l'extension Chrome :
- /health : healthcheck pour monitoring
- /analyze : coeur de l'app — analyse une annonce et retourne un score de confiance
- /email-draft : generation de brouillon email vendeur via Gemini
- /scan-report : generation PDF du rapport d'analyse
"""

import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Any

import httpx
from flask import current_app, jsonify, make_response, request
from fpdf.errors import FPDFException
from pydantic import ValidationError as PydanticValidationError

from app.api import api_bp
from app.errors import ExtractionError
from app.extensions import db, limiter
from app.filters.engine import FilterEngine
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.filter_result import FilterResultSchema
from app.services import email_service
from app.services.currency_service import convert_to_eur
from app.services.extraction import extract_ad_data
from app.services.scoring import calculate_score

logger = logging.getLogger(__name__)


@api_bp.route("/health", methods=["GET"])
def health():
    """Point de controle de sante de l'API."""
    return jsonify(
        {
            "success": True,
            "data": {
                "status": "ok",
                "version": current_app.config.get("APP_VERSION", "0.0.0"),
            },
        }
    )


@api_bp.route("/analyze", methods=["POST"])
@limiter.limit("30/minute")
def analyze():
    """Analyse une annonce Leboncoin et retourne un score de confiance.

    Attend un corps JSON avec un champ 'next_data' contenant le
    payload __NEXT_DATA__ de la page Leboncoin.
    """
    # Catch-all explicite pour ne jamais renvoyer une 500 HTML a l'extension.
    # On liste les types d'exception concrets au lieu d'un bare except.
    try:
        return _do_analyze()
    except (KeyError, ValueError, AttributeError, TypeError, OSError, httpx.HTTPError) as exc:
        logger.error("Unhandled error in /analyze: %s\n%s", exc, traceback.format_exc())
        return jsonify(
            {
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": "Erreur interne du serveur.",
                "data": None,
            }
        ), 500


def _do_analyze():
    """Logique interne de l'endpoint analyze, encapsulee pour le catch-all.

    Le flow complet :
    1. Validation du JSON entrant (Pydantic)
    2. Extraction des donnees de l'annonce (LBC legacy ou pre-normalise)
    3. Canonicalisation marque/modele
    4. Detection pays + conversion devise
    5. Execution des 11 filtres d'analyse
    6. Calcul du score global
    7. Persistence en DB (best-effort)
    8. Enrichissements optionnels (motorisations, video, pneus, fiabilite)
    9. Construction de la reponse JSON
    """
    # --- 1. Validation de la requete ---
    json_data = request.get_json(silent=True)
    if not json_data:
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "Le corps de la requete doit etre du JSON valide.",
                "data": None,
            }
        ), 400

    try:
        req = AnalyzeRequest.model_validate(json_data)
    except PydanticValidationError as exc:
        logger.warning("Validation error: %s", exc)
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "Donnees invalides. Verifiez le format du payload.",
                "data": None,
            }
        ), 400

    # Au moins un des deux payloads est requis : next_data (LBC) ou ad_data (multi-source)
    if req.next_data is None and req.ad_data is None:
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "next_data ou ad_data requis.",
                "data": None,
            }
        ), 400

    # --- 2. Extraction des donnees de l'annonce ---
    if req.ad_data is not None:
        # Chemin pre-normalise (AutoScout24, La Centrale, etc.) :
        # l'extension envoie deja un dict propre, pas besoin d'extraction.
        ad_data = req.ad_data
        if req.source:
            ad_data["source"] = req.source
    else:
        # Chemin legacy LBC : on parse le gros blob __NEXT_DATA__
        try:
            ad_data = extract_ad_data(req.next_data)
        except ExtractionError as exc:
            logger.warning("Extraction failed: %s", exc)
            return jsonify(
                {
                    "success": False,
                    "error": "EXTRACTION_ERROR",
                    "message": "Impossible d'extraire les donnees de cette annonce.",
                    "data": None,
                }
            ), 422

    # --- 3. Canonicalisation marque/modele ---
    # Aligne l'affichage (ex: "bmw" → "BMW"), le filtre L2 referentiel,
    # et les recherches de prix marche. Meme logique pour toutes les sources.
    try:
        from app.services.vehicle_lookup import display_brand, display_model

        if ad_data.get("make"):
            ad_data["make"] = display_brand(str(ad_data["make"]))
        if ad_data.get("model"):
            ad_data["model"] = display_model(str(ad_data["model"]))
    except Exception:
        logger.debug("Make/model canonicalization skipped", exc_info=True)

    # --- 4. Detection pays + conversion devise ---
    # Le pays est deduit du TLD de l'URL (ex: .ch → CH, .de → DE)
    # pour que les filtres L6 (telephone) et L7 (SIRET) s'adaptent.
    ad_data["country"] = _detect_country(req.url or "", req.source)

    # Si le prix est en CHF ou autre devise, on le convertit en EUR
    # pour que les filtres L4/L5 comparent des pommes avec des pommes.
    # On garde le prix original pour l'affichage dans l'extension.
    original_currency = ad_data.get("currency")
    original_price = ad_data.get("price_eur")
    price_eur, was_converted = convert_to_eur(original_price, original_currency)
    if was_converted:
        ad_data["price_eur"] = price_eur
        ad_data["price_original"] = original_price
        ad_data["currency_original"] = original_currency

    # Calcul days_online si absent mais publication_date present.
    # Les sources pre-normalisees (AS24) envoient la date brute
    # mais pas le delta — on le calcule ici pour L10.
    if ad_data.get("days_online") is None and ad_data.get("publication_date"):
        try:
            pub_str = ad_data["publication_date"]
            pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            ad_data["days_online"] = (datetime.now(timezone.utc) - pub_date).days
        except (ValueError, TypeError):
            pass  # format de date non reconnu, L10 fera skip

    # --- Detection non-voiture ---
    # On verifie la categorie dans l'URL (LBC uniquement) + presence marque/modele.
    # Pour les sources non-LBC, le format d'URL ne contient pas de categorie exploitable.
    url = req.url or ""
    is_lbc_source = req.source is None or req.source == "leboncoin"
    url_category = _extract_url_category(url) if is_lbc_source else None
    has_vehicle_attrs = bool(ad_data.get("make")) and bool(ad_data.get("model"))

    # Motos : categorie reconnue mais pas encore supportee
    if url_category == "motos":
        logger.info("NOT_SUPPORTED: category=motos, url=%s", url)
        return jsonify(
            {
                "success": False,
                "error": "NOT_SUPPORTED",
                "message": "Les motos, c'est pas encore notre rayon... mais ca arrive tres vite !",
                "data": {"category": "motos"},
            }
        ), 422

    # Autres categories non-voiture sans attributs vehicule (LBC uniquement) :
    # equipement_auto, caravaning, etc. → on refuse poliment.
    if is_lbc_source and url_category != "voitures" and not has_vehicle_attrs:
        logger.info(
            "NOT_A_VEHICLE: category=%s, make=%r, model=%r",
            url_category,
            ad_data.get("make"),
            ad_data.get("model"),
        )
        return jsonify(
            {
                "success": False,
                "error": "NOT_A_VEHICLE",
                "message": "C'est pas une bagnole... bien tente !",
                "data": {"category": url_category or "inconnue"},
            }
        ), 422

    # --- 5. Execution des 11 filtres d'analyse ---
    engine = _build_engine()
    try:
        filter_results = engine.run_all(ad_data)
    except (KeyError, ValueError, AttributeError, TypeError, OSError) as exc:
        logger.error("Engine crash: %s: %s", type(exc).__name__, exc)
        return jsonify(
            {
                "success": False,
                "error": "ENGINE_ERROR",
                "message": "Erreur lors de l'analyse. Reessayez.",
                "data": None,
            }
        ), 500

    # --- 6. Calcul du score ---
    score, is_partial = calculate_score(filter_results)

    # --- 7. Persistence (best-effort) ---
    # On sauvegarde le scan et ses resultats en DB pour le dashboard admin
    # et les stats. Si ca echoue, la reponse API part quand meme.
    try:
        scan = ScanLog(
            url=req.url,
            raw_data=json_data.get("next_data") or json_data.get("ad_data"),
            score=score,
            is_partial=is_partial,
            vehicle_make=ad_data.get("make"),
            vehicle_model=ad_data.get("model"),
            price_eur=ad_data.get("price_eur"),
            days_online=ad_data.get("days_online"),
            republished=ad_data.get("republished", False),
            source=req.source or ("leboncoin" if is_lbc_source else "autoscout24"),
            country=(ad_data.get("country") or "FR").upper(),
        )
        db.session.add(scan)
        db.session.flush()

        for r in filter_results:
            db.session.add(
                FilterResultDB(
                    scan_id=scan.id,
                    filter_id=r.filter_id,
                    status=r.status,
                    score=r.score,
                    message=r.message,
                    details=r.details,
                )
            )

        db.session.commit()
        logger.info("Persisted ScanLog id=%d score=%d", scan.id, score)
    except Exception as exc:  # noqa: BLE001 -- best-effort, ne casse jamais la reponse
        db.session.rollback()
        scan = None
        logger.warning("Failed to persist scan: %s: %s", type(exc).__name__, exc)

    # --- 8a. Enrichissement motorisations observees (best-effort) ---
    # Alimente la table des motorisations crowdsourcees pour chaque scan.
    # Ca permet de decouvrir des variantes moteur non presentes dans le CSV Kaggle.
    if scan and ad_data.get("make") and ad_data.get("model") and not current_app.testing:
        try:
            from app.services.motorization_service import enrich_observed_motorizations
            from app.services.vehicle_lookup import find_vehicle

            vehicle = find_vehicle(ad_data["make"], ad_data["model"])
            if vehicle:
                scan_detail = {
                    "fuel": ad_data.get("fuel"),
                    "gearbox": ad_data.get("gearbox"),
                    "horse_power": ad_data.get("power_din_hp"),
                    "seats": ad_data.get("seats"),
                    "power_fiscal_cv": ad_data.get("power_fiscal_cv"),
                    "price": ad_data.get("price_eur", 0),
                    "year": ad_data.get("year_model", 0),
                    "km": ad_data.get("mileage_km", 0),
                }
                enrich_observed_motorizations(vehicle.id, [scan_detail])
        except Exception:  # noqa: BLE001
            logger.debug("Scan motorization enrichment skipped", exc_info=True)

    # --- 9. Construction de la reponse ---
    filters_out = [
        FilterResultSchema(
            filter_id=r.filter_id,
            status=r.status,
            score=r.score,
            message=r.message,
            details=r.details,
        )
        for r in filter_results
    ]

    # 8b. Video YouTube featured pour ce vehicule (best-effort)
    featured_video = None
    make = ad_data.get("make")
    model = ad_data.get("model")
    if make and model:
        try:
            from app.services.youtube_service import get_featured_video

            featured_video = get_featured_video(make, model)
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Featured video lookup failed: %s", exc)

    # 8c. Dimensions pneus pour ce vehicule (best-effort)
    tire_sizes_data = None
    year = ad_data.get("year_model")
    if make and model and year:
        try:
            from app.services.tire_service import get_tire_sizes

            tire_sizes_data = get_tire_sizes(make, model, year)
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Tire sizes lookup failed: %s", exc)

    # 8d. Remplissage background pneus pour un AUTRE vehicule ---
    # Strategie "piggyback" : a chaque scan, on profite du thread pour
    # remplir les dimensions d'un vehicule qui n'en a pas encore.
    if make and model and not current_app.testing:
        try:
            import threading

            from app.services.tire_service import fill_next_missing_vehicle

            app_obj = current_app._get_current_object()

            def _run_bg_fill(exclude_mm: tuple[str, str]) -> None:
                try:
                    with app_obj.app_context():
                        fill_next_missing_vehicle(exclude_make_model=exclude_mm)
                except Exception:  # noqa: BLE001 — background thread, ne doit jamais crasher
                    pass

            t = threading.Thread(
                target=_run_bg_fill,
                args=((make.lower(), model.lower()),),
                daemon=True,
            )
            t.start()
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Background tire fill failed: %s", exc)

    # 8e. Fiabilite moteur (best-effort) ---
    # On cherche la note de fiabilite du moteur correspondant a ce vehicule,
    # en matchant sur le code moteur + type de carburant.
    engine_reliability_data = None
    if make and model:
        try:
            from app.models.vehicle import VehicleSpec
            from app.services.engine_reliability_service import get_engine_reliability
            from app.services.vehicle_lookup import find_vehicle

            veh = find_vehicle(make, model)
            if veh:
                fuel_raw = (ad_data.get("fuel") or "").lower()
                specs = VehicleSpec.query.filter_by(vehicle_id=veh.id).all()
                matched_spec = None
                if specs:
                    # On cherche la spec dont le fuel_type colle au carburant de l'annonce
                    for s in specs:
                        ft = (s.fuel_type or "").lower()
                        if fuel_raw and (fuel_raw in ft or ft in fuel_raw):
                            matched_spec = s
                            break
                    # Fallback : premiere spec si aucun match carburant
                    if not matched_spec:
                        matched_spec = specs[0]
                if matched_spec and matched_spec.engine:
                    rel = get_engine_reliability(matched_spec.engine, matched_spec.fuel_type)
                    if rel:
                        engine_reliability_data = {
                            "score": rel.score,
                            "stars": rel.stars,
                            "engine_code": rel.engine_code,
                            "brand": rel.brand,
                            "note": rel.note,
                            "matched": True,
                        }
                    else:
                        engine_reliability_data = {"matched": False}
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            logger.debug("Engine reliability lookup failed: %s", exc)

    vehicle_info: dict[str, Any] = {
        "make": make,
        "model": model,
        "year": ad_data.get("year_model"),
        "price": ad_data.get("price_eur"),
        "mileage": ad_data.get("mileage_km"),
    }
    # Inclure le prix original si une conversion de devise a ete appliquee
    if ad_data.get("price_original") is not None:
        vehicle_info["price_original"] = ad_data["price_original"]
        vehicle_info["currency"] = ad_data.get("currency_original", "EUR")

    response = AnalyzeResponse(
        scan_id=scan.id if scan else None,
        score=score,
        is_partial=is_partial,
        filters=filters_out,
        vehicle=vehicle_info,
        featured_video=featured_video,
        tire_sizes=tire_sizes_data,
        engine_reliability=engine_reliability_data,
    )

    return jsonify(
        {
            "success": True,
            "error": None,
            "message": None,
            "data": response.model_dump(),
        }
    )


def _build_engine() -> FilterEngine:
    """Construit et retourne un FilterEngine avec les 11 filtres enregistres.

    Les imports sont locaux pour eviter des imports circulaires au demarrage
    et pour ne charger les filtres que quand on en a vraiment besoin.
    """
    from app.filters.l1_extraction import L1ExtractionFilter
    from app.filters.l2_referentiel import L2ReferentielFilter
    from app.filters.l3_coherence import L3CoherenceFilter
    from app.filters.l4_price import L4PriceFilter
    from app.filters.l5_visual import L5VisualFilter
    from app.filters.l6_phone import L6PhoneFilter
    from app.filters.l7_siret import L7SiretFilter
    from app.filters.l8_reputation import L8ImportDetectionFilter
    from app.filters.l9_score import L9GlobalAssessmentFilter
    from app.filters.l10_listing_age import L10ListingAgeFilter
    from app.filters.l11_recall import L11RecallFilter

    engine = FilterEngine()
    engine.register(L1ExtractionFilter())
    engine.register(L2ReferentielFilter())
    engine.register(L3CoherenceFilter())
    engine.register(L4PriceFilter())
    engine.register(L5VisualFilter())
    engine.register(L6PhoneFilter())
    engine.register(L7SiretFilter())
    engine.register(L8ImportDetectionFilter())
    engine.register(L9GlobalAssessmentFilter())
    engine.register(L10ListingAgeFilter())
    engine.register(L11RecallFilter())
    return engine


# Regex pour extraire la categorie depuis une URL LBC : /ad/<category>/<id>
_URL_CATEGORY_RE = re.compile(r"/ad/([a-z_]+)/")


def _extract_url_category(url: str) -> str | None:
    """Extrait la categorie LeBonCoin depuis l'URL (ex. 'voitures', 'equipement_auto').

    Retourne None si le pattern n'est pas trouve (URL non-LBC ou format inattendu).
    """
    m = _URL_CATEGORY_RE.search(url)
    return m.group(1) if m else None


# Mapping TLD → code pays ISO 2 lettres pour la detection automatique.
# Utilise par _detect_country() pour adapter les filtres L6/L7 au contexte local.
_TLD_COUNTRY_MAP = {
    ".ch": "CH",
    ".de": "DE",
    ".at": "AT",
    ".it": "IT",
    ".nl": "NL",
    ".be": "BE",
    ".es": "ES",
    ".lu": "LU",
    ".pl": "PL",
    ".se": "SE",
    ".fr": "FR",
}


def _detect_country(url: str, source: str | None) -> str:
    """Detecte le pays depuis le TLD de l'URL ou la source.

    On scanne l'URL pour trouver un TLD connu (.ch, .de, etc.).
    Si rien ne matche, on assume la France par defaut (LBC).
    """
    url_lower = url.lower()
    for tld, country in _TLD_COUNTRY_MAP.items():
        if tld in url_lower:
            return country
    # leboncoin.fr => FR implicite
    if source is None or source == "leboncoin":
        return "FR"
    return "FR"


@api_bp.route("/email-draft", methods=["POST"])
def email_draft():
    """Genere un brouillon d'email vendeur via Gemini.

    L'extension envoie le scan_id, on recupere le contexte du scan
    et on genere un email personnalise avec les points d'attention.
    """
    data = request.get_json(silent=True) or {}
    scan_id = data.get("scan_id")

    if not scan_id:
        return jsonify({"success": False, "error": "scan_id requis"}), 400

    try:
        draft = email_service.generate_email_draft(scan_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except ConnectionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 503

    return jsonify(
        {
            "success": True,
            "error": None,
            "data": {
                "draft_id": draft.id,
                "generated_text": draft.generated_text,
                "status": draft.status,
                "vehicle_make": draft.vehicle_make,
                "vehicle_model": draft.vehicle_model,
                "tokens_used": draft.tokens_used,
            },
        }
    )


@api_bp.route("/scan-report", methods=["POST"])
def scan_report():
    """Genere et retourne le rapport PDF d'un scan existant.

    Le PDF est genere a la volee via fpdf2 et renvoye en attachment.
    L'extension le telecharge directement cote navigateur.
    """
    data = request.get_json(silent=True) or {}
    scan_id = data.get("scan_id")

    if scan_id is None:
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "scan_id requis",
                "data": None,
            }
        ), 400

    try:
        scan_id_int = int(scan_id)
    except (TypeError, ValueError):
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "scan_id invalide",
                "data": None,
            }
        ), 400

    try:
        from app.services.report_service import generate_scan_report_pdf

        pdf_bytes = generate_scan_report_pdf(scan_id_int)
    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "error": "NOT_FOUND",
                "message": str(exc),
                "data": None,
            }
        ), 404
    except (RuntimeError, FPDFException) as exc:
        logger.error("PDF generation failed for scan_id=%s: %s", scan_id_int, exc)
        return jsonify(
            {
                "success": False,
                "error": "PDF_GENERATION_ERROR",
                "message": str(exc),
                "data": None,
            }
        ), 500

    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="okazcar-rapport-{scan_id_int}.pdf"'
    )
    return response
