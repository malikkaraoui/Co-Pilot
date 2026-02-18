"""Route API pour les prix du marche crowdsources."""

import logging
from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.api import api_bp
from app.extensions import db, limiter
from app.models.market_price import MarketPrice
from app.models.vehicle import Vehicle
from app.services.market_service import (
    MIN_SAMPLE_COUNT,
    market_text_key,
    market_text_key_expr,
    store_market_prices,
)

FRESHNESS_DAYS = 7

logger = logging.getLogger(__name__)


_EXCLUDED_CATEGORIES = frozenset(
    {"motos", "equipement_moto", "caravaning", "nautisme", "utilitaires"}
)

# Modeles generiques LBC : pas un vrai modele, melange de vehicules differents
_GENERIC_MODELS = frozenset({"autres", "autre", "other", "divers"})


class MarketPricesRequest(BaseModel):
    """Schema de validation pour les prix du marche envoyes par l'extension."""

    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1990, le=2030)
    region: str = Field(min_length=1, max_length=80)
    prices: list[int] = Field(min_length=MIN_SAMPLE_COUNT)
    category: str | None = Field(default=None, max_length=40)
    fuel: str | None = Field(default=None, max_length=30)


@api_bp.route("/market-prices", methods=["POST"])
@limiter.limit("20/minute")
def submit_market_prices():
    """Recoit les prix collectes par l'extension Chrome.

    Body JSON attendu :
        { make, model, year, region, prices: [int, ...] }

    Retourne :
        { success: true, data: { sample_count: N, price_median: M } }
    """
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
        req = MarketPricesRequest.model_validate(json_data)
    except PydanticValidationError as exc:
        logger.warning("Market prices validation error: %s", exc)
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "Donnees invalides. Verifiez le format du payload.",
                "data": None,
            }
        ), 400

    # Rejeter les modeles generiques ("Autres") qui melangent des vehicules differents
    if req.model.strip().lower() in _GENERIC_MODELS:
        logger.info("Market prices rejected: generic model '%s' (%s)", req.model, req.make)
        return jsonify(
            {
                "success": False,
                "error": "GENERIC_MODEL",
                "message": "Le modèle générique n'est pas accepté pour les prix du marché.",
                "data": None,
            }
        ), 400

    # Rejeter les categories non-voiture (motos, etc.)
    if req.category and req.category in _EXCLUDED_CATEGORIES:
        logger.info(
            "Market prices rejected: category=%s (%s %s)", req.category, req.make, req.model
        )
        return jsonify(
            {
                "success": False,
                "error": "EXCLUDED_CATEGORY",
                "message": f"La categorie '{req.category}' n'est pas prise en charge.",
                "data": None,
            }
        ), 400

    # Filtrer les prix aberrants (< 500 EUR probablement des erreurs)
    valid_prices = [p for p in req.prices if p >= 500]
    if len(valid_prices) < MIN_SAMPLE_COUNT:
        return jsonify(
            {
                "success": False,
                "error": "INSUFFICIENT_DATA",
                "message": f"Pas assez de prix valides (minimum {MIN_SAMPLE_COUNT}).",
                "data": None,
            }
        ), 400

    try:
        mp = store_market_prices(
            make=req.make,
            model=req.model,
            year=req.year,
            region=req.region,
            prices=valid_prices,
            fuel=req.fuel,
        )
    except (ValueError, TypeError, OSError) as exc:
        logger.error("Failed to store market prices: %s", exc)
        return jsonify(
            {
                "success": False,
                "error": "STORAGE_ERROR",
                "message": "Erreur lors du stockage des prix.",
                "data": None,
            }
        ), 500

    return jsonify(
        {
            "success": True,
            "error": None,
            "message": None,
            "data": {
                "sample_count": mp.sample_count,
                "price_median": mp.price_median,
            },
        }
    )


@api_bp.route("/market-prices/next-job", methods=["GET"])
@limiter.limit("60/minute")
def next_market_job():
    """Indique a l'extension quel vehicule collecter pour l'argus maison.

    Si le vehicule courant a besoin d'un rafraichissement (> 7 jours ou absent),
    on le retourne. Sinon, on cherche un autre vehicule du referentiel qui a
    besoin de mise a jour dans la meme region.

    Query params :
        make, model, year (int), region

    Retourne :
        { success: true, data: { collect: bool, vehicle?: {make, model, year}, region?: str } }
    """
    make = request.args.get("make")
    model = request.args.get("model")
    year = request.args.get("year", type=int)
    region = request.args.get("region")

    if not all([make, model, region]):
        return jsonify({"success": True, "data": {"collect": False}})

    # Ne pas collecter de prix pour les modeles generiques
    if model and model.strip().lower() in _GENERIC_MODELS:
        return jsonify({"success": True, "data": {"collect": False}})

    if year is not None and not (1990 <= year <= 2030):
        return jsonify({"success": True, "data": {"collect": False}})

    # Comparaisons en naive UTC (SQLite ne conserve pas le tzinfo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=FRESHNESS_DAYS)

    # 1. Le vehicule courant a-t-il besoin d'un refresh ?
    current = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
    ).first()

    if not current or current.collected_at < cutoff:
        logger.info("next-job: vehicule courant %s %s %s a collecter", make, model, region)
        return jsonify(
            {
                "success": True,
                "data": {
                    "collect": True,
                    "vehicle": {"make": make, "model": model, "year": year},
                    "region": region,
                },
            }
        )

    # 2. Trouver un autre vehicule qui a besoin de mise a jour dans cette region
    # Sous-requete : dernier collected_at par (make, model) dans cette region
    from sqlalchemy import case, func

    latest_mp = (
        db.session.query(
            func.lower(MarketPrice.make).label("mp_make"),
            func.lower(MarketPrice.model).label("mp_model"),
            func.max(MarketPrice.collected_at).label("latest_at"),
        )
        .filter(market_text_key_expr(MarketPrice.region) == market_text_key(region))
        .group_by(func.lower(MarketPrice.make), func.lower(MarketPrice.model))
        .subquery()
    )

    # LEFT JOIN Vehicle avec la sous-requete pour trouver les vehicules stale/absents
    candidates = (
        db.session.query(
            Vehicle.brand,
            Vehicle.model,
            Vehicle.year_start,
            Vehicle.year_end,
            latest_mp.c.latest_at,
        )
        .outerjoin(
            latest_mp,
            db.and_(
                func.lower(Vehicle.brand) == latest_mp.c.mp_make,
                func.lower(Vehicle.model) == latest_mp.c.mp_model,
            ),
        )
        .filter(Vehicle.year_start.isnot(None))
        .order_by(
            # Priorite : jamais collecte (NULL) d'abord, puis le plus ancien
            case((latest_mp.c.latest_at.is_(None), 0), else_=1),
            latest_mp.c.latest_at.asc(),
        )
        .limit(1)
        .all()
    )

    best_candidate = None
    for c in candidates:
        # Verifier que le candidat est stale ou absent
        if c.latest_at is None or c.latest_at < cutoff:
            mid_year = (c.year_start + (c.year_end or c.year_start)) // 2
            best_candidate = (c.brand, c.model, mid_year)

    if best_candidate:
        logger.info(
            "next-job: redirection vers %s %s pour region %s",
            best_candidate[0],
            best_candidate[1],
            region,
        )
        return jsonify(
            {
                "success": True,
                "data": {
                    "collect": True,
                    "vehicle": {
                        "make": best_candidate[0],
                        "model": best_candidate[1],
                        "year": best_candidate[2],
                    },
                    "region": region,
                },
            }
        )

    # 3. Tout est a jour dans cette region
    logger.info("next-job: tout est a jour pour la region %s", region)
    return jsonify({"success": True, "data": {"collect": False}})
