"""Definitions des routes API."""

import logging
import traceback

import httpx
from flask import jsonify, request
from pydantic import ValidationError as PydanticValidationError

from app.api import api_bp
from app.errors import ExtractionError
from app.filters.engine import FilterEngine
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.filter_result import FilterResultSchema
from app.services.extraction import extract_ad_data
from app.services.scoring import calculate_score

logger = logging.getLogger(__name__)


@api_bp.route("/health", methods=["GET"])
def health():
    """Point de controle de sante de l'API."""
    return jsonify({"success": True, "data": {"status": "ok"}})


@api_bp.route("/analyze", methods=["POST"])
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
        return jsonify({
            "success": False,
            "error": "INTERNAL_ERROR",
            "message": "Erreur interne du serveur.",
            "data": None,
        }), 500


def _do_analyze():
    """Logique interne de l'endpoint analyze, encapsulee pour le catch-all."""
    # Validation de la requete
    json_data = request.get_json(silent=True)
    if not json_data:
        return jsonify({
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": "Le corps de la requete doit etre du JSON valide.",
            "data": None,
        }), 400

    try:
        req = AnalyzeRequest.model_validate(json_data)
    except PydanticValidationError as exc:
        logger.warning("Validation error: %s", exc)
        return jsonify({
            "success": False,
            "error": "VALIDATION_ERROR",
            "message": "Donnees invalides. Verifiez le format du payload.",
            "data": None,
        }), 400

    # Extraction des donnees de l'annonce
    try:
        ad_data = extract_ad_data(req.next_data)
    except ExtractionError as exc:
        logger.warning("Extraction failed: %s", exc)
        return jsonify({
            "success": False,
            "error": "EXTRACTION_ERROR",
            "message": "Impossible d'extraire les donnees de cette annonce.",
            "data": None,
        }), 422

    # Execution des filtres
    engine = _build_engine()
    try:
        filter_results = engine.run_all(ad_data)
    except (KeyError, ValueError, AttributeError, TypeError, OSError) as exc:
        logger.error("Engine crash: %s: %s", type(exc).__name__, exc)
        return jsonify({
            "success": False,
            "error": "ENGINE_ERROR",
            "message": "Erreur lors de l'analyse. Reessayez.",
            "data": None,
        }), 500

    # Calcul du score
    score, is_partial = calculate_score(filter_results)

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
    response = AnalyzeResponse(
        score=score,
        is_partial=is_partial,
        filters=filters_out,
        vehicle={
            "make": ad_data.get("make"),
            "model": ad_data.get("model"),
            "year": ad_data.get("year_model"),
            "price": ad_data.get("price_eur"),
            "mileage": ad_data.get("mileage_km"),
        },
    )

    return jsonify({
        "success": True,
        "error": None,
        "message": None,
        "data": response.model_dump(),
    })


def _build_engine() -> FilterEngine:
    """Construit et retourne un FilterEngine avec les 9 filtres enregistres."""
    from app.filters.l1_extraction import L1ExtractionFilter
    from app.filters.l2_referentiel import L2ReferentielFilter
    from app.filters.l3_coherence import L3CoherenceFilter
    from app.filters.l4_price import L4PriceFilter
    from app.filters.l5_visual import L5VisualFilter
    from app.filters.l6_phone import L6PhoneFilter
    from app.filters.l7_siret import L7SiretFilter
    from app.filters.l8_reputation import L8ImportDetectionFilter
    from app.filters.l9_score import L9GlobalAssessmentFilter

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
    return engine
