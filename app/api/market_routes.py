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
from app.services.collection_job_service import expand_collection_jobs, pick_bonus_jobs
from app.services.market_service import (
    MIN_SAMPLE_ABSOLUTE,
    get_min_sample_count,
    market_text_key,
    market_text_key_expr,
    store_market_prices,
)

FRESHNESS_DAYS = 7

logger = logging.getLogger(__name__)


_EXCLUDED_CATEGORIES = frozenset({"motos", "equipement_moto", "caravaning", "nautisme"})

# Modeles generiques LBC : pas un vrai modele, melange de vehicules differents
_GENERIC_MODELS = frozenset({"autres", "autre", "other", "divers"})

# Les 13 regions francaises post-reforme 2016
POST_2016_REGIONS = [
    "Île-de-France",
    "Auvergne-Rhône-Alpes",
    "Provence-Alpes-Côte d'Azur",
    "Occitanie",
    "Nouvelle-Aquitaine",
    "Hauts-de-France",
    "Grand Est",
    "Bretagne",
    "Pays de la Loire",
    "Normandie",
    "Bourgogne-Franche-Comté",
    "Centre-Val de Loire",
    "Corse",
]


def _compute_bonus_jobs(
    make: str,
    model: str,
    year: int,
    fuel: str | None,
    exclude_region: str,
    max_bonus: int = 2,
) -> list[dict]:
    """Determine les bonus jobs intelligents pour le meme modele.

    Priorite :
    1. Regions manquantes (aucune donnee MarketPrice)
    2. Regions avec donnees > FRESHNESS_DAYS (refresh)
    3. [] si tout est frais
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=FRESHNESS_DAYS)

    query = MarketPrice.query.filter(
        market_text_key_expr(MarketPrice.make) == market_text_key(make),
        market_text_key_expr(MarketPrice.model) == market_text_key(model),
        MarketPrice.year == year,
    )
    if fuel:
        query = query.filter(db.func.lower(db.func.coalesce(MarketPrice.fuel, "")) == fuel.lower())

    existing = query.all()

    covered: dict[str, MarketPrice] = {}
    for mp in existing:
        key = market_text_key(mp.region)
        if key not in covered or mp.collected_at > covered[key].collected_at:
            covered[key] = mp

    missing_regions: list[str] = []
    stale_regions: list[tuple[str, datetime]] = []
    for r in POST_2016_REGIONS:
        if market_text_key(r) == market_text_key(exclude_region):
            continue
        entry = covered.get(market_text_key(r))
        if entry is None:
            missing_regions.append(r)
        elif entry.collected_at < cutoff:
            stale_regions.append((r, entry.collected_at))

    stale_regions.sort(key=lambda x: x[1])

    bonus_jobs: list[dict] = []
    for r in missing_regions:
        if len(bonus_jobs) >= max_bonus:
            break
        bonus_jobs.append({"make": make, "model": model, "year": year, "region": r})
    for r, _ in stale_regions:
        if len(bonus_jobs) >= max_bonus:
            break
        bonus_jobs.append({"make": make, "model": model, "year": year, "region": r})

    return bonus_jobs


class PriceDetail(BaseModel):
    """Detail d'un prix individuel collecte (annonce LBC)."""

    price: int
    year: int | None = None
    km: int | None = None
    fuel: str | None = None


class SearchStep(BaseModel):
    """Un pas de la cascade de recherche argus."""

    step: int = Field(ge=1, le=10)
    precision: int = Field(ge=1, le=5)
    location_type: str = Field(max_length=20)
    year_spread: int = Field(ge=1, le=5)
    filters_applied: list[str] = Field(default_factory=list)
    ads_found: int = Field(ge=0)
    url: str = Field(max_length=500)
    was_selected: bool = False
    reason: str = Field(default="", max_length=200)


class MarketPricesRequest(BaseModel):
    """Schema de validation pour les prix du marche envoyes par l'extension."""

    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1990, le=2030)
    region: str = Field(min_length=1, max_length=80)
    prices: list[int] = Field(min_length=MIN_SAMPLE_ABSOLUTE)
    price_details: list[PriceDetail] | None = None
    category: str | None = Field(default=None, max_length=40)
    fuel: str | None = Field(default=None, max_length=30)
    precision: int | None = Field(default=None, ge=1, le=5)
    search_log: list[SearchStep] | None = None
    hp_range: str | None = Field(default=None, max_length=20)
    fiscal_hp: int | None = Field(default=None, ge=1, le=100)
    lbc_estimate_low: int | None = Field(default=None, ge=0)
    lbc_estimate_high: int | None = Field(default=None, ge=0)


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

    # Seuil dynamique selon la puissance du vehicule (niche = moins d'annonces)
    min_required = get_min_sample_count(req.make, req.model)
    if len(valid_prices) < min_required:
        return jsonify(
            {
                "success": False,
                "error": "INSUFFICIENT_DATA",
                "message": f"Pas assez de prix valides ({len(valid_prices)}/{min_required}).",
                "data": {"min_required": min_required, "received": len(valid_prices)},
            }
        ), 400

    # Convertir price_details et search_log en liste de dicts pour le stockage JSON
    raw_details = None
    if req.price_details:
        raw_details = [d.model_dump() for d in req.price_details]
    raw_search_log = [s.model_dump() for s in req.search_log] if req.search_log else None

    try:
        mp = store_market_prices(
            make=req.make,
            model=req.model,
            year=req.year,
            region=req.region,
            prices=valid_prices,
            fuel=req.fuel,
            precision=req.precision,
            price_details=raw_details,
            search_log=raw_search_log,
            hp_range=req.hp_range,
            fiscal_hp=req.fiscal_hp,
            lbc_estimate_low=req.lbc_estimate_low,
            lbc_estimate_high=req.lbc_estimate_high,
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
    fuel = request.args.get("fuel")
    gearbox = request.args.get("gearbox")
    hp_range = request.args.get("hp_range")

    if not all([make, model, region]):
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    # Ne pas collecter de prix pour les modeles generiques
    if model and model.strip().lower() in _GENERIC_MODELS:
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    if year is not None and not (1990 <= year <= 2030):
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    # Expand collection jobs pour ce vehicule (dedup gere les repetitions)
    expand_collection_jobs(
        make=make,
        model=model,
        year=year,
        region=region,
        fuel=fuel,
        gearbox=gearbox,
        hp_range=hp_range,
    )

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
        picked = pick_bonus_jobs(max_jobs=3)
        bonus = [
            {
                "make": j.make,
                "model": j.model,
                "year": j.year,
                "region": j.region,
                "fuel": j.fuel,
                "gearbox": j.gearbox,
                "hp_range": j.hp_range,
                "job_id": j.id,
            }
            for j in picked
        ]
        logger.info(
            "next-job: vehicule courant %s %s %s a collecter (+%d bonus)",
            make,
            model,
            region,
            len(bonus),
        )
        return jsonify(
            {
                "success": True,
                "data": {
                    "collect": True,
                    "vehicle": {"make": make, "model": model, "year": year},
                    "region": region,
                    "bonus_jobs": bonus,
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
    # Exclure les modeles generiques ("Autres") qui ne sont pas de vrais modeles
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
        .filter(
            Vehicle.year_start.isnot(None),
            ~func.lower(Vehicle.model).in_(list(_GENERIC_MODELS)),
        )
        .order_by(
            # Priorite 1 : jamais collecte (NULL) d'abord
            case((latest_mp.c.latest_at.is_(None), 0), else_=1),
            # Priorite 2 : vehicules partial (enrichment en cours) avant complete
            case((Vehicle.enrichment_status == "partial", 0), else_=1),
            # Priorite 3 : le plus ancien
            latest_mp.c.latest_at.asc(),
            Vehicle.id.asc(),
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
        picked = pick_bonus_jobs(max_jobs=3)
        bonus = [
            {
                "make": j.make,
                "model": j.model,
                "year": j.year,
                "region": j.region,
                "fuel": j.fuel,
                "gearbox": j.gearbox,
                "hp_range": j.hp_range,
                "job_id": j.id,
            }
            for j in picked
        ]
        logger.info(
            "next-job: redirection vers %s %s pour region %s (+%d bonus)",
            best_candidate[0],
            best_candidate[1],
            region,
            len(bonus),
        )
        return jsonify(
            {
                "success": True,
                "data": {
                    "collect": True,
                    "redirect": True,
                    "vehicle": {
                        "make": best_candidate[0],
                        "model": best_candidate[1],
                        "year": best_candidate[2],
                    },
                    "region": region,
                    "bonus_jobs": bonus,
                },
            }
        )

    # 3. Tout est a jour dans cette region
    picked = pick_bonus_jobs(max_jobs=3)
    bonus = [
        {
            "make": j.make,
            "model": j.model,
            "year": j.year,
            "region": j.region,
            "fuel": j.fuel,
            "gearbox": j.gearbox,
            "hp_range": j.hp_range,
            "job_id": j.id,
        }
        for j in picked
    ]
    logger.info("next-job: tout est a jour pour la region %s (+%d bonus)", region, len(bonus))
    return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": bonus}})
