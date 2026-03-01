"""Route API pour les prix du marche crowdsources."""

import logging
from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func

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
    normalize_market_text,
    store_market_prices,
)

FRESHNESS_DAYS = 7

logger = logging.getLogger(__name__)


_EXCLUDED_CATEGORIES = frozenset({"motos", "equipement_moto", "caravaning", "nautisme"})

# Modeles generiques LBC : pas un vrai modele, melange de vehicules differents
_GENERIC_MODELS = frozenset({"autres", "autre", "other", "divers"})


def _lookup_site_tokens(make: str, model: str) -> dict:
    """Retourne les tokens LBC et slugs AS24 stockes pour un vehicule (ou dict vide)."""
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    result = {}
    if vehicle:
        if vehicle.site_brand_token:
            result["site_brand_token"] = vehicle.site_brand_token
        if vehicle.site_model_token:
            result["site_model_token"] = vehicle.site_model_token
        if vehicle.as24_slug_make:
            result["as24_slug_make"] = vehicle.as24_slug_make
        if vehicle.as24_slug_model:
            result["as24_slug_model"] = vehicle.as24_slug_model
    return result


def _pick_and_serialize_bonus(
    site: str = "lbc", country: str = "FR", tld: str = "", max_jobs: int = 3
) -> list[dict]:
    """Pick pending jobs from the queue and serialize them for the API response."""
    if site == "as24":
        from app.services.collection_job_as24_service import pick_bonus_jobs_as24

        picked = pick_bonus_jobs_as24(country=country, tld=tld, max_jobs=max_jobs)
        result = []
        for j in picked:
            result.append(
                {
                    "make": j.make,
                    "model": j.model,
                    "year": j.year,
                    "region": j.region,
                    "fuel": j.fuel,
                    "gearbox": j.gearbox,
                    "hp_range": j.hp_range,
                    "country": j.country,
                    "tld": j.tld,
                    "slug_make": j.slug_make,
                    "slug_model": j.slug_model,
                    "search_strategy": j.search_strategy,
                    "currency": j.currency,
                    "job_id": j.id,
                }
            )
        return result

    # LBC (default)
    picked = pick_bonus_jobs(max_jobs=max_jobs)
    result = []
    for j in picked:
        entry = {
            "make": j.make,
            "model": j.model,
            "year": j.year,
            "region": j.region,
            "fuel": j.fuel,
            "gearbox": j.gearbox,
            "hp_range": j.hp_range,
            "country": j.country or "FR",
            "job_id": j.id,
        }
        tokens = _lookup_site_tokens(j.make, j.model)
        entry.update(tokens)
        result.append(entry)
    return result


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
    # Label optionnel pour lisibilite UI (pas utilise cote backend)
    label: str | None = Field(default=None, max_length=100)


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
    # Tokens LBC auto-appris depuis le DOM (accents corrects pour les URLs de recherche)
    site_brand_token: str | None = Field(default=None, max_length=120)
    site_model_token: str | None = Field(default=None, max_length=200)
    # Slugs AS24 auto-appris depuis les URLs de recherche reelles
    as24_slug_make: str | None = Field(default=None, max_length=120)
    as24_slug_model: str | None = Field(default=None, max_length=200)
    # Code pays ISO 2 lettres (FR, CH, DE, AT, IT, BE, NL, ES). Default FR.
    country: str | None = Field(default=None, max_length=5)


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
            country=req.country,
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

    # Auto-apprendre les tokens LBC depuis le DOM de l'extension.
    # Ces tokens contiennent les accents corrects (ex: "BMW_Série 3")
    # et sont necessaires pour construire les URLs de recherche LBC.
    if req.site_brand_token or req.site_model_token:
        _persist_site_tokens(req.make, req.model, req.site_brand_token, req.site_model_token)

    # Auto-apprentissage AS24 : slugs canoniques vus dans les URLs de recherche.
    if req.as24_slug_make or req.as24_slug_model:
        _persist_as24_slugs(req.make, req.model, req.as24_slug_make, req.as24_slug_model)

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


def _persist_site_tokens(
    make: str, model: str, brand_token: str | None, model_token: str | None
) -> None:
    """Persiste les tokens LBC sur le Vehicle correspondant.

    Les tokens proviennent du DOM de l'annonce LBC (lien "Voir d'autres annonces").
    Ils contiennent les accents corrects (ex: "BMW_Série 3") indispensables
    pour construire des URLs de recherche fonctionnelles.

    Ne met a jour que si le vehicule existe dans le referentiel.
    """
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    if not vehicle:
        return

    updated = False
    if brand_token and vehicle.site_brand_token != brand_token:
        vehicle.site_brand_token = brand_token
        updated = True
    if model_token and vehicle.site_model_token != model_token:
        vehicle.site_model_token = model_token
        updated = True

    if updated:
        db.session.commit()
        logger.info(
            "Auto-learned LBC tokens for %s %s: brand=%s model=%s",
            make,
            model,
            brand_token,
            model_token,
        )


def _persist_as24_slugs(
    make: str, model: str, slug_make: str | None, slug_model: str | None
) -> None:
    """Persiste les slugs AS24 canoniques sur le Vehicle correspondant."""
    from app.services.vehicle_lookup import find_vehicle

    vehicle = find_vehicle(make, model)
    if not vehicle:
        return

    updated = False
    if slug_make and vehicle.as24_slug_make != slug_make:
        vehicle.as24_slug_make = slug_make
        updated = True
    if slug_model and vehicle.as24_slug_model != slug_model:
        vehicle.as24_slug_model = slug_model
        updated = True

    if updated:
        db.session.commit()
        logger.info(
            "Auto-learned AS24 slugs for %s %s: make=%s model=%s",
            make,
            model,
            slug_make,
            slug_model,
        )


@api_bp.route("/market-prices/job-done", methods=["POST"])
@limiter.limit("60/minute")
def mark_job_complete():
    """Callback de l'extension pour signaler qu'un job de collecte est termine.

    Body JSON :
        { job_id: int, success: bool }
    """
    from app.services.collection_job_service import mark_job_done

    data = request.get_json(silent=True)
    if not data or "job_id" not in data:
        return jsonify(
            {
                "success": False,
                "error": "MISSING_JOB_ID",
                "message": "Le champ job_id est requis.",
                "data": None,
            }
        ), 400

    job_id = data["job_id"]
    if not isinstance(job_id, int):
        return jsonify(
            {
                "success": False,
                "error": "INVALID_JOB_ID",
                "message": "Le champ job_id doit etre un entier.",
                "data": None,
            }
        ), 400

    success = data.get("success", True)

    try:
        mark_job_done(job_id, success=success)
    except (ValueError, TypeError) as exc:
        return jsonify(
            {
                "success": False,
                "error": "INVALID_JOB",
                "message": str(exc),
                "data": None,
            }
        ), 404

    return jsonify(
        {
            "success": True,
            "error": None,
            "message": None,
            "data": {"job_id": job_id, "status": "done" if success else "failed"},
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
    country = request.args.get("country") or "FR"
    site = request.args.get("site", "lbc")  # "lbc" | "as24"
    tld = request.args.get("tld", "")

    if not all([make, model, year, region]):
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    # Ne pas collecter de prix pour les modeles generiques
    if model and model.strip().lower() in _GENERIC_MODELS:
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    if not (1990 <= year <= 2030):
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    # Canonicaliser make/model pour les comparaisons DB (meme aliases que store/get).
    # IMPORTANT: on conserve make/model bruts pour la reponse API vers l'extension,
    # afin de ne pas casser la construction d'URL cote navigateur.
    from app.services.vehicle_lookup import display_brand, display_model

    lookup_make = display_brand(make)
    lookup_model = display_model(model)

    # Expand collection jobs pour ce vehicule (dedup gere les repetitions)
    expand_collection_jobs(
        make=make,
        model=model,
        year=year,
        region=region,
        fuel=fuel,
        gearbox=gearbox,
        hp_range=hp_range,
        country=country,
    )

    # Comparaisons en naive UTC (SQLite ne conserve pas le tzinfo)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=FRESHNESS_DAYS)

    # 1. Le vehicule courant a-t-il besoin d'un refresh ?
    # Priorite absolue au vehicule scanne : si l'extension fournit fuel/hp_range,
    # on exige cette variante exacte (sinon un record generique frais pourrait
    # masquer l'absence de donnees reellement utiles pour L4).
    country_upper = country.upper().strip()
    current_filters = [
        market_text_key_expr(MarketPrice.make) == market_text_key(lookup_make),
        market_text_key_expr(MarketPrice.model) == market_text_key(lookup_model),
        MarketPrice.year == year,
        market_text_key_expr(MarketPrice.region) == market_text_key(region),
        func.coalesce(MarketPrice.country, "FR") == country_upper,
    ]
    if fuel:
        fuel_key = normalize_market_text(fuel).lower()
        current_filters.append(func.lower(MarketPrice.fuel) == fuel_key)
    if hp_range:
        current_filters.append(func.lower(MarketPrice.hp_range) == hp_range.lower())

    current = MarketPrice.query.filter(*current_filters).first()

    if not current or current.collected_at < cutoff:
        bonus = _pick_and_serialize_bonus(site=site, country=country_upper, tld=tld)
        tokens = _lookup_site_tokens(make, model)
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
                    "vehicle": {
                        "make": make,
                        "model": model,
                        "year": year,
                        **tokens,
                    },
                    "region": region,
                    "country": country_upper,
                    "bonus_jobs": bonus,
                },
            }
        )

    # 2. Trouver un autre vehicule qui a besoin de mise a jour dans cette region
    # Sous-requete : dernier collected_at par (make, model) dans cette region
    from sqlalchemy import case

    latest_mp = (
        db.session.query(
            func.lower(MarketPrice.make).label("mp_make"),
            func.lower(MarketPrice.model).label("mp_model"),
            func.max(MarketPrice.collected_at).label("latest_at"),
        )
        .filter(
            market_text_key_expr(MarketPrice.region) == market_text_key(region),
            func.coalesce(MarketPrice.country, "FR") == country_upper,
        )
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
        bonus = _pick_and_serialize_bonus(site=site, country=country_upper, tld=tld)
        tokens = _lookup_site_tokens(best_candidate[0], best_candidate[1])
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
                        **tokens,
                    },
                    "region": region,
                    "country": country_upper,
                    "bonus_jobs": bonus,
                },
            }
        )

    # 3. Tout est a jour dans cette region
    bonus = _pick_and_serialize_bonus(site=site, country=country_upper, tld=tld)
    logger.info("next-job: tout est a jour pour la region %s (+%d bonus)", region, len(bonus))
    return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": bonus}})


@api_bp.route("/market-prices/failed-search", methods=["POST"])
@limiter.limit("30/minute")
def report_failed_search():
    """Recoit un rapport de recherche echouee (0 annonces sur toutes les strategies).

    Permet d'identifier les URLs mal construites (tokens manquants, accents, etc.)
    et d'apprendre rapidement des erreurs.

    Body JSON :
        { make, model, year, region, search_log: [...], brand_token_used, model_token_used, token_source }
    """
    import json as json_mod

    from app.models.failed_search import FailedSearch

    data = request.get_json(silent=True)
    if not data:
        return jsonify(
            {"success": False, "error": "VALIDATION_ERROR", "message": "JSON requis.", "data": None}
        ), 400

    make = data.get("make", "")
    model_name = data.get("model", "")
    year = data.get("year")
    region = data.get("region", "")

    if not make or not model_name or not region:
        return jsonify(
            {
                "success": False,
                "error": "MISSING_FIELDS",
                "message": "make, model, region requis.",
                "data": None,
            }
        ), 400

    search_log = data.get("search_log")
    total_ads = sum(s.get("ads_found", 0) for s in search_log) if search_log else 0

    # Compter les occurrences precedentes pour auto-calculer la severite
    from sqlalchemy import func as sqla_func

    occurrence_count = FailedSearch.query.filter(
        sqla_func.lower(FailedSearch.make) == make.strip().lower(),
        sqla_func.lower(FailedSearch.model) == model_name.strip().lower(),
    ).count()

    # Compat LBC + AS24:
    # - LBC legacy: brand_token_used/model_token_used/token_source
    # - AS24: slug_make_used/slug_model_used/slug_source + site/tld
    site = (data.get("site") or "").strip().lower()
    brand_token_used = data.get("brand_token_used") or data.get("slug_make_used")
    model_token_used = data.get("model_token_used") or data.get("slug_model_used")
    token_source = data.get("token_source") or data.get("slug_source")

    if not token_source and site == "as24":
        token_source = "as24_generated_url"

    severity_source = token_source
    if token_source and "fallback" in token_source.lower():
        severity_source = "fallback"

    severity = FailedSearch.compute_severity(occurrence_count + 1, severity_source)

    entry = FailedSearch(
        make=make,
        model=model_name,
        year=int(year) if year else 0,
        region=region,
        fuel=data.get("fuel"),
        hp_range=data.get("hp_range"),
        country=data.get("country", "FR"),
        brand_token_used=brand_token_used,
        model_token_used=model_token_used,
        token_source=token_source,
        search_log=json_mod.dumps(search_log) if search_log else None,
        total_ads_found=total_ads,
        severity=severity,
    )
    db.session.add(entry)
    db.session.commit()

    logger.warning(
        "Failed search logged: %s %s %d %s (token_source=%s, total_ads=%d, severity=%s)",
        make,
        model_name,
        entry.year,
        region,
        token_source,
        total_ads,
        severity,
    )

    return jsonify(
        {
            "success": True,
            "error": None,
            "message": None,
            "data": {"id": entry.id, "total_ads_found": total_ads},
        }
    )
