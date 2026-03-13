"""Route API pour les prix du marche crowdsources.

Ce module gere tout le cycle de collecte de l'argus maison :
- /market-prices : reception des prix collectes par l'extension
- /market-prices/next-job : indique a l'extension quel vehicule collecter ensuite
- /market-prices/job-done : callback quand un job de collecte est termine
- /market-prices/failed-search : rapport de recherche echouee (0 resultats)

Le systeme fonctionne en crowdsourcing : chaque extension Chrome active
collecte des prix sur LBC/AS24/La Centrale et les remonte ici.
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import jsonify, request
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

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

# Duree de fraicheur d'un prix marche avant qu'il soit considere "stale"
FRESHNESS_DAYS = 7

logger = logging.getLogger(__name__)


# Categories LBC qu'on refuse pour eviter de polluer l'argus avec des non-voitures
_EXCLUDED_CATEGORIES = frozenset({"motos", "equipement_moto", "caravaning", "nautisme"})

# Modeles generiques LBC ("Autres", "Autre") : pas un vrai modele,
# c'est un fourre-tout qui melange des vehicules differents → on refuse.
_GENERIC_MODELS = frozenset({"autres", "autre", "other", "divers"})

# Classement de severite des diagnostics La Centrale :
# plus c'est haut, plus c'est bloquant (anti-bot > parser_no_match > true_zero)
_LACENTRALE_DIAGNOSTIC_PRIORITY = {
    "anti_bot_403": 6,
    "anti_bot_page": 5,
    "iframe_blocked": 4,
    "parser_no_match": 3,
    "html_without_cards": 2,
    "true_zero_results": 1,
}


def _lookup_site_tokens(make: str, model: str) -> dict:
    """Retourne les tokens LBC et slugs AS24 stockes pour un vehicule (ou dict vide).

    Ces tokens sont auto-appris depuis le DOM des annonces et servent
    a construire les URLs de recherche avec les bons accents/slugs.
    """
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
    """Pioche des jobs bonus dans la file d'attente et les serialise pour la reponse API.

    Les jobs bonus sont des collectes "piggyback" : pendant que l'extension
    est en train de collecter pour le vehicule courant, on lui donne 1-3
    vehicules supplementaires a collecter au passage.
    """
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

    if site == "lacentrale":
        from app.services.collection_job_lc_service import pick_bonus_jobs_lc

        picked = pick_bonus_jobs_lc(max_jobs=max_jobs)
        return [
            {
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
            for j in picked
        ]

    # LBC (default) — on filtre par pays pour ne pas servir des jobs CH a une extension FR
    picked = pick_bonus_jobs(max_jobs=max_jobs, country=country)
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
        # On ajoute les tokens LBC pour que l'extension puisse construire
        # les URLs de recherche avec les bons accents
        tokens = _lookup_site_tokens(j.make, j.model)
        entry.update(tokens)
        result.append(entry)
    return result


# ── Schemas Pydantic pour la validation des payloads entrants ──


class PriceDetail(BaseModel):
    """Detail d'un prix individuel collecte (annonce LBC/AS24)."""

    price: int
    year: int | None = None
    km: int | None = None
    fuel: str | None = None
    gearbox: str | None = None
    horse_power: int | str | None = None
    seats: int | None = None


class SearchStep(BaseModel):
    """Un pas de la cascade de recherche argus.

    L'extension tente plusieurs strategies de recherche en cascade
    (par region, national, annee +/-1, etc.) et enregistre chaque etape
    pour le debug et l'optimisation des recherches.
    """

    step: int = Field(ge=1, le=15)
    precision: int = Field(ge=0, le=5)
    location_type: str = Field(max_length=20)
    year_spread: int = Field(ge=1, le=5)
    filters_applied: list[str] = Field(default_factory=list)
    ads_found: int = Field(ge=0)
    url: str = Field(max_length=500)
    was_selected: bool = False
    reason: str = Field(default="", max_length=200)
    # Label optionnel pour lisibilite UI (pas utilise cote backend)
    label: str | None = Field(default=None, max_length=100)
    diagnostic_tag: str | None = Field(default=None, max_length=40)
    fetch_mode: str | None = Field(default=None, max_length=20)
    http_status: int | None = Field(default=None, ge=0, le=599)
    body_excerpt: str | None = Field(default=None, max_length=400)
    html_title: str | None = Field(default=None, max_length=160)
    resource_sample: str | None = Field(default=None, max_length=500)
    response_bytes: int | None = Field(default=None, ge=0)
    anti_bot_detected: bool = False


class MarketPricesRequest(BaseModel):
    """Schema de validation pour les prix du marche envoyes par l'extension.

    Champs obligatoires : make, model, year, region, prices.
    Le reste est optionnel et sert a enrichir les donnees ou a ajuster
    le seuil minimum d'annonces requis.
    """

    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=1990, le=2030)
    region: str = Field(min_length=1, max_length=80)
    prices: list[int] = Field(min_length=MIN_SAMPLE_ABSOLUTE)
    price_details: list[PriceDetail] | None = None
    category: str | None = Field(default=None, max_length=40)
    fuel: str | None = Field(default=None, max_length=60)
    precision: int | None = Field(default=None, ge=0, le=5)
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
        # On extrait les 5 premiers champs en erreur pour faciliter le debug
        field_errors = [
            f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]
        ]
        return jsonify(
            {
                "success": False,
                "error": "VALIDATION_ERROR",
                "message": "; ".join(field_errors) if field_errors else "Donnees invalides.",
                "data": None,
            }
        ), 400

    # Rejeter les modeles generiques ("Autres") — ils melangent des vehicules differents
    # et fausseraient completement la mediane des prix.
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

    # Rejeter les categories non-voiture (motos, nautisme, etc.)
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

    # Filtrer les prix aberrants : en dessous de 500 EUR c'est probablement
    # une erreur de parsing ou un "prix sur demande" a 1 EUR.
    valid_prices = [p for p in req.prices if p >= 500]

    # Seuil dynamique : les vehicules de niche (>300ch) ou ultra-niche (>420ch)
    # ont des seuils plus bas car le volume d'annonces est naturellement faible.
    min_required = get_min_sample_count(req.make, req.model, country=req.country or "FR")
    if len(valid_prices) < min_required:
        return jsonify(
            {
                "success": False,
                "error": "INSUFFICIENT_DATA",
                "message": f"Pas assez de prix valides ({len(valid_prices)}/{min_required}).",
                "data": {"min_required": min_required, "received": len(valid_prices)},
            }
        ), 400

    # Serialiser les details et le search_log en dicts pour le stockage JSON
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
        logger.error("Failed to store market prices (client payload error): %s", exc)
        return jsonify(
            {
                "success": False,
                "error": "STORAGE_ERROR",
                "message": "Erreur lors du stockage des prix.",
                "data": None,
            }
        ), 500
    except SQLAlchemyError as exc:
        # DB lock/timeout/constraint — on rollback pour ne pas laisser
        # la session SQLAlchemy dans un etat invalide.
        try:
            db.session.rollback()
        except Exception:  # rollback best-effort
            pass
        logger.error("Failed to store market prices (database error): %s", exc, exc_info=True)
        return jsonify(
            {
                "success": False,
                "error": "DATABASE_ERROR",
                "message": "Erreur base de données lors du stockage des prix.",
                "data": None,
            }
        ), 503

    # Auto-apprentissage des tokens LBC depuis le DOM de l'extension.
    # Ces tokens contiennent les accents corrects (ex: "BMW_Série 3")
    # et sont indispensables pour construire les URLs de recherche LBC.
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
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.warning(
                "Failed to persist LBC tokens for %s %s",
                make,
                model,
                exc_info=True,
            )
            return
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
    """Persiste les slugs AS24 canoniques sur le Vehicle correspondant.

    Meme logique que les tokens LBC mais pour AutoScout24 : les slugs
    viennent des URLs de recherche reelles et servent a construire
    les futures URLs de collecte.
    """
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
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.warning(
                "Failed to persist AS24 slugs for %s %s",
                make,
                model,
                exc_info=True,
            )
            return
        logger.info(
            "Auto-learned AS24 slugs for %s %s: make=%s model=%s",
            make,
            model,
            slug_make,
            slug_model,
        )


def _is_lacentrale_failed_search(site: str | None, search_log: list[dict] | None) -> bool:
    """Determine si un echec de recherche concerne La Centrale.

    On verifie le champ site explicite, ou a defaut on scanne les URLs
    du search_log pour detecter "lacentrale.fr".
    """
    site_norm = (site or "").strip().lower()
    if site_norm == "lacentrale":
        return True

    for step in search_log or []:
        if not isinstance(step, dict):
            continue
        url = str(step.get("url") or "").lower()
        if "lacentrale.fr" in url:
            return True
    return False


def _best_lacentrale_diagnostic_tag(search_log: list[dict] | None) -> str | None:
    """Retourne le diagnostic LC le plus significatif du search_log.

    On priorise par severite : anti_bot_403 > anti_bot_page > iframe_blocked > ...
    pour que le dashboard affiche le probleme le plus critique.
    """
    best_tag = None
    best_rank = -1
    for step in search_log or []:
        if not isinstance(step, dict):
            continue
        tag = step.get("diagnostic_tag")
        rank = _LACENTRALE_DIAGNOSTIC_PRIORITY.get(tag, 0)
        if rank > best_rank:
            best_rank = rank
            best_tag = tag
    return best_tag


def _queue_lacentrale_market_fallback(
    make: str,
    model: str,
    year: int,
    region: str,
    fuel: str | None,
    gearbox: str | None,
    hp_range: str | None,
    country: str,
    payload: dict,
    search_log: list[dict] | None,
) -> dict:
    """Cree des jobs de fallback LBC/AS24 pour un echec La Centrale.

    Idee produit : si LC ne donne rien (anti-bot, parser casse, etc.),
    on pousse ce vehicule dans les files LBC et AS24 qui sont plus
    fiables. Ca garantit que le vehicule aura quand meme un argus.
    """
    from app.services.collection_job_as24_service import enqueue_collection_job_as24
    from app.services.collection_job_service import (
        POST_2016_REGIONS,
        enqueue_collection_job,
        expand_collection_jobs,
    )
    from app.services.vehicle_lookup import find_vehicle

    # Le fallback LC ne fonctionne que pour la France (pas de LC hors FR)
    country_upper = (country or "FR").upper().strip()
    if country_upper != "FR":
        return {
            "triggered": False,
            "reason": "country_not_supported",
            "diagnostic_tag": _best_lacentrale_diagnostic_tag(search_log),
        }

    source_vehicle = f"{make} {model} {year} {fuel or ''} {gearbox or ''}".strip()
    clean_region = (region or "").strip()

    # Job LBC : soit exact (region post-2016) soit regional_fallback (expansion)
    lbc_job = None
    lbc_mode = "exact"
    if clean_region in POST_2016_REGIONS:
        lbc_job = enqueue_collection_job(
            make=make,
            model=model,
            year=year,
            region=clean_region,
            fuel=fuel,
            gearbox=gearbox,
            hp_range=hp_range,
            priority=0,
            source_vehicle=source_vehicle,
            country="FR",
        )
        lbc_count = 1 if lbc_job else 0
    else:
        # Region pas dans le nouveau format → on expand en plusieurs jobs regionaux
        lbc_mode = "regional_fallback"
        lbc_jobs = expand_collection_jobs(
            make=make,
            model=model,
            year=year,
            region=clean_region or "France",
            fuel=fuel,
            gearbox=gearbox,
            hp_range=hp_range,
            country="FR",
        )
        lbc_count = len(lbc_jobs)

    # Job AS24 : on a besoin des slugs pour construire l'URL
    vehicle = find_vehicle(make, model)
    slug_make = (payload.get("as24_slug_make") or "").strip()
    slug_model = (payload.get("as24_slug_model") or "").strip()
    # Fallback sur les slugs deja enregistres dans le referentiel
    if not slug_make and vehicle and vehicle.as24_slug_make:
        slug_make = vehicle.as24_slug_make.strip()
    if not slug_model and vehicle and vehicle.as24_slug_model:
        slug_model = vehicle.as24_slug_model.strip()

    as24_reason = None
    as24_job = None
    if slug_make and slug_model:
        as24_job = enqueue_collection_job_as24(
            make=make,
            model=model,
            year=year,
            region="national",
            fuel=fuel,
            gearbox=gearbox,
            hp_range=hp_range,
            priority=0,
            source_vehicle=source_vehicle,
            country="FR",
            tld="fr",
            slug_make=slug_make,
            slug_model=slug_model,
        )
    else:
        # Sans slugs, impossible de construire l'URL AS24
        as24_reason = "slugs_manquants"

    return {
        "triggered": True,
        "diagnostic_tag": _best_lacentrale_diagnostic_tag(search_log),
        "lbc_jobs": lbc_count,
        "lbc_mode": lbc_mode,
        "as24_jobs": 1 if as24_job else 0,
        "as24_reason": as24_reason,
        "slug_make": slug_make or None,
        "slug_model": slug_model or None,
    }


@api_bp.route("/market-prices/job-done", methods=["POST"])
@limiter.limit("60/minute")
def mark_job_complete():
    """Callback de l'extension pour signaler qu'un job de collecte est termine.

    Body JSON :
        { job_id: int, success: bool, site: "lbc"|"as24"|"lacentrale" (default "lbc") }
    """
    from app.services.collection_job_as24_service import mark_job_done_as24
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
    site = data.get("site", "lbc")

    try:
        if site == "as24":
            mark_job_done_as24(job_id, success=success)
        elif site == "lacentrale":
            from app.services.collection_job_lc_service import mark_job_done_lc

            mark_job_done_lc(job_id, success=success)
        else:
            try:
                mark_job_done(job_id, success=success)
            except (ValueError, TypeError):
                # Fallback : le job n'est pas dans la table LBC,
                # on tente la table AS24 (peut arriver si l'extension
                # n'a pas precise le site correctement).
                mark_job_done_as24(job_id, success=success)
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

    Logique en 3 etapes :
    1. Si le vehicule courant a besoin d'un refresh (> 7 jours ou absent) → le retourner
    2. Sinon, trouver un autre vehicule du referentiel stale dans la meme region
    3. Si tout est a jour, renvoyer collect=false + bonus_jobs eventuels

    Query params :
        make, model, year (int), region, fuel, gearbox, hp_range, country, site, tld
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

    # Ne pas collecter de prix pour les modeles generiques ("Autres")
    if model and model.strip().lower() in _GENERIC_MODELS:
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    if not (1990 <= year <= 2030):
        return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": []}})

    # Canonicaliser make/model pour les lookups DB (memes aliases que store/get).
    # IMPORTANT: on garde les valeurs brutes pour la reponse API vers l'extension,
    # sinon on casserait la construction d'URL cote navigateur.
    from app.services.vehicle_lookup import display_brand, display_model

    lookup_make = display_brand(make)
    lookup_model = display_model(model)

    # Creer des jobs de collecte pour ce vehicule (la dedup gere les repetitions)
    if site == "as24":
        from app.services.collection_job_as24_service import expand_collection_jobs_as24

        slug_make = request.args.get("slug_make", "")
        slug_model = request.args.get("slug_model", "")
        expand_collection_jobs_as24(
            make=make,
            model=model,
            year=year,
            region=region,
            fuel=fuel,
            gearbox=gearbox,
            hp_range=hp_range,
            country=country,
            tld=tld,
            slug_make=slug_make,
            slug_model=slug_model,
        )
    elif site == "lacentrale":
        from app.services.collection_job_lc_service import expand_collection_jobs_lc

        expand_collection_jobs_lc(
            make=make,
            model=model,
            year=year,
            fuel=fuel,
            gearbox=gearbox,
            hp_range=hp_range,
        )
    else:
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

    # --- Etape 1 : Le vehicule courant a-t-il besoin d'un refresh ? ---
    # Si l'extension fournit fuel/hp_range, on exige cette variante exacte.
    # Sinon un record generique "frais" pourrait masquer l'absence de la
    # variante reellement utile pour L4.
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

    # --- Etape 2 : Trouver un autre vehicule stale dans la meme region ---
    # Sous-requete : dernier collected_at par (make, model) dans cette region
    from sqlalchemy import case

    latest_mp = (
        db.session.query(
            func.vehicle_lookup_key(MarketPrice.make).label("mp_make_key"),
            func.vehicle_lookup_key(MarketPrice.model).label("mp_model_key"),
            func.max(MarketPrice.collected_at).label("latest_at"),
        )
        .filter(
            market_text_key_expr(MarketPrice.region) == market_text_key(region),
            func.coalesce(MarketPrice.country, "FR") == country_upper,
        )
        .group_by(
            func.vehicle_lookup_key(MarketPrice.make),
            func.vehicle_lookup_key(MarketPrice.model),
        )
        .subquery()
    )

    # LEFT JOIN avec le referentiel Vehicle pour trouver les vehicules stale ou jamais collectes
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
                Vehicle.brand_lookup_key == latest_mp.c.mp_make_key,
                Vehicle.model_lookup_key == latest_mp.c.mp_model_key,
            ),
        )
        .filter(
            Vehicle.year_start.isnot(None),
            ~Vehicle.model_lookup_key.in_(list(_GENERIC_MODELS)),
        )
        .order_by(
            # Priorite 1 : jamais collecte (NULL) d'abord
            case((latest_mp.c.latest_at.is_(None), 0), else_=1),
            # Priorite 2 : vehicules en cours d'enrichissement avant les complets
            case((Vehicle.enrichment_status == "partial", 0), else_=1),
            # Priorite 3 : le plus ancien en date de collecte
            latest_mp.c.latest_at.asc(),
            Vehicle.id.asc(),
        )
        .limit(1)
        .all()
    )

    best_candidate = None
    for c in candidates:
        if c.latest_at is None or c.latest_at < cutoff:
            # On prend l'annee du milieu de la plage de production
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

    # --- Etape 3 : Tout est a jour dans cette region ---
    bonus = _pick_and_serialize_bonus(site=site, country=country_upper, tld=tld)
    logger.info("next-job: tout est a jour pour la region %s (+%d bonus)", region, len(bonus))
    return jsonify({"success": True, "data": {"collect": False, "bonus_jobs": bonus}})


@api_bp.route("/market-prices/failed-search", methods=["POST"])
@limiter.limit("30/minute")
def report_failed_search():
    """Recoit un rapport de recherche echouee (0 annonces sur toutes les strategies).

    Permet d'identifier les URLs mal construites (tokens manquants, accents, etc.)
    et d'apprendre rapidement des erreurs. Alimente aussi le dashboard admin
    "Monitoring Recherches" pour investiguer les patterns d'echec.

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

    # Compter les occurrences precedentes pour ce vehicule :
    # la severite augmente automatiquement si le meme vehicule echoue souvent.
    from sqlalchemy import func as sqla_func

    occurrence_count = FailedSearch.query.filter(
        sqla_func.lower(FailedSearch.make) == make.strip().lower(),
        sqla_func.lower(FailedSearch.model) == model_name.strip().lower(),
    ).count()

    # Compat multi-sites : LBC utilise brand_token_used/model_token_used,
    # AS24 utilise slug_make_used/slug_model_used. On normalise.
    site = (data.get("site") or "").strip().lower()
    brand_token_used = data.get("brand_token_used") or data.get("slug_make_used")
    model_token_used = data.get("model_token_used") or data.get("slug_model_used")
    token_source = data.get("token_source") or data.get("slug_source")

    if not token_source and site == "as24":
        token_source = "as24_generated_url"

    # Les tokens "fallback" indiquent qu'on a utilise un slug genere
    # plutot qu'un slug appris → severite plus haute car plus fragile.
    severity_source = token_source
    if token_source and "fallback" in token_source.lower():
        severity_source = "fallback"

    severity = FailedSearch.compute_severity(occurrence_count + 1, severity_source)

    try:
        year_int = int(year) if year else 0
    except (TypeError, ValueError):
        year_int = 0

    entry = FailedSearch(
        make=make,
        model=model_name,
        year=year_int,
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

    # Auto-learn tokens meme en echec : le DOM peut avoir les bons tokens
    # meme si la recherche n'a rien retourne (ex: vehicule niche, annee rare)
    _site_bt = data.get("site_brand_token")
    _site_mt = data.get("site_model_token")
    if _site_bt or _site_mt:
        _persist_site_tokens(make, model_name, _site_bt, _site_mt)

    _as24_sm = data.get("as24_slug_make")
    _as24_smod = data.get("as24_slug_model")
    if _as24_sm or _as24_smod:
        _persist_as24_slugs(make, model_name, _as24_sm, _as24_smod)

    # Si l'echec vient de La Centrale, on lance un fallback automatique
    # vers LBC/AS24 pour ne pas rester sans argus.
    if _is_lacentrale_failed_search(site, search_log) and 1990 <= year_int <= 2030:
        try:
            fallback = _queue_lacentrale_market_fallback(
                make=make,
                model=model_name,
                year=year_int,
                region=region,
                fuel=data.get("fuel"),
                gearbox=data.get("gearbox"),
                hp_range=data.get("hp_range"),
                country=data.get("country", "FR"),
                payload=data,
                search_log=search_log,
            )
            if fallback.get("triggered"):
                lbc_label = (
                    f"{fallback['lbc_jobs']} job(s) LBC"
                    if fallback.get("lbc_mode") == "exact"
                    else f"{fallback['lbc_jobs']} job(s) LBC regionaux"
                )
                if fallback.get("as24_reason") == "slugs_manquants":
                    as24_label = "AS24 ignore (slugs manquants)"
                else:
                    as24_label = f"{fallback['as24_jobs']} job(s) AS24"

                note = (
                    f"Fallback automatique La Centrale → autres sites : {lbc_label}, {as24_label}."
                )
                if fallback.get("diagnostic_tag"):
                    note += f" Diagnostic={fallback['diagnostic_tag']}."

                if fallback.get("lbc_jobs") or fallback.get("as24_jobs"):
                    entry.set_status("investigating", note)
                else:
                    entry.add_note("auto_fallback", note)
                db.session.commit()
        except (ValueError, TypeError, SQLAlchemyError):
            db.session.rollback()
            logger.warning(
                "Failed to queue La Centrale fallback jobs for %s %s",
                make,
                model_name,
                exc_info=True,
            )

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
