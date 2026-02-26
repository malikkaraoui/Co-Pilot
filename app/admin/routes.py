"""Routes du blueprint admin : login, dashboard, vehicules, erreurs, pipelines."""

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.admin import admin_bp
from app.extensions import db, limiter
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.gemini_config import GeminiConfig, GeminiPromptConfig
from app.models.llm_usage import LLMUsage
from app.models.log import AppLog
from app.models.market_price import MarketPrice
from app.models.pipeline_run import PipelineRun
from app.models.scan import ScanLog
from app.models.user import User
from app.models.vehicle import Vehicle
from app.models.vehicle_synthesis import VehicleSynthesis
from app.models.youtube import YouTubeTranscript, YouTubeVideo

logger = logging.getLogger(__name__)

# ── Pipeline jobs (in-memory, thread-safe) ─────────────────────
# Stocke les jobs de synthese YouTube en cours pour le suivi temps reel.
_synthesis_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ── Authentification ────────────────────────────────────────────


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5/minute")
def login():
    """Page de connexion administrateur."""
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            logger.info("Admin '%s' connecte", username)
            return redirect(url_for("admin.dashboard"))

        flash("Identifiants invalides.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout")
@login_required
def logout():
    """Deconnexion de l'administrateur."""
    logout_user()
    return redirect(url_for("admin.login"))


# ── Dashboard principal ─────────────────────────────────────────


@admin_bp.route("/")
@admin_bp.route("/dashboard")
@login_required
def dashboard():
    """Page principale du tableau de bord avec statistiques et graphiques."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Statistiques generales
    total_scans = db.session.query(db.func.count(ScanLog.id)).scalar() or 0
    scans_today = (
        db.session.query(db.func.count(ScanLog.id))
        .filter(ScanLog.created_at >= today_start)
        .scalar()
        or 0
    )
    avg_score = (
        db.session.query(db.func.avg(ScanLog.score)).filter(ScanLog.score.isnot(None)).scalar()
    )
    avg_score = round(avg_score, 1) if avg_score else 0

    partial_count = (
        db.session.query(db.func.count(ScanLog.id)).filter(ScanLog.is_partial.is_(True)).scalar()
        or 0
    )
    partial_rate = round(partial_count / total_scans * 100, 1) if total_scans else 0

    # Taux d'echec : % de scans avec au moins un filtre "fail"
    scans_with_fail = (
        db.session.query(db.func.count(db.distinct(FilterResultDB.scan_id)))
        .filter(FilterResultDB.status == "fail")
        .scalar()
        or 0
    )
    fail_rate = round(scans_with_fail / total_scans * 100, 1) if total_scans else 0

    # Nombre total d'avertissements filtres
    warning_count = (
        db.session.query(db.func.count(FilterResultDB.id))
        .filter(FilterResultDB.status == "warning")
        .scalar()
        or 0
    )

    # Nombre d'erreurs applicatives (depuis AppLog)
    error_count = (
        db.session.query(db.func.count(AppLog.id)).filter(AppLog.level == "ERROR").scalar() or 0
    )

    # Donnees pour graphique : scans par jour (30 derniers jours)
    thirty_days_ago = now - timedelta(days=30)
    daily_scans = (
        db.session.query(
            db.func.date(ScanLog.created_at).label("day"),
            db.func.count(ScanLog.id).label("count"),
        )
        .filter(ScanLog.created_at >= thirty_days_ago)
        .group_by(db.func.date(ScanLog.created_at))
        .order_by(db.func.date(ScanLog.created_at))
        .all()
    )
    chart_days = [str(row.day) for row in daily_scans]
    chart_counts = [row.count for row in daily_scans]

    # Donnees pour graphique : distribution des scores
    scores = db.session.query(ScanLog.score).filter(ScanLog.score.isnot(None)).all()
    score_values = [s.score for s in scores]

    # Performance des filtres : pass/warning/fail/skip par filter_id
    filter_stats = (
        db.session.query(
            FilterResultDB.filter_id,
            FilterResultDB.status,
            db.func.count(FilterResultDB.id).label("count"),
        )
        .group_by(FilterResultDB.filter_id, FilterResultDB.status)
        .all()
    )
    filter_perf: dict[str, dict[str, int]] = {}
    for row in filter_stats:
        if row.filter_id not in filter_perf:
            filter_perf[row.filter_id] = {"pass": 0, "warning": 0, "fail": 0, "skip": 0}
        filter_perf[row.filter_id][row.status] = row.count

    # Top 10 vehicules analyses (GROUP BY insensible a la casse)
    top_vehicles = (
        db.session.query(
            db.func.min(ScanLog.vehicle_make).label("vehicle_make"),
            db.func.min(ScanLog.vehicle_model).label("vehicle_model"),
            db.func.count(ScanLog.id).label("count"),
        )
        .filter(ScanLog.vehicle_make.isnot(None))
        .group_by(db.func.lower(ScanLog.vehicle_make), db.func.lower(ScanLog.vehicle_model))
        .order_by(db.func.count(ScanLog.id).desc())
        .limit(10)
        .all()
    )

    # 10 derniers scans
    recent_scans = ScanLog.query.order_by(ScanLog.created_at.desc()).limit(10).all()

    # Vehicules non reconnus (distinct make+model avec L2 warning)
    unrecognized_subq = (
        db.session.query(ScanLog.vehicle_make, ScanLog.vehicle_model)
        .join(FilterResultDB, FilterResultDB.scan_id == ScanLog.id)
        .filter(
            FilterResultDB.filter_id == "L2",
            FilterResultDB.status == "warning",
            ScanLog.vehicle_make.isnot(None),
            ScanLog.vehicle_model.isnot(None),
        )
        .group_by(ScanLog.vehicle_make, ScanLog.vehicle_model)
        .subquery()
    )
    unrecognized_count = (
        db.session.query(db.func.count()).select_from(unrecognized_subq).scalar() or 0
    )

    # Prix du marche crowdsources
    market_total = db.session.query(db.func.count(MarketPrice.id)).scalar() or 0
    market_fresh = (
        db.session.query(db.func.count(MarketPrice.id))
        .filter(MarketPrice.refresh_after > now)
        .scalar()
        or 0
    )
    market_total_samples = db.session.query(db.func.sum(MarketPrice.sample_count)).scalar() or 0
    recent_market = MarketPrice.query.order_by(MarketPrice.collected_at.desc()).limit(10).all()

    # Prospection CSV : vehicules disponibles
    from app.services.csv_enrichment import get_csv_missing_vehicles

    csv_missing_count = len(get_csv_missing_vehicles())

    return render_template(
        "admin/dashboard.html",
        total_scans=total_scans,
        scans_today=scans_today,
        avg_score=avg_score,
        partial_rate=partial_rate,
        fail_rate=fail_rate,
        warning_count=warning_count,
        error_count=error_count,
        chart_days=json.dumps(chart_days),
        chart_counts=json.dumps(chart_counts),
        score_values=json.dumps(score_values),
        filter_perf=json.dumps(filter_perf),
        top_vehicles=top_vehicles,
        recent_scans=recent_scans,
        unrecognized_count=unrecognized_count,
        market_total=market_total,
        market_fresh=market_fresh,
        market_total_samples=market_total_samples,
        recent_market=recent_market,
        csv_missing_count=csv_missing_count,
        now=now,
    )


# ── Vehicules non reconnus ──────────────────────────────────────


@admin_bp.route("/car")
@login_required
def car():
    """Modeles vehicules les plus demandes mais non reconnus."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    # Query robuste : JOIN ScanLog + FilterResultDB (L2 warning = non reconnu)
    # GROUP BY insensible a la casse pour fusionner "transit"/"TRANSIT"/"Transit"
    unrecognized_rows_raw = (
        db.session.query(
            db.func.min(ScanLog.vehicle_make).label("vehicle_make"),
            db.func.min(ScanLog.vehicle_model).label("vehicle_model"),
            db.func.count(ScanLog.id).label("demand_count"),
            db.func.min(ScanLog.created_at).label("first_seen"),
            db.func.max(ScanLog.created_at).label("last_seen"),
        )
        .join(FilterResultDB, FilterResultDB.scan_id == ScanLog.id)
        .filter(
            FilterResultDB.filter_id == "L2",
            FilterResultDB.status == "warning",
            ScanLog.vehicle_make.isnot(None),
            ScanLog.vehicle_model.isnot(None),
        )
        .group_by(db.func.lower(ScanLog.vehicle_make), db.func.lower(ScanLog.vehicle_model))
        .order_by(db.func.count(ScanLog.id).desc())
        .limit(50)
        .all()
    )

    # Exclure les vehicules deja ajoutes au referentiel + les generiques ("Autres")
    from app.services.vehicle_lookup import find_vehicle, is_generic_model

    unrecognized_rows = [
        row
        for row in unrecognized_rows_raw
        if not find_vehicle(row.vehicle_make, row.vehicle_model)
        and not is_generic_model(row.vehicle_model)
    ]

    # Auto-promotion : vehicules avec assez de scans + donnees → auto-creation
    from app.services.csv_enrichment import has_specs
    from app.services.market_service import market_text_key, market_text_key_expr
    from app.services.vehicle_factory import auto_create_vehicle

    auto_promoted = []
    still_unrecognized = []
    for row in unrecognized_rows:
        if row.demand_count >= 3:
            vehicle = auto_create_vehicle(row.vehicle_make, row.vehicle_model)
            if vehicle:
                auto_promoted.append(f"{vehicle.brand} {vehicle.model}")
                continue
        still_unrecognized.append(row)
    unrecognized_rows = still_unrecognized

    if auto_promoted:
        flash(
            f"Auto-ajout ({len(auto_promoted)}) : {', '.join(auto_promoted)}",
            "success",
        )

    # Tendance 7j : comptages semaine courante vs semaine precedente (1 requete)
    trend_rows = (
        db.session.query(
            db.func.min(ScanLog.vehicle_make).label("vehicle_make"),
            db.func.min(ScanLog.vehicle_model).label("vehicle_model"),
            db.func.sum(db.case((ScanLog.created_at >= seven_days_ago, 1), else_=0)).label(
                "recent_cnt"
            ),
            db.func.sum(
                db.case(
                    (
                        db.and_(
                            ScanLog.created_at >= fourteen_days_ago,
                            ScanLog.created_at < seven_days_ago,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("previous_cnt"),
        )
        .join(FilterResultDB, FilterResultDB.scan_id == ScanLog.id)
        .filter(
            FilterResultDB.filter_id == "L2",
            FilterResultDB.status == "warning",
            ScanLog.created_at >= fourteen_days_ago,
            ScanLog.vehicle_make.isnot(None),
            ScanLog.vehicle_model.isnot(None),
        )
        .group_by(db.func.lower(ScanLog.vehicle_make), db.func.lower(ScanLog.vehicle_model))
        .all()
    )
    recent_counts = {(r.vehicle_make, r.vehicle_model): r.recent_cnt for r in trend_rows}
    previous_counts = {(r.vehicle_make, r.vehicle_model): r.previous_cnt for r in trend_rows}

    unrecognized_models = []
    for row in unrecognized_rows:
        key = (row.vehicle_make, row.vehicle_model)
        recent = recent_counts.get(key, 0)
        previous = previous_counts.get(key, 0)
        if previous > 0:
            trend = round((recent - previous) / previous * 100)
        elif recent > 0:
            trend = None  # "Nouveau" -- pas de semaine precedente pour comparer
        else:
            trend = 0

        # Statut CSV : est-ce que le vehicule a des donnees dans le CSV ?
        # has_specs() est O(1) grace au cache en memoire
        csv_available = has_specs(row.vehicle_make, row.vehicle_model)

        # Statut marche : est-ce qu'on a des prix collectes pour ce vehicule ?
        market_records = MarketPrice.query.filter(
            market_text_key_expr(MarketPrice.make) == market_text_key(row.vehicle_make),
            market_text_key_expr(MarketPrice.model) == market_text_key(row.vehicle_model),
        ).all()
        market_samples = sum(r.sample_count for r in market_records) if market_records else 0

        unrecognized_models.append(
            {
                "brand": row.vehicle_make,
                "model": row.vehicle_model,
                "count": row.demand_count,
                "first_seen": row.first_seen,
                "last_seen": row.last_seen,
                "trend": trend,
                "csv_available": csv_available,
                "market_available": market_samples >= 20,
                "market_samples": market_samples,
            }
        )

    # Vehicules reconnus dans le referentiel (pagines)
    page = request.args.get("page", 1, type=int)
    per_page = 50
    known_pagination = Vehicle.query.order_by(Vehicle.brand, Vehicle.model).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # ── Couverture marques : comparer referentiel vs marques scannees ──
    # Toutes les marques scannees (reconnus + non reconnus)
    scanned_brands_raw = (
        db.session.query(
            db.func.min(ScanLog.vehicle_make).label("vehicle_make"),
            db.func.count(ScanLog.id).label("scan_count"),
        )
        .filter(ScanLog.vehicle_make.isnot(None))
        .group_by(db.func.lower(ScanLog.vehicle_make))
        .order_by(db.func.count(ScanLog.id).desc())
        .all()
    )

    # Marques dans le referentiel (en minuscules pour comparaison)
    ref_brands = {v.brand.lower() for v in db.session.query(Vehicle.brand).distinct().all()}

    # Marques dans le marche (MarketPrice)
    market_brands = {m.make.lower() for m in db.session.query(MarketPrice.make).distinct().all()}

    from app.services.vehicle_lookup import BRAND_ALIASES, normalize_brand

    brand_coverage = []
    for row in scanned_brands_raw:
        brand_raw = row.vehicle_make
        brand_norm = normalize_brand(brand_raw)
        in_referentiel = brand_norm in ref_brands
        in_market = brand_norm in market_brands or brand_raw.lower() in market_brands

        # Compter les modeles dans le referentiel pour cette marque
        models_in_ref = Vehicle.query.filter(
            db.func.lower(Vehicle.brand) == brand_norm,
        ).count()

        # Compter les modeles scannes (L2 warning = non reconnus)
        models_scanned_unrec = sum(
            1 for u in unrecognized_models if u["brand"].lower() == brand_raw.lower()
        )

        brand_coverage.append(
            {
                "brand": brand_raw,
                "brand_normalized": brand_norm,
                "scan_count": row.scan_count,
                "in_referentiel": in_referentiel,
                "in_market": in_market,
                "models_in_ref": models_in_ref,
                "models_unrecognized": models_scanned_unrec,
                "has_alias": brand_raw.lower() in BRAND_ALIASES,
            }
        )

    # Stats resume pour les stat cards
    total_scanned_brands = len(brand_coverage)
    covered_brands = sum(1 for b in brand_coverage if b["in_referentiel"])
    uncovered_brands = total_scanned_brands - covered_brands
    total_ref_models = known_pagination.total

    # Enrichissement du referentiel : compter par source
    enrichment_stats = (
        db.session.query(
            Vehicle.enrichment_status,
            db.func.count(Vehicle.id).label("count"),
        )
        .group_by(Vehicle.enrichment_status)
        .all()
    )
    enrichment_counts = {row.enrichment_status: row.count for row in enrichment_stats}

    return render_template(
        "admin/car.html",
        unrecognized_models=unrecognized_models,
        known_vehicles=known_pagination.items,
        pagination=known_pagination,
        brand_coverage=brand_coverage,
        total_scanned_brands=total_scanned_brands,
        covered_brands=covered_brands,
        uncovered_brands=uncovered_brands,
        total_ref_models=total_ref_models,
        enrichment_counts=enrichment_counts,
    )


@admin_bp.route("/vehicle/quick-add", methods=["POST"])
@login_required
def quick_add_vehicle():
    """Ajout rapide d'un vehicule au referentiel depuis la demande utilisateur."""
    brand = request.form.get("brand", "").strip()[:80]
    model_name = request.form.get("model", "").strip()[:120]

    if not brand or not model_name:
        flash("Marque et modele sont requis.", "error")
        return redirect(url_for("admin.car"))

    # Validation : caracteres autorises (lettres, chiffres, espaces, tirets, points)
    _VALID_NAME = re.compile(r"^[\w\s.\-/]+$", re.UNICODE)
    if not _VALID_NAME.match(brand) or not _VALID_NAME.match(model_name):
        flash("Caracteres invalides dans la marque ou le modele.", "error")
        return redirect(url_for("admin.car"))

    # Normalisation canonique (memes fonctions que l'extraction et find_vehicle)
    from app.services.vehicle_lookup import (
        display_brand,
        display_model,
        normalize_brand,
        normalize_model,
    )

    brand_clean = display_brand(brand)
    model_clean = display_model(model_name)

    # Verifier doublon (via normalisation canonique)
    existing = Vehicle.query.filter(
        db.func.lower(Vehicle.brand) == normalize_brand(brand),
        db.func.lower(Vehicle.model) == normalize_model(model_name),
    ).first()

    if existing:
        flash(f"{brand_clean} {model_clean} existe deja dans le referentiel.", "warning")
        return redirect(url_for("admin.car"))

    source = request.form.get("source", "csv")
    current_year = datetime.now(timezone.utc).year

    # Determiner year_start/year_end depuis les donnees marche si source=market
    year_start = current_year
    year_end = None
    if source == "market":
        from app.services.market_service import market_text_key, market_text_key_expr

        market_records = MarketPrice.query.filter(
            market_text_key_expr(MarketPrice.make) == market_text_key(brand_clean),
            market_text_key_expr(MarketPrice.model) == market_text_key(model_clean),
        ).all()
        if market_records:
            years = [r.year for r in market_records if r.year]
            if years:
                year_start = min(years)
                year_end = max(years)

    vehicle = Vehicle(
        brand=brand_clean,
        model=model_clean,
        year_start=year_start,
        year_end=year_end,
        enrichment_status="pending",
    )
    db.session.add(vehicle)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash(f"{brand} {model_name} existe deja dans le referentiel.", "warning")
        return redirect(url_for("admin.car"))

    logger.info(
        "Quick-add vehicle: %s %s (id=%d, source=%s) by admin '%s'",
        brand_clean,
        model_clean,
        vehicle.id,
        source,
        current_user.username,
    )

    # Auto-enrichissement depuis le CSV Kaggle (gratuit, immediat)
    from app.services.csv_enrichment import lookup_specs

    csv_specs = lookup_specs(brand_clean, model_clean)
    specs_created = 0
    if csv_specs:
        from app.models.vehicle import VehicleSpec

        # Extraire les annees du CSV avant de creer les specs
        years_from = [s["year_from"] for s in csv_specs if s.get("year_from")]
        years_to = [s["year_to"] for s in csv_specs if s.get("year_to")]

        for spec_data in csv_specs:
            # Retirer les metadata CSV (pas dans VehicleSpec)
            spec_data.pop("generation", None)
            spec_data.pop("year_from", None)
            spec_data.pop("year_to", None)
            spec = VehicleSpec(vehicle_id=vehicle.id, **spec_data)
            db.session.add(spec)
            specs_created += 1

        if years_from:
            vehicle.year_start = min(years_from)
        if years_to:
            vehicle.year_end = max(years_to)
        vehicle.enrichment_status = "partial"
        db.session.commit()
        logger.info(
            "Auto-enriched %s %s: %d specs from CSV", brand_clean, model_clean, specs_created
        )
    elif source == "market":
        vehicle.enrichment_status = "partial"
        db.session.commit()

    sources_msg = []
    if specs_created:
        sources_msg.append(f"{specs_created} fiches CSV")
    if source == "market":
        sources_msg.append("donnees marche")
    enrichment_msg = (
        f" (sources: {' + '.join(sources_msg)})" if sources_msg else " (enrichissement en attente)"
    )
    flash(
        f"{brand_clean} {model_clean} ajoute au referentiel{enrichment_msg}.",
        "success",
    )
    return redirect(url_for("admin.car"))


# ── Base Vehicules (import CSV) ───────────────────────────────────


@admin_bp.route("/database")
@login_required
def database():
    """Exploration de la base vehicules importee depuis le CSV Kaggle."""
    from app.models.vehicle import VehicleSpec

    # Parametres de filtrage
    brand_filter = request.args.get("brand", "").strip()
    model_filter = request.args.get("model", "").strip()
    fuel_filter = request.args.get("fuel", "").strip()
    page = request.args.get("page", 1, type=int)

    # Stats generales
    total_brands = db.session.query(db.func.count(db.distinct(Vehicle.brand))).scalar() or 0
    total_models = (
        db.session.query(db.func.count(db.distinct(Vehicle.brand + " " + Vehicle.model))).scalar()
        or 0
    )
    total_specs = db.session.query(db.func.count(VehicleSpec.id)).scalar() or 0

    # Distribution par marque (top 20) pour graphique Plotly
    brand_dist = (
        db.session.query(
            Vehicle.brand,
            db.func.count(VehicleSpec.id).label("count"),
        )
        .join(VehicleSpec, Vehicle.id == VehicleSpec.vehicle_id)
        .group_by(Vehicle.brand)
        .order_by(db.func.count(VehicleSpec.id).desc())
        .limit(20)
        .all()
    )
    chart_brands = [row.brand for row in brand_dist]
    chart_counts = [row.count for row in brand_dist]

    # Liste des marques pour le select de filtre
    all_brands = db.session.query(Vehicle.brand).distinct().order_by(Vehicle.brand).all()
    brand_list = [b.brand for b in all_brands]

    # Liste des carburants pour le select de filtre
    all_fuels = (
        db.session.query(VehicleSpec.fuel_type)
        .filter(VehicleSpec.fuel_type.isnot(None), VehicleSpec.fuel_type != "")
        .distinct()
        .order_by(VehicleSpec.fuel_type)
        .all()
    )
    fuel_list = [f.fuel_type for f in all_fuels]

    # Query principale avec filtres
    query = (
        db.session.query(Vehicle, VehicleSpec)
        .join(VehicleSpec, Vehicle.id == VehicleSpec.vehicle_id)
        .order_by(Vehicle.brand, Vehicle.model, VehicleSpec.power_hp)
    )

    if brand_filter:
        query = query.filter(Vehicle.brand == brand_filter)
    if model_filter:
        query = query.filter(Vehicle.model.ilike(f"%{model_filter}%"))
    if fuel_filter:
        query = query.filter(VehicleSpec.fuel_type == fuel_filter)

    # Pagination manuelle (query retourne des tuples, pas un model)
    per_page = 50
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    results = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template(
        "admin/database.html",
        total_brands=total_brands,
        total_models=total_models,
        total_specs=total_specs,
        chart_brands=json.dumps(chart_brands),
        chart_counts=json.dumps(chart_counts),
        brand_list=brand_list,
        fuel_list=fuel_list,
        brand_filter=brand_filter,
        model_filter=model_filter,
        fuel_filter=fuel_filter,
        results=results,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    )


# ── Prospection CSV ─────────────────────────────────────────


@admin_bp.route("/csv-prospection")
@login_required
def csv_prospection():
    """Prospection CSV : véhicules disponibles dans les CSV mais pas encore importés."""
    from urllib.parse import quote_plus

    from app.services.csv_enrichment import get_csv_missing_vehicles

    # Récupérer les véhicules manquants
    missing_vehicles = get_csv_missing_vehicles()

    # Stats pour les cards
    total_missing = len(missing_vehicles)
    total_specs = sum(v["specs_count"] for v in missing_vehicles)

    # Pagination
    page = request.args.get("page", 1, type=int)
    per_page = 50
    total_pages = max(1, (total_missing + per_page - 1) // per_page)
    page = min(page, total_pages)

    start = (page - 1) * per_page
    end = start + per_page
    paginated_vehicles = missing_vehicles[start:end]

    # Préconstruire les URLs LBC (Option B : plus simple dans le template)
    for vehicle in paginated_vehicles:
        query = f"{vehicle['brand']} {vehicle['model']}"
        vehicle["lbc_url"] = (
            f"https://www.leboncoin.fr/recherche?category=2&text={quote_plus(query)}"
        )

    return render_template(
        "admin/csv_prospection.html",
        missing_vehicles=paginated_vehicles,
        total_missing=total_missing,
        total_specs=total_specs,
        page=page,
        total_pages=total_pages,
    )


# ── Logs d'erreurs ───────────────────────────────────────────────


@admin_bp.route("/errors")
@login_required
def errors():
    """Consulter les logs d'erreurs et d'avertissements recents."""
    level_filter = request.args.get("level", "ERROR")
    page = request.args.get("page", 1, type=int)

    query = AppLog.query
    if level_filter != "ALL":
        query = query.filter(AppLog.level == level_filter)

    logs = query.order_by(AppLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )

    return render_template(
        "admin/errors.html",
        logs=logs,
        level_filter=level_filter,
    )


# ── Monitoring pipelines ────────────────────────────────────────


@admin_bp.route("/pipelines")
@login_required
def pipelines():
    """Etat des pipelines d'enrichissement de donnees."""
    from app.models.argus import ArgusPrice
    from app.models.vehicle import VehicleSpec

    # Statistiques du referentiel
    vehicle_count = db.session.query(db.func.count(Vehicle.id)).scalar() or 0
    spec_count = db.session.query(db.func.count(VehicleSpec.id)).scalar() or 0
    argus_count = db.session.query(db.func.count(ArgusPrice.id)).scalar() or 0

    # Helpers pour interroger PipelineRun
    def _last_run(name: str) -> PipelineRun | None:
        return (
            PipelineRun.query.filter_by(name=name).order_by(PipelineRun.started_at.desc()).first()
        )

    def _run_counts(name: str) -> dict[str, int]:
        success = PipelineRun.query.filter_by(name=name, status="success").count()
        failure = PipelineRun.query.filter_by(name=name, status="failure").count()
        return {"success": success, "failure": failure}

    last_ref = _last_run("referentiel_vehicules")
    last_csv = _last_run("import_csv_specs")
    last_argus = _last_run("argus_geolocalise")
    last_yt = _last_run("youtube_transcripts")
    last_llm = _last_run("llm_fiches")

    # Stats YouTube
    yt_video_count = db.session.query(db.func.count(YouTubeVideo.id)).scalar() or 0
    yt_transcript_count = (
        db.session.query(db.func.count(YouTubeTranscript.id))
        .filter(YouTubeTranscript.status == "extracted")
        .scalar()
        or 0
    )

    pipeline_status = [
        {
            "name": "Referentiel vehicules",
            "description": "Modeles et specifications dans la base",
            "count": vehicle_count,
            "specs": spec_count,
            "status": "ok" if vehicle_count > 0 else "vide",
            "last_run": last_ref.started_at if last_ref else None,
            "runs": _run_counts("referentiel_vehicules"),
        },
        {
            "name": "Import CSV specs",
            "description": "Import des specs techniques depuis le CSV Kaggle",
            "count": spec_count,
            "status": "ok" if last_csv else ("vide" if spec_count == 0 else "ok"),
            "last_run": last_csv.started_at if last_csv else None,
            "runs": _run_counts("import_csv_specs"),
        },
        {
            "name": "Argus geolocalise",
            "description": "Prix argus par region",
            "count": argus_count,
            "status": "ok" if argus_count > 0 else "vide",
            "last_run": last_argus.started_at if last_argus else None,
            "runs": _run_counts("argus_geolocalise"),
        },
        {
            "name": "YouTube Transcripts",
            "description": "Extraction sous-titres francais des tests YouTube",
            "count": yt_transcript_count,
            "specs": yt_video_count,
            "status": "ok"
            if yt_transcript_count > 0
            else ("non lance" if not last_yt else last_yt.status),
            "last_run": last_yt.started_at if last_yt else None,
            "runs": _run_counts("youtube_transcripts"),
        },
        {
            "name": "LLM fiches vehicules",
            "description": "Generation de fiches via LLM",
            "count": 0,
            "status": "non lance" if not last_llm else last_llm.status,
            "last_run": last_llm.started_at if last_llm else None,
            "runs": _run_counts("llm_fiches"),
        },
    ]

    # Dernier scan effectue
    last_scan = ScanLog.query.order_by(ScanLog.created_at.desc()).first()

    # Derniere erreur pipeline
    last_pipeline_error = (
        AppLog.query.filter(AppLog.module.like("%pipeline%"))
        .order_by(AppLog.created_at.desc())
        .first()
    )

    return render_template(
        "admin/pipelines.html",
        pipelines=pipeline_status,
        last_scan=last_scan,
        last_pipeline_error=last_pipeline_error,
    )


# ── Matrice des filtres ───────────────────────────────────────────

# Metadata statique : description, source, maturite de chaque filtre.
# Mise a jour manuelle quand un filtre evolue.
_FILTER_META = [
    {
        "id": "L1",
        "name": "Completude des donnees",
        "description": "Verifie que les champs critiques de l'annonce sont presents "
        "(prix, marque, modele, annee, km).",
        "data_source": "Donnees de l'annonce",
        "data_source_type": "real",
        "maturity": 100,
        "maturity_note": "Logique pure, aucune donnee externe",
    },
    {
        "id": "L2",
        "name": "Modele reconnu",
        "description": "Verifie si la marque/modele existe dans le referentiel vehicules Co-Pilot. "
        "Detecte les modeles generiques LBC (Autres).",
        "data_source": "Referentiel vehicules (92 modeles, 293 specs)",
        "data_source_type": "real",
        "maturity": 85,
        "maturity_note": "92 modeles dont gamme Mercedes complete, auto-promotion 5+ scans, "
        "detection generique 'Autres'. Objectif 200+",
    },
    {
        "id": "L3",
        "name": "Coherence km / annee",
        "description": "Verifie que le kilometrage est coherent avec l'age du vehicule "
        "(15 000 km/an en moyenne).",
        "data_source": "Donnees de l'annonce",
        "data_source_type": "real",
        "maturity": 100,
        "maturity_note": "Calcul mathematique, aucune donnee externe",
    },
    {
        "id": "L4",
        "name": "Prix vs Argus",
        "description": "Compare le prix de l'annonce aux prix reels collectes sur LeBonCoin "
        "(meme modele, annee, region). Detecte le signal 'anguille sous roche' "
        "(prix bas + annonce >30j = acheteurs mefiants).",
        "data_source": "Crowdsource LeBonCoin (prix reels collectes par les extensions)",
        "data_source_type": "real",
        "maturity": 60,
        "maturity_note": "Crowdsourcing actif via extension. Fallback seed argus quand <5 annonces "
        "collectees. Maturite croit avec le nombre d'utilisateurs.",
    },
    {
        "id": "L5",
        "name": "Analyse statistique prix",
        "description": "Analyse par z-scores NumPy pour detecter les prix outliers "
        "par rapport a la distribution de reference du marche. "
        "Detecte aussi les diesels en zone urbaine dense (risque FAP/injecteurs).",
        "data_source": "Crowdsource LeBonCoin (prix reels collectes par les extensions)",
        "data_source_type": "real",
        "maturity": 60,
        "maturity_note": "Crowdsourcing actif via extension. Fallback seed quand <5 annonces. "
        "Precision augmente avec le volume de donnees collectees.",
    },
    {
        "id": "L6",
        "name": "Telephone",
        "description": "Analyse le numero de telephone : format francais, "
        "mobile/fixe, indicatif etranger.",
        "data_source": "Donnees de l'annonce + listes ARCEP",
        "data_source_type": "real",
        "maturity": 100,
        "maturity_note": "Validation regex + bases ARCEP, aucune donnee externe payante",
    },
    {
        "id": "L7",
        "name": "SIRET vendeur",
        "description": "Verifie le SIRET/SIREN du vendeur pro via l'API "
        "recherche-entreprises.gouv.fr.",
        "data_source": "API gouvernementale (live)",
        "data_source_type": "real",
        "maturity": 100,
        "maturity_note": "API publique gratuite, fonctionnelle en production",
    },
    {
        "id": "L8",
        "name": "Detection import",
        "description": "Detecte les signaux de vehicules importes : mots-cles, "
        "indicatif etranger, anomalie de prix, texte etranger non traduit.",
        "data_source": "Donnees de l'annonce + heuristiques",
        "data_source_type": "real",
        "maturity": 85,
        "maturity_note": "7 signaux independants. Heuristique prix < 3000 EUR a affiner "
        "avec des seuils par segment",
    },
    {
        "id": "L9",
        "name": "Evaluation globale",
        "description": "Evalue les signaux de confiance transversaux : qualite de description, "
        "type de vendeur, photos, options payantes, localisation.",
        "data_source": "Donnees de l'annonce",
        "data_source_type": "real",
        "maturity": 95,
        "maturity_note": "Signaux qualitatifs complets. Anciennete deplacee vers L10. "
        "Objectif : analyse semantique IA",
    },
    {
        "id": "L10",
        "name": "Anciennete annonce",
        "description": "Analyse la duree de mise en vente par rapport au marche. "
        "Detecte les annonces stagnantes et les republications pour paraitre recent.",
        "data_source": "ScanLog historique + seuils par segment de prix",
        "data_source_type": "real",
        "maturity": 70,
        "maturity_note": "Scoring contextuel : mediane marche si 5+ scans, sinon seuils "
        "par prix. Detection republication. Maturite croit avec les scans.",
    },
]


@admin_bp.route("/filters")
@login_required
def filters():
    """Vue d'ensemble des 9 filtres d'analyse avec maturite et statistiques."""
    # Statistiques d'execution depuis FilterResultDB
    filter_stats_rows = (
        db.session.query(
            FilterResultDB.filter_id,
            FilterResultDB.status,
            db.func.count(FilterResultDB.id).label("cnt"),
        )
        .group_by(FilterResultDB.filter_id, FilterResultDB.status)
        .all()
    )

    filter_stats: dict[str, dict[str, int]] = {}
    for row in filter_stats_rows:
        if row.filter_id not in filter_stats:
            filter_stats[row.filter_id] = {
                "pass": 0,
                "warning": 0,
                "fail": 0,
                "skip": 0,
                "total": 0,
            }
        filter_stats[row.filter_id][row.status] = row.cnt
        filter_stats[row.filter_id]["total"] += row.cnt

    # Cartes resume (les filtres "planned" sont exclus des compteurs actifs)
    active_filters = [f for f in _FILTER_META if f["data_source_type"] != "planned"]
    planned_filters = [f for f in _FILTER_META if f["data_source_type"] == "planned"]
    total_filters = len(active_filters)
    real_count = sum(1 for f in active_filters if f["data_source_type"] == "real")
    planned_count = len(planned_filters)
    avg_maturity = (
        round(
            sum(f["maturity"] for f in active_filters) / total_filters,
        )
        if total_filters
        else 0
    )

    return render_template(
        "admin/filters.html",
        filter_meta=_FILTER_META,
        filter_stats=filter_stats,
        total_filters=total_filters,
        real_count=real_count,
        planned_count=planned_count,
        avg_maturity=avg_maturity,
    )


# ── Argus maison (prix crowdsources) ─────────────────────────────


@admin_bp.route("/argus")
@login_required
def argus():
    """Vue dediee de l'argus maison : tous les prix crowdsources par les extensions."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Filtres
    make_filter = request.args.get("make", "").strip()
    region_filter = request.args.get("region", "").strip()
    page = request.args.get("page", 1, type=int)

    # Stats resume
    total_refs = db.session.query(db.func.count(MarketPrice.id)).scalar() or 0
    fresh_refs = (
        db.session.query(db.func.count(MarketPrice.id))
        .filter(MarketPrice.refresh_after > now)
        .scalar()
        or 0
    )
    stale_refs = total_refs - fresh_refs
    total_samples = db.session.query(db.func.sum(MarketPrice.sample_count)).scalar() or 0

    # Couverture : nombre de marques et regions distinctes
    distinct_makes = db.session.query(db.func.count(db.distinct(MarketPrice.make))).scalar() or 0
    distinct_regions = (
        db.session.query(db.func.count(db.distinct(MarketPrice.region))).scalar() or 0
    )

    # Listes pour les selects de filtre
    all_makes = db.session.query(MarketPrice.make).distinct().order_by(MarketPrice.make).all()
    make_list = [m.make for m in all_makes]

    all_regions = db.session.query(MarketPrice.region).distinct().order_by(MarketPrice.region).all()
    region_list = [r.region for r in all_regions]

    # Query principale
    query = MarketPrice.query.order_by(MarketPrice.collected_at.desc())

    if make_filter:
        query = query.filter(MarketPrice.make == make_filter)
    if region_filter:
        query = query.filter(MarketPrice.region == region_filter)

    # Pagination
    per_page = 30
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    # ── Argus insuffisant : vehicules scannes sans argus fiable ──
    from app.services.market_service import (
        MIN_SAMPLE_COUNT,
        MIN_SAMPLE_NICHE,
        MIN_SAMPLE_ULTRA_NICHE,
        get_min_sample_count,
    )

    # Tous les MarketPrice avec leur seuil dynamique
    all_market = MarketPrice.query.order_by(MarketPrice.make, MarketPrice.model).all()
    insufficient_argus = []
    for mp in all_market:
        min_required = get_min_sample_count(mp.make, mp.model)
        if mp.sample_count < min_required:
            insufficient_argus.append(
                {
                    "make": mp.make,
                    "model": mp.model,
                    "year": mp.year,
                    "region": mp.region,
                    "fuel": mp.fuel,
                    "sample_count": mp.sample_count,
                    "min_required": min_required,
                    "deficit": min_required - mp.sample_count,
                    "price_median": mp.price_median,
                    "price_iqr_mean": mp.price_iqr_mean,
                    "precision": mp.precision,
                    "collected_at": mp.collected_at,
                }
            )

    # Vehicules du referentiel avec leur seuil configurable
    vehicle_thresholds = []
    for v in Vehicle.query.order_by(Vehicle.brand, Vehicle.model).all():
        from app.models.vehicle import VehicleSpec

        max_hp = (
            db.session.query(db.func.max(VehicleSpec.power_hp))
            .filter(VehicleSpec.vehicle_id == v.id, VehicleSpec.power_hp.isnot(None))
            .scalar()
        )
        dynamic_min = MIN_SAMPLE_COUNT
        if max_hp:
            if max_hp > 420:
                dynamic_min = MIN_SAMPLE_ULTRA_NICHE
            elif max_hp > 300:
                dynamic_min = MIN_SAMPLE_NICHE
        effective_min = v.argus_min_samples if v.argus_min_samples is not None else dynamic_min
        tier = "standard"
        if max_hp and max_hp > 420:
            tier = "ultra-niche"
        elif max_hp and max_hp > 300:
            tier = "niche"

        # Compter les MarketPrice pour ce vehicule
        from app.services.market_service import market_text_key, market_text_key_expr

        mp_count = MarketPrice.query.filter(
            market_text_key_expr(MarketPrice.make) == market_text_key(v.brand),
            market_text_key_expr(MarketPrice.model) == market_text_key(v.model),
        ).count()

        vehicle_thresholds.append(
            {
                "id": v.id,
                "brand": v.brand,
                "model": v.model,
                "max_hp": max_hp,
                "tier": tier,
                "dynamic_min": dynamic_min,
                "override": v.argus_min_samples,
                "effective_min": effective_min,
                "market_count": mp_count,
            }
        )

    # Validation LBC : comparer notre argus vs fourchette LBC
    for r in records:
        r._validation = None
        if r.lbc_estimate_low and r.lbc_estimate_high and r.price_iqr_mean:
            iqr = r.price_iqr_mean
            low, high = r.lbc_estimate_low, r.lbc_estimate_high
            if low <= iqr <= high:
                r._validation = "valid"
            elif iqr < low * 0.85 or iqr > high * 1.15:
                r._validation = "ecart"
            else:
                r._validation = "proche"

    # Stat globale validation
    validated = sum(
        1
        for r in all_market
        if r.lbc_estimate_low
        and r.lbc_estimate_high
        and r.price_iqr_mean
        and r.lbc_estimate_low <= r.price_iqr_mean <= r.lbc_estimate_high
    )
    total_with_lbc = sum(1 for r in all_market if r.lbc_estimate_low and r.lbc_estimate_high)
    validation_rate = round(validated / total_with_lbc * 100) if total_with_lbc > 0 else 0

    return render_template(
        "admin/argus.html",
        total_refs=total_refs,
        fresh_refs=fresh_refs,
        stale_refs=stale_refs,
        total_samples=total_samples,
        distinct_makes=distinct_makes,
        distinct_regions=distinct_regions,
        make_list=make_list,
        region_list=region_list,
        make_filter=make_filter,
        region_filter=region_filter,
        records=records,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
        now=now,
        insufficient_argus=insufficient_argus,
        vehicle_thresholds=vehicle_thresholds,
        validation_rate=validation_rate,
        total_with_lbc=total_with_lbc,
    )


@admin_bp.route("/vehicle/<int:vehicle_id>/argus-threshold", methods=["POST"])
@login_required
def set_argus_threshold(vehicle_id: int):
    """Override manuel du seuil minimum d'annonces pour l'argus d'un vehicule."""
    vehicle = db.session.get(Vehicle, vehicle_id) or abort(404)
    threshold_str = request.form.get("threshold", "").strip()

    if not threshold_str or threshold_str.lower() == "auto":
        vehicle.argus_min_samples = None
        db.session.commit()
        flash(
            f"{vehicle.brand} {vehicle.model} : seuil argus remis en automatique.",
            "success",
        )
    else:
        try:
            threshold = int(threshold_str)
            if threshold < 1 or threshold > 100:
                flash("Le seuil doit etre entre 1 et 100.", "error")
                return redirect(url_for("admin.argus"))
        except ValueError:
            flash("Seuil invalide (nombre entier attendu).", "error")
            return redirect(url_for("admin.argus"))

        vehicle.argus_min_samples = threshold
        db.session.commit()
        logger.info(
            "Argus threshold override: %s %s -> %d (admin '%s')",
            vehicle.brand,
            vehicle.model,
            threshold,
            current_user.username,
        )
        flash(
            f"{vehicle.brand} {vehicle.model} : seuil argus fixe a {threshold} annonces.",
            "success",
        )

    return redirect(url_for("admin.argus"))


# ── YouTube Tests ────────────────────────────────────────────────


@admin_bp.route("/youtube")
@login_required
def youtube():
    """Page d'administration des videos YouTube et transcripts."""
    # Filtres
    vehicle_filter = request.args.get("vehicle_id", "")
    status_filter = request.args.get("status", "")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 25

    # Stats globales
    total_videos = db.session.query(db.func.count(YouTubeVideo.id)).scalar() or 0
    total_transcripts = (
        db.session.query(db.func.count(YouTubeTranscript.id))
        .filter(YouTubeTranscript.status == "extracted")
        .scalar()
        or 0
    )
    total_chars = (
        db.session.query(db.func.coalesce(db.func.sum(YouTubeTranscript.char_count), 0))
        .filter(YouTubeTranscript.status == "extracted")
        .scalar()
    )

    # Couverture vehicules
    total_vehicle_count = db.session.query(db.func.count(Vehicle.id)).scalar() or 1
    vehicles_with_transcripts = (
        db.session.query(db.func.count(db.distinct(YouTubeVideo.vehicle_id)))
        .join(YouTubeVideo.transcript)
        .filter(YouTubeTranscript.status == "extracted")
        .scalar()
        or 0
    )
    coverage_pct = round(100 * vehicles_with_transcripts / total_vehicle_count)

    # Query filtree
    query = YouTubeVideo.query

    if vehicle_filter:
        query = query.filter(YouTubeVideo.vehicle_id == int(vehicle_filter))

    if status_filter == "archived":
        query = query.filter(YouTubeVideo.is_archived.is_(True))
    elif status_filter:
        query = query.filter(YouTubeVideo.is_archived.is_(False))
        query = query.join(YouTubeVideo.transcript).filter(
            YouTubeTranscript.status == status_filter
        )
    else:
        query = query.filter(YouTubeVideo.is_archived.is_(False))

    query = query.order_by(YouTubeVideo.created_at.desc())
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    videos = query.offset((page - 1) * per_page).limit(per_page).all()

    # Liste vehicules pour les dropdowns
    vehicle_list = Vehicle.query.order_by(Vehicle.brand, Vehicle.model).all()

    return render_template(
        "admin/youtube.html",
        total_videos=total_videos,
        total_transcripts=total_transcripts,
        total_chars=total_chars,
        coverage_pct=coverage_pct,
        vehicle_filter=vehicle_filter,
        status_filter=status_filter,
        videos=videos,
        vehicle_list=vehicle_list,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    )


@admin_bp.route("/youtube/<int:video_id>")
@login_required
def youtube_detail(video_id: int):
    """Page de detail d'une video YouTube."""
    video = db.session.get(YouTubeVideo, video_id) or abort(404)
    return render_template(
        "admin/youtube_detail.html",
        video=video,
        transcript=video.transcript,
    )


@admin_bp.route("/youtube/<int:video_id>/extract", methods=["POST"])
@login_required
def youtube_extract(video_id: int):
    """Extraction manuelle du transcript d'une video."""
    from app.services.youtube_service import extract_and_store_transcript

    video = db.session.get(YouTubeVideo, video_id) or abort(404)
    try:
        transcript = extract_and_store_transcript(video)
        if transcript.status == "extracted":
            flash(
                f'Transcript extrait pour "{video.title[:60]}" ({transcript.char_count} caracteres).',
                "success",
            )
        else:
            flash(
                f'Pas de sous-titres disponibles pour "{video.title[:60]}".',
                "warning",
            )
    except Exception as exc:
        flash(f"Erreur d'extraction : {exc}", "error")
        logger.exception("Erreur extraction transcript video %d", video_id)

    return redirect(request.referrer or url_for("admin.youtube"))


@admin_bp.route("/youtube/search", methods=["POST"])
@login_required
def youtube_search():
    """Recherche et extraction de videos pour un vehicule."""
    from app.services.youtube_service import search_and_extract_for_vehicle

    vehicle_id = request.form.get("vehicle_id", type=int)
    if not vehicle_id:
        flash("Veuillez selectionner un vehicule.", "error")
        return redirect(url_for("admin.youtube"))

    vehicle = db.session.get(Vehicle, vehicle_id) or abort(404)
    try:
        stats = search_and_extract_for_vehicle(vehicle, max_videos=5)
        flash(
            f"{vehicle.brand} {vehicle.model} : {stats['videos_found']} videos trouvees, "
            f"{stats['transcripts_ok']} transcripts extraits.",
            "success",
        )
    except Exception as exc:
        flash(f"Erreur de recherche : {exc}", "error")
        logger.exception("Erreur recherche YouTube pour vehicule %d", vehicle_id)

    return redirect(url_for("admin.youtube", vehicle_id=vehicle_id))


@admin_bp.route("/youtube/<int:video_id>/archive", methods=["POST"])
@login_required
def youtube_archive(video_id: int):
    """Toggle l'archivage d'une video."""
    video = db.session.get(YouTubeVideo, video_id) or abort(404)
    video.is_archived = not video.is_archived
    db.session.commit()

    action = "archivee" if video.is_archived else "restauree"
    flash(f'Video {action} : "{video.title[:60]}".', "success")
    return redirect(request.referrer or url_for("admin.youtube"))


@admin_bp.route("/youtube/<int:video_id>/featured", methods=["POST"])
@login_required
def youtube_featured(video_id: int):
    """Toggle le statut featured d'une video.

    Une seule video featured par vehicule : si on marque celle-ci,
    les autres du meme vehicule perdent leur featured.
    """
    video = db.session.get(YouTubeVideo, video_id) or abort(404)

    if video.is_featured:
        # Retirer le featured
        video.is_featured = False
        db.session.commit()
        flash(f'Video retiree du featured : "{video.title[:60]}".', "success")
    else:
        # Retirer le featured des autres videos du meme vehicule
        if video.vehicle_id:
            YouTubeVideo.query.filter(
                YouTubeVideo.vehicle_id == video.vehicle_id,
                YouTubeVideo.is_featured.is_(True),
            ).update({"is_featured": False})
        video.is_featured = True
        db.session.commit()
        flash(f'Video featured : "{video.title[:60]}".', "success")

    return redirect(request.referrer or url_for("admin.youtube"))


# ── YouTube Recherche Fine ────────────────────────────────────────

_DEFAULT_SYNTHESIS_PROMPT = (
    "Tu es un expert automobile francais. A partir des transcripts de tests "
    "YouTube ci-dessous, redige une synthese structuree du vehicule.\n\n"
    "Inclus:\n"
    "- Points forts (3-5)\n"
    "- Points faibles (3-5)\n"
    "- Fiabilite et problemes connus\n"
    "- A qui s'adresse ce vehicule\n"
    "- Verdict global\n\n"
    "Sois factuel et concis. Ne repete pas le contenu des transcripts mot pour mot."
)


def _build_vehicle_catalog() -> dict:
    """Construit le catalogue vehicules pour les selects en cascade.

    Retourne un dict JSON-serialisable :
    {brand: {model: {years: [2015, 2016, ...], hp: [90, 110, 130, ...]}}}
    """
    from app.models.vehicle import VehicleSpec

    catalog: dict[str, dict[str, dict]] = {}

    vehicles = Vehicle.query.order_by(Vehicle.brand, Vehicle.model).all()
    for v in vehicles:
        if v.brand not in catalog:
            catalog[v.brand] = {}

        # Annees depuis year_start/year_end
        years = []
        if v.year_start:
            end = v.year_end or datetime.now(timezone.utc).year
            years = list(range(v.year_start, end + 1))

        # Chevaux depuis VehicleSpec (valeurs uniques, triees)
        hp_rows = (
            db.session.query(db.distinct(VehicleSpec.power_hp))
            .filter(
                VehicleSpec.vehicle_id == v.id,
                VehicleSpec.power_hp.isnot(None),
            )
            .order_by(VehicleSpec.power_hp)
            .all()
        )
        hp_values = [row[0] for row in hp_rows]

        catalog[v.brand][v.model] = {"years": years, "hp": hp_values}

    return catalog


@admin_bp.route("/youtube/fine-search")
@login_required
def youtube_fine_search():
    """Page de recherche YouTube fine avec parametres vehicule et synthese LLM."""
    from app.services.llm_service import list_ollama_models

    catalog = _build_vehicle_catalog()
    brand_list = sorted(catalog.keys())
    ollama_models = list_ollama_models()
    syntheses = VehicleSynthesis.query.order_by(VehicleSynthesis.created_at.desc()).limit(20).all()

    return render_template(
        "admin/youtube_search.html",
        brand_list=brand_list,
        ollama_models=ollama_models,
        syntheses=syntheses,
        default_prompt=_DEFAULT_SYNTHESIS_PROMPT,
        form_data={},
        result=None,
        vehicle_catalog=catalog,
    )


@admin_bp.route("/youtube/fine-search", methods=["POST"])
@login_required
def youtube_fine_search_run():
    """Lance le pipeline en background et redirige vers la page avec job_id."""
    make = request.form.get("make", "").strip()
    model_name = request.form.get("model", "").strip()

    if not make or not model_name:
        flash("Marque et modele sont requis.", "error")
        return redirect(url_for("admin.youtube_fine_search"))

    # Creer le job
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "status": "running",
        "progress": 0,
        "progress_label": "Demarrage...",
        "pipeline_log": [],
        "videos_detail": [],
        "result": None,
        "cancelled": False,
        "form_data": {
            "make": make,
            "model": model_name,
            "year": request.form.get("year", "").strip(),
            "fuel": request.form.get("fuel", "").strip(),
            "hp": request.form.get("hp", "").strip(),
            "keywords": request.form.get("keywords", "").strip(),
            "focus_channel": request.form.get("focus_channel", "").strip(),
            "max_results": request.form.get("max_results", 5, type=int),
            "llm_model": request.form.get("llm_model", "").strip(),
            "prompt": request.form.get("prompt", "").strip() or _DEFAULT_SYNTHESIS_PROMPT,
        },
    }
    with _jobs_lock:
        _synthesis_jobs[job_id] = job

    # Lancer le pipeline en background thread
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_synthesis_pipeline,
        args=(app, job),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("admin.youtube_fine_search", job_id=job_id))


def _run_synthesis_pipeline(app, job: dict) -> None:
    """Execute le pipeline YouTube+LLM dans un thread background."""
    from app.services.llm_service import generate_synthesis
    from app.services.youtube_service import build_search_query, search_and_extract_custom

    fd = job["form_data"]

    def _log(step: int, label: str, status: str, detail: str) -> None:
        job["pipeline_log"].append(
            {
                "step": step,
                "label": label,
                "status": status,
                "detail": detail,
            }
        )

    def _is_cancelled() -> bool:
        return job.get("cancelled", False)

    with app.app_context():
        try:
            # ── Etape 1 : Vehicule dans le referentiel (10%) ──
            job["progress"] = 5
            job["progress_label"] = "Recherche vehicule..."
            vehicle = Vehicle.query.filter(
                Vehicle.brand.ilike(fd["make"]),
                Vehicle.model.ilike(fd["model"]),
            ).first()
            vehicle_id = vehicle.id if vehicle else None
            _log(
                1,
                "Recherche vehicule dans le referentiel",
                "ok" if vehicle else "warning",
                f"Trouve : {vehicle.brand} {vehicle.model} (id={vehicle.id})"
                if vehicle
                else f"{fd['make']} {fd['model']} non trouve (recherche libre)",
            )
            job["progress"] = 10
            if _is_cancelled():
                job["status"] = "cancelled"
                _log(0, "Pipeline annule", "error", "Annule par l'utilisateur")
                return

            # ── Etape 2 : Construction query (15%) ──
            job["progress_label"] = "Construction query YouTube..."
            year_int = int(fd["year"]) if fd["year"] else None
            query = build_search_query(
                make=fd["make"],
                model=fd["model"],
                year=year_int,
                fuel=fd["fuel"] or None,
                hp=fd["hp"] or None,
                keywords=fd["keywords"] or None,
            )
            _log(2, "Construction query YouTube", "ok", query)
            job["progress"] = 15
            if _is_cancelled():
                job["status"] = "cancelled"
                _log(0, "Pipeline annule", "error", "Annule par l'utilisateur")
                return

            # ── Etape 3 : Recherche YouTube (15% → 50%) ──
            job["progress_label"] = "Recherche YouTube en cours..."
            t0 = time.monotonic()
            try:
                # Convertir year en int si fourni
                year_int = None
                if fd.get("year"):
                    try:
                        year_int = int(fd["year"])
                    except ValueError:
                        pass

                # Parser les chaines a privilegier (comma-separated)
                focus_channels = []
                if fd.get("focus_channel"):
                    focus_channels = [
                        ch.strip() for ch in fd["focus_channel"].split(",") if ch.strip()
                    ]

                stats = search_and_extract_custom(
                    query,
                    vehicle_id=vehicle_id,
                    max_results=fd["max_results"],
                    vehicle_year=year_int,
                    focus_channels=focus_channels,
                )
            except Exception as exc:
                logger.exception("YouTube fine search failed: %s", exc)
                _log(3, "Recherche YouTube", "error", f"Erreur : {exc}")
                job["status"] = "error"
                job["progress"] = 100
                job["progress_label"] = "Erreur recherche YouTube"
                return
            search_duration = round(time.monotonic() - t0, 1)
            _log(
                3,
                f"Recherche YouTube ({search_duration}s)",
                "ok" if stats["videos_found"] > 0 else "warning",
                f"{stats['videos_found']} videos, {stats['transcripts_ok']} transcripts, "
                f"{stats.get('transcripts_failed', 0)} echecs",
            )
            job["progress"] = 50
            if _is_cancelled():
                job["status"] = "cancelled"
                _log(0, "Pipeline annule", "error", "Annule par l'utilisateur")
                return

            # ── Etape 4 : Detail videos (55%) ──
            job["progress_label"] = "Extraction details videos..."
            video_ids_db = stats.get("video_ids", [])
            videos_detail = []
            transcripts_parts = []
            for vid_id in video_ids_db:
                yt_video = db.session.get(YouTubeVideo, vid_id)
                if not yt_video:
                    continue
                has_transcript = yt_video.transcript and yt_video.transcript.status == "extracted"
                char_count = yt_video.transcript.char_count if has_transcript else 0
                videos_detail.append(
                    {
                        "title": yt_video.title,
                        "channel": yt_video.channel_name or "?",
                        "video_id": yt_video.video_id,
                        "url": f"https://www.youtube.com/watch?v={yt_video.video_id}",
                        "has_transcript": has_transcript,
                        "char_count": char_count,
                    }
                )
                if has_transcript:
                    header = f"--- {yt_video.title} ({yt_video.channel_name}) ---"
                    transcripts_parts.append(f"{header}\n{yt_video.transcript.full_text}")

            job["videos_detail"] = videos_detail
            total_chars = sum(len(p) for p in transcripts_parts)
            concatenated = "\n\n".join(transcripts_parts)
            _log(
                4,
                "Videos et transcripts",
                "ok" if transcripts_parts else "warning",
                f"{len(videos_detail)} videos, {len(transcripts_parts)} avec transcript",
            )
            job["progress"] = 55
            if _is_cancelled():
                job["status"] = "cancelled"
                _log(0, "Pipeline annule", "error", "Annule par l'utilisateur")
                return

            # ── Etape 5 : Synthese LLM (55% → 95%) ──
            synthesis_text = ""
            synthesis_id = None
            llm_duration = 0.0
            llm_model = fd["llm_model"]
            prompt = fd["prompt"]

            if concatenated and llm_model:
                job["progress_label"] = f"Generation LLM ({llm_model})..."
                _log(
                    5,
                    f"Envoi au LLM ({llm_model})",
                    "pending",
                    f"Prompt : {len(prompt)} chars, Input : {total_chars} chars",
                )
                t1 = time.monotonic()
                try:
                    synthesis_text = generate_synthesis(llm_model, prompt, concatenated)
                except ConnectionError as exc:
                    logger.error("Ollama synthesis failed: %s", exc)
                    synthesis_text = ""
                llm_duration = round(time.monotonic() - t1, 1)

                if _is_cancelled():
                    job["status"] = "cancelled"
                    _log(0, "Pipeline annule", "error", "Annule pendant la generation LLM")
                    job["progress"] = 100
                    return

                # Mettre a jour le log LLM
                job["pipeline_log"][-1] = {
                    "step": 5,
                    "label": f"Synthese LLM ({llm_duration}s)",
                    "status": "ok" if synthesis_text else "error",
                    "detail": (
                        f"{llm_model}, {len(synthesis_text)} chars en {llm_duration}s"
                        if synthesis_text
                        else f"Echec generation avec {llm_model}"
                    ),
                }
                job["progress"] = 90

                # Store VehicleSynthesis
                if synthesis_text:
                    synth = VehicleSynthesis(
                        vehicle_id=vehicle_id,
                        make=fd["make"],
                        model=fd["model"],
                        year=year_int,
                        fuel=fd["fuel"] or None,
                        llm_model=llm_model,
                        prompt_used=prompt,
                        source_video_ids=video_ids_db,
                        raw_transcript_chars=total_chars,
                        synthesis_text=synthesis_text,
                        status="draft",
                    )
                    db.session.add(synth)
                    db.session.commit()
                    synthesis_id = synth.id
                    _log(6, "Sauvegarde synthese", "ok", f"id={synth.id}, status=draft")
                    logger.info(
                        "Synthesis created: %s %s (id=%d, llm=%s, %d chars input)",
                        fd["make"],
                        fd["model"],
                        synth.id,
                        llm_model,
                        total_chars,
                    )
            elif not concatenated:
                _log(5, "Synthese LLM", "skip", "Aucun transcript, synthese impossible")

            # ── Termine ──
            job["progress"] = 100
            job["progress_label"] = "Termine"
            job["status"] = "done"
            job["result"] = {
                "videos_found": stats["videos_found"],
                "transcripts_ok": stats["transcripts_ok"],
                "total_chars": total_chars,
                "query": query,
                "synthesis_text": synthesis_text,
                "synthesis_id": synthesis_id,
                "llm_model": llm_model,
                "llm_duration": llm_duration,
                "search_duration": search_duration,
                "prompt_used": prompt,
            }
        except Exception as exc:
            logger.exception("Pipeline background thread failed: %s", exc)
            job["pipeline_log"].append(
                {
                    "step": 0,
                    "label": "Erreur fatale",
                    "status": "error",
                    "detail": str(exc),
                }
            )
            job["status"] = "error"
            job["progress"] = 100
            job["progress_label"] = f"Erreur : {exc}"


@admin_bp.route("/youtube/job-status/<job_id>")
@login_required
def youtube_job_status(job_id: str):
    """API JSON pour le polling du statut d'un job pipeline."""
    with _jobs_lock:
        job = _synthesis_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify(
        {
            "id": job["id"],
            "status": job["status"],
            "progress": job["progress"],
            "progress_label": job["progress_label"],
            "pipeline_log": job["pipeline_log"],
            "videos_detail": job["videos_detail"],
            "result": job["result"],
            "form_data": job["form_data"],
        }
    )


@admin_bp.route("/youtube/job-stop/<job_id>", methods=["POST"])
@login_required
def youtube_job_stop(job_id: str):
    """Annule un job pipeline en cours."""
    with _jobs_lock:
        job = _synthesis_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job introuvable"}), 404
    job["cancelled"] = True
    return jsonify({"ok": True, "message": "Annulation demandee"})


@admin_bp.route("/youtube/synthesis/<int:synthesis_id>/validate", methods=["POST"])
@login_required
def youtube_synthesis_validate(synthesis_id: int):
    """Toggle la synthese de draft vers validated."""
    synth = db.session.get(VehicleSynthesis, synthesis_id) or abort(404)
    if synth.status == "draft":
        synth.status = "validated"
        db.session.commit()
        flash(f"Synthese {synth.make} {synth.model} validee.", "success")
    else:
        flash("Cette synthese n'est pas en draft.", "warning")
    return redirect(url_for("admin.youtube_fine_search"))


# ── Issues collecte (CollectionJob queue) ─────────────────────────


@admin_bp.route("/issues")
@login_required
def issues():
    """File d'attente des collectes argus (CollectionJob queue)."""
    from app.models.collection_job import CollectionJob

    status_filter = request.args.get("status", "").strip()
    make_filter = request.args.get("make", "").strip()
    priority_filter = request.args.get("priority", "", type=str).strip()
    page = request.args.get("page", 1, type=int)

    # Stats
    pending = CollectionJob.query.filter_by(status="pending").count()
    assigned = CollectionJob.query.filter_by(status="assigned").count()
    done = CollectionJob.query.filter_by(status="done").count()
    failed = CollectionJob.query.filter_by(status="failed").count()
    total = pending + assigned + done + failed
    completion_rate = round(done / total * 100) if total > 0 else 0

    # Query
    query = CollectionJob.query.order_by(
        CollectionJob.priority.asc(), CollectionJob.created_at.desc()
    )
    if status_filter:
        query = query.filter(CollectionJob.status == status_filter)
    if make_filter:
        query = query.filter(CollectionJob.make == make_filter)
    if priority_filter:
        query = query.filter(CollectionJob.priority == int(priority_filter))

    per_page = 50
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    make_list = [
        r[0]
        for r in db.session.query(CollectionJob.make).distinct().order_by(CollectionJob.make).all()
    ]

    return render_template(
        "admin/issues.html",
        pending=pending,
        assigned=assigned,
        done=done,
        failed=failed,
        total=total,
        completion_rate=completion_rate,
        records=records,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
        status_filter=status_filter,
        make_filter=make_filter,
        priority_filter=priority_filter,
        make_list=make_list,
    )


@admin_bp.route("/issues/purge-failed", methods=["POST"])
@login_required
def purge_failed_jobs():
    """Reset all failed jobs back to pending."""
    from app.models.collection_job import CollectionJob

    count = CollectionJob.query.filter_by(status="failed").update(
        {"status": "pending", "attempts": 0}
    )
    db.session.commit()
    flash(f"{count} jobs echoues remis en attente.", "success")
    return redirect(url_for("admin.issues"))


# ── Failed Searches (diagnostic URLs) ────────────────────────────


@admin_bp.route("/failed-searches")
@login_required
def failed_searches():
    """Page d'inspection des recherches LBC echouees (0 annonces)."""
    from app.models.failed_search import FailedSearch

    resolved_filter = request.args.get("resolved", "")
    make_filter = request.args.get("make", "").strip()
    page = request.args.get("page", 1, type=int)

    # Stats
    total = FailedSearch.query.count()
    unresolved = FailedSearch.query.filter_by(resolved=False).count()
    resolved = FailedSearch.query.filter_by(resolved=True).count()

    # Token source breakdown
    from sqlalchemy import func as sqla_func

    source_stats = dict(
        db.session.query(FailedSearch.token_source, sqla_func.count())
        .group_by(FailedSearch.token_source)
        .all()
    )

    # Query
    query = FailedSearch.query.order_by(FailedSearch.created_at.desc())
    if resolved_filter == "0":
        query = query.filter(FailedSearch.resolved.is_(False))
    elif resolved_filter == "1":
        query = query.filter(FailedSearch.resolved.is_(True))
    if make_filter:
        query = query.filter(FailedSearch.make == make_filter)

    per_page = 50
    total_results = query.count()
    total_pages = max(1, (total_results + per_page - 1) // per_page)
    page = min(page, total_pages)
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    make_list = [
        r[0]
        for r in db.session.query(FailedSearch.make).distinct().order_by(FailedSearch.make).all()
    ]

    return render_template(
        "admin/failed_searches.html",
        total=total,
        unresolved=unresolved,
        resolved_count=resolved,
        source_stats=source_stats,
        records=records,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
        resolved_filter=resolved_filter,
        make_filter=make_filter,
        make_list=make_list,
    )


@admin_bp.route("/failed-searches/<int:fs_id>/resolve", methods=["POST"])
@login_required
def resolve_failed_search(fs_id):
    """Marquer une recherche echouee comme resolue."""
    from app.models.failed_search import FailedSearch

    fs = db.session.get(FailedSearch, fs_id)
    if not fs:
        abort(404)
    fs.resolved = True
    fs.resolved_note = request.form.get("note", "")
    db.session.commit()
    flash(f"Recherche {fs.make} {fs.model} marquee comme resolue.", "success")
    return redirect(url_for("admin.failed_searches"))


# ── LLM Google Gemini ─────────────────────────────────────────────


@admin_bp.route("/llm")
@login_required
def llm_config():
    """Page de configuration et monitoring du LLM Google Gemini."""
    from sqlalchemy import func

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # Stats du jour
    today_usage = (
        db.session.query(
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.total_tokens), 0),
            func.coalesce(func.sum(LLMUsage.estimated_cost_eur), 0.0),
        )
        .filter(LLMUsage.created_at >= today)
        .first()
    )

    requests_today = today_usage[0]
    tokens_today = today_usage[1]
    cost_today = today_usage[2]

    # Config Gemini
    gemini_cfg = GeminiConfig.query.first()

    # Prompts
    prompts = GeminiPromptConfig.query.order_by(GeminiPromptConfig.created_at.desc()).all()

    # Health check
    api_ok = False
    if gemini_cfg and gemini_cfg.is_active:
        from app.services import gemini_service

        api_ok = gemini_service.check_health()

    # Historique 7 jours
    week_ago = today - timedelta(days=7)
    daily_usage_rows = (
        db.session.query(
            func.date(LLMUsage.created_at),
            func.sum(LLMUsage.total_tokens),
            func.sum(LLMUsage.estimated_cost_eur),
            func.count(LLMUsage.id),
        )
        .filter(
            LLMUsage.created_at >= week_ago,
        )
        .group_by(func.date(LLMUsage.created_at))
        .all()
    )
    daily_usage = [
        [str(row[0]), int(row[1] or 0), float(row[2] or 0), int(row[3])] for row in daily_usage_rows
    ]

    return render_template(
        "admin/llm.html",
        requests_today=requests_today,
        tokens_today=tokens_today,
        cost_today=round(cost_today, 4),
        api_ok=api_ok,
        gemini_config=gemini_cfg,
        prompts=prompts,
        daily_usage=daily_usage,
        max_daily_requests=gemini_cfg.max_daily_requests if gemini_cfg else 500,
        max_daily_cost=gemini_cfg.max_daily_cost_eur if gemini_cfg else 1.0,
    )


@admin_bp.route("/llm/config", methods=["POST"])
@login_required
def llm_config_save():
    """Sauvegarde la configuration Gemini."""
    gemini_cfg = GeminiConfig.query.first()
    if not gemini_cfg:
        gemini_cfg = GeminiConfig(
            api_key_encrypted="",
            model_name="gemini-2.5-flash",
        )
        db.session.add(gemini_cfg)

    api_key = request.form.get("api_key", "").strip()
    if api_key:
        gemini_cfg.api_key_encrypted = api_key

    gemini_cfg.model_name = request.form.get("model_name", "gemini-2.5-flash")
    gemini_cfg.max_daily_requests = int(request.form.get("max_daily_requests", 500))
    gemini_cfg.max_daily_cost_eur = float(request.form.get("max_daily_cost_eur", 1.0))
    gemini_cfg.is_active = request.form.get("is_active") == "on"

    db.session.commit()
    flash("Configuration Gemini sauvegardee.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/prompt/new", methods=["POST"])
@login_required
def llm_prompt_new():
    """Cree un nouveau prompt Gemini."""
    prompt = GeminiPromptConfig(
        name=request.form.get("name", "nouveau_prompt"),
        system_prompt=request.form.get("system_prompt", ""),
        task_prompt_template=request.form.get("task_prompt_template", ""),
        max_output_tokens=int(request.form.get("max_output_tokens", 500)),
        temperature=float(request.form.get("temperature", 0.3)),
        top_p=float(request.form.get("top_p", 0.9)),
        hallucination_guard=request.form.get("hallucination_guard", ""),
        max_sentences=int(request.form.get("max_sentences", 0)) or None,
        is_active=False,
        version=1,
    )
    db.session.add(prompt)
    db.session.commit()
    flash("Prompt cree.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/prompt/<int:prompt_id>/activate", methods=["POST"])
@login_required
def llm_prompt_activate(prompt_id):
    """Active un prompt et desactive les autres."""
    GeminiPromptConfig.query.update({"is_active": False})
    prompt = db.session.get(GeminiPromptConfig, prompt_id)
    if prompt:
        prompt.is_active = True
    db.session.commit()
    flash("Prompt active.", "success")
    return redirect(url_for("admin.llm_config"))


@admin_bp.route("/llm/test", methods=["POST"])
@login_required
def llm_test():
    """Teste l'API Gemini avec un prompt de test."""
    from app.services import gemini_service

    test_prompt = request.form.get("test_prompt", "Dis bonjour en une phrase.")
    try:
        text, tokens = gemini_service.generate_text(
            prompt=test_prompt,
            feature="admin_test",
            temperature=0.3,
            max_output_tokens=100,
        )
        return jsonify({"success": True, "response": text, "tokens": tokens})
    except (ValueError, ConnectionError) as exc:
        return jsonify({"success": False, "error": str(exc)})


# ── Emails Vendeur ────────────────────────────────────────────────


@admin_bp.route("/email")
@login_required
def email_list():
    """Liste des brouillons d'emails vendeur."""
    from sqlalchemy import func

    status_filter = request.args.get("status", "")
    seller_filter = request.args.get("seller_type", "")

    query = EmailDraft.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if seller_filter:
        query = query.filter_by(seller_type=seller_filter)

    drafts = query.order_by(EmailDraft.created_at.desc()).limit(100).all()

    total_drafts = EmailDraft.query.filter_by(status="draft").count()
    total_approved = EmailDraft.query.filter_by(status="approved").count()
    total_sent = EmailDraft.query.filter_by(status="sent").count()
    avg_tokens = db.session.query(func.avg(EmailDraft.tokens_used)).scalar() or 0

    return render_template(
        "admin/email_list.html",
        drafts=drafts,
        total_drafts=total_drafts,
        total_approved=total_approved,
        total_sent=total_sent,
        avg_tokens=round(avg_tokens),
        status_filter=status_filter,
        seller_filter=seller_filter,
    )


@admin_bp.route("/email/<int:draft_id>")
@login_required
def email_detail(draft_id):
    """Detail d'un brouillon d'email."""
    draft = db.session.get(EmailDraft, draft_id)
    if not draft:
        flash("Brouillon introuvable.", "error")
        return redirect(url_for("admin.email_list"))
    scan = db.session.get(ScanLog, draft.scan_id)
    filters = FilterResultDB.query.filter_by(scan_id=draft.scan_id).all() if scan else []

    return render_template(
        "admin/email_detail.html",
        draft=draft,
        scan=scan,
        filters=filters,
    )


@admin_bp.route("/email/<int:draft_id>/regenerate", methods=["POST"])
@login_required
def email_regenerate(draft_id):
    """Regenere un email avec Gemini."""
    draft = db.session.get(EmailDraft, draft_id)
    if not draft:
        flash("Brouillon introuvable.", "error")
        return redirect(url_for("admin.email_list"))
    from app.services import email_service

    try:
        new_draft = email_service.generate_email_draft(draft.scan_id)
        flash("Email regenere.", "success")
        return redirect(url_for("admin.email_detail", draft_id=new_draft.id))
    except (ValueError, ConnectionError) as exc:
        flash(f"Erreur: {exc}", "error")
        return redirect(url_for("admin.email_detail", draft_id=draft_id))


@admin_bp.route("/email/<int:draft_id>/approve", methods=["POST"])
@login_required
def email_approve(draft_id):
    """Approuve un brouillon."""
    draft = db.session.get(EmailDraft, draft_id)
    if not draft:
        flash("Brouillon introuvable.", "error")
        return redirect(url_for("admin.email_list"))
    edited = request.form.get("edited_text", "").strip()
    if edited:
        draft.edited_text = edited
    draft.status = "approved"
    db.session.commit()
    flash("Email approuve.", "success")
    return redirect(url_for("admin.email_detail", draft_id=draft_id))


@admin_bp.route("/email/<int:draft_id>/archive", methods=["POST"])
@login_required
def email_archive(draft_id):
    """Archive un brouillon."""
    draft = db.session.get(EmailDraft, draft_id)
    if not draft:
        flash("Brouillon introuvable.", "error")
        return redirect(url_for("admin.email_list"))
    draft.status = "archived"
    db.session.commit()
    flash("Email archive.", "success")
    return redirect(url_for("admin.email_list"))


# ── Initialisation admin ─────────────────────────────────────────


def ensure_admin_user():
    """Cree l'utilisateur admin s'il n'existe pas encore."""
    username = current_app.config.get("ADMIN_USERNAME", "malik")
    password_hash = current_app.config.get("ADMIN_PASSWORD_HASH", "")

    if not password_hash:
        # Dev uniquement : generer un hash par defaut (bloque en prod par create_app)
        logger.warning("ADMIN_PASSWORD_HASH non defini -- utilisation d'un mot de passe dev")
        password_hash = generate_password_hash("dev-password-change-me")

    existing = User.query.filter_by(username=username).first()
    if not existing:
        user = User(username=username, password_hash=password_hash, is_admin=True)
        db.session.add(user)
        db.session.commit()
        logger.info("Utilisateur admin '%s' cree", username)
