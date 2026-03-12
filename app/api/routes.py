"""Definitions des routes API."""

import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Any

import httpx
from flask import current_app, jsonify, request
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
    # -- Catch-all pour logger toute erreur non prevue --
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
    """Logique interne de l'endpoint analyze, encapsulee pour le catch-all."""
    # Validation de la requete
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

    # Validation: au moins un des deux payloads requis
    if req.next_data is None and req.ad_data is None:
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "next_data ou ad_data requis.",
                "data": None,
            }
        ), 400

    # Extraction des donnees de l'annonce
    if req.ad_data is not None:
        # Pre-normalized path (AutoScout24, La Centrale, etc.)
        ad_data = req.ad_data
        if req.source:
            ad_data["source"] = req.source
    else:
        # Legacy LBC path
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

    # Canonicaliser make/model pour toutes les sources (AS24, LBC, ...)
    # afin d'aligner l'affichage, L2 référentiel et les recherches associées.
    try:
        from app.services.vehicle_lookup import display_brand, display_model

        if ad_data.get("make"):
            ad_data["make"] = display_brand(str(ad_data["make"]))
        if ad_data.get("model"):
            ad_data["model"] = display_model(str(ad_data["model"]))
    except Exception:
        logger.debug("Make/model canonicalization skipped", exc_info=True)

    # Detection du pays depuis le TLD de l'URL pour les filtres (L6, L7)
    ad_data["country"] = _detect_country(req.url or "", req.source)

    # Conversion de devise : si le prix est en CHF (ou autre), convertir en EUR
    # pour que les filtres L4/L5 comparent des pommes avec des pommes.
    # On preserve le prix original et la devise pour l'affichage.
    original_currency = ad_data.get("currency")
    original_price = ad_data.get("price_eur")
    price_eur, was_converted = convert_to_eur(original_price, original_currency)
    if was_converted:
        ad_data["price_eur"] = price_eur
        ad_data["price_original"] = original_price
        ad_data["currency_original"] = original_currency

    # Calcul days_online si absent mais publication_date present
    # (sources pre-normalisees comme AS24 envoient la date mais pas le calcul)
    if ad_data.get("days_online") is None and ad_data.get("publication_date"):
        try:
            pub_str = ad_data["publication_date"]
            pub_date = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
            ad_data["days_online"] = (datetime.now(timezone.utc) - pub_date).days
        except (ValueError, TypeError):
            pass  # format de date non reconnu, L10 fera skip

    # Detection non-voiture : categorie URL + presence marque/modele
    # Note : _extract_url_category ne fonctionne que pour les URLs LBC (/ad/<cat>/).
    # Pour les sources non-LBC (AutoScout24, etc.), on skip la detection par URL
    # car leur format d'URL ne contient pas de categorie exploitable.
    url = req.url or ""
    is_lbc_source = req.source is None or req.source == "leboncoin"
    url_category = _extract_url_category(url) if is_lbc_source else None
    has_vehicle_attrs = bool(ad_data.get("make")) and bool(ad_data.get("model"))

    # Motos : categorie reconnue mais pas encore supportee (LBC uniquement)
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

    # Autres categories non-voiture sans attributs vehicule (LBC uniquement)
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

    # Execution des filtres
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

    # Calcul du score
    score, is_partial = calculate_score(filter_results)

    # Persistence (best-effort : ne casse jamais la reponse API)
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

    # Enrichir les motorisations observees depuis ce scan individuel (best-effort)
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

    # Construction de la reponse
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
    # Recherche de la video featured pour ce vehicule
    featured_video = None
    make = ad_data.get("make")
    model = ad_data.get("model")
    if make and model:
        try:
            from app.services.youtube_service import get_featured_video

            featured_video = get_featured_video(make, model)
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Featured video lookup failed: %s", exc)

    # Recherche des dimensions pneus pour ce vehicule
    tire_sizes_data = None
    year = ad_data.get("year_model")
    if make and model and year:
        try:
            from app.services.tire_service import get_tire_sizes

            tire_sizes_data = get_tire_sizes(make, model, year)
        except (OSError, ValueError, TypeError) as exc:
            logger.debug("Tire sizes lookup failed: %s", exc)

    # --- Background fill : remplir un AUTRE vehicule via Wheel-Size ---
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

    # Fiabilite moteur (best-effort)
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
                    for s in specs:
                        ft = (s.fuel_type or "").lower()
                        if fuel_raw and (fuel_raw in ft or ft in fuel_raw):
                            matched_spec = s
                            break
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
    # Inclure le prix original si une conversion a ete appliquee
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
    """Construit et retourne un FilterEngine avec les 10 filtres enregistres."""
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
    return engine


# Pattern : /ad/<category>/<id> ou /ad/<category>/
_URL_CATEGORY_RE = re.compile(r"/ad/([a-z_]+)/")


def _extract_url_category(url: str) -> str | None:
    """Extrait la categorie LeBonCoin depuis l'URL (ex. 'voitures', 'equipement_auto')."""
    m = _URL_CATEGORY_RE.search(url)
    return m.group(1) if m else None


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
    """Detecte le pays depuis le TLD de l'URL ou la source. Defaut: FR."""
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
    """Genere un brouillon d'email vendeur via Gemini."""
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
