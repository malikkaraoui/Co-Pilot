"""Routes du blueprint admin : login, dashboard, vehicules, erreurs, pipelines."""

import json
import logging
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.admin import admin_bp
from app.extensions import db
from app.models.filter_result import FilterResultDB
from app.models.log import AppLog
from app.models.pipeline_run import PipelineRun
from app.models.scan import ScanLog
from app.models.user import User
from app.models.vehicle import Vehicle

logger = logging.getLogger(__name__)


# ── Authentification ────────────────────────────────────────────


@admin_bp.route("/login", methods=["GET", "POST"])
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
    now = datetime.now(timezone.utc)
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

    # Top 10 vehicules analyses
    top_vehicles = (
        db.session.query(
            ScanLog.vehicle_make,
            ScanLog.vehicle_model,
            db.func.count(ScanLog.id).label("count"),
        )
        .filter(ScanLog.vehicle_make.isnot(None))
        .group_by(ScanLog.vehicle_make, ScanLog.vehicle_model)
        .order_by(db.func.count(ScanLog.id).desc())
        .limit(10)
        .all()
    )

    # 10 derniers scans
    recent_scans = ScanLog.query.order_by(ScanLog.created_at.desc()).limit(10).all()

    # Prix du marche crowdsources
    from app.models.market_price import MarketPrice

    market_total = db.session.query(db.func.count(MarketPrice.id)).scalar() or 0
    market_fresh = (
        db.session.query(db.func.count(MarketPrice.id))
        .filter(MarketPrice.refresh_after > now)
        .scalar()
        or 0
    )
    market_total_samples = db.session.query(db.func.sum(MarketPrice.sample_count)).scalar() or 0
    recent_market = MarketPrice.query.order_by(MarketPrice.collected_at.desc()).limit(10).all()

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
        market_total=market_total,
        market_fresh=market_fresh,
        market_total_samples=market_total_samples,
        recent_market=recent_market,
        now=now,
    )


# ── Vehicules non reconnus ──────────────────────────────────────


@admin_bp.route("/car")
@login_required
def car():
    """Modeles vehicules les plus demandes mais non reconnus."""
    # Filtres L2 avec status "warning" = modele non reconnu
    unrecognized = (
        db.session.query(
            FilterResultDB.details,
            db.func.count(FilterResultDB.id).label("count"),
        )
        .filter(
            FilterResultDB.filter_id == "L2",
            FilterResultDB.status == "warning",
        )
        .group_by(FilterResultDB.details)
        .order_by(db.func.count(FilterResultDB.id).desc())
        .limit(20)
        .all()
    )

    # Extraire marque/modele des details JSON
    unrecognized_models = []
    for row in unrecognized:
        details = row.details if isinstance(row.details, dict) else {}
        brand = details.get("brand", "?")
        model = details.get("model", "?")
        unrecognized_models.append(
            {
                "brand": brand,
                "model": model,
                "count": row.count,
            }
        )

    # Vehicules reconnus dans le referentiel
    known_vehicles = Vehicle.query.order_by(Vehicle.brand, Vehicle.model).all()

    return render_template(
        "admin/car.html",
        unrecognized_models=unrecognized_models,
        known_vehicles=known_vehicles,
    )


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
    last_yt = _last_run("youtube_whisper")
    last_llm = _last_run("llm_fiches")

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
            "name": "YouTube / Whisper",
            "description": "Extraction sous-titres et transcription",
            "count": 0,
            "status": "non lance" if not last_yt else last_yt.status,
            "last_run": last_yt.started_at if last_yt else None,
            "runs": _run_counts("youtube_whisper"),
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
        "description": "Verifie si la marque/modele existe dans le referentiel vehicules Co-Pilot.",
        "data_source": "Referentiel vehicules (base locale)",
        "data_source_type": "real",
        "maturity": 80,
        "maturity_note": "Referentiel a enrichir (52 modeles actuellement, objectif 200+)",
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
        "description": "Compare le prix de l'annonce aux donnees argus geolocalisees "
        "pour detecter les anomalies de prix.",
        "data_source": "Crowdsource LeBonCoin (fallback seed data)",
        "data_source_type": "simulated",
        "maturity": 40,
        "maturity_note": "Crowdsourcing via extension implemente. Fallback sur seed (39 prix) "
        "tant que pas assez de donnees reelles collectees.",
    },
    {
        "id": "L5",
        "name": "Analyse statistique",
        "description": "Analyse par z-scores NumPy pour detecter les prix outliers "
        "par rapport a la distribution de reference.",
        "data_source": "Crowdsource LeBonCoin (fallback seed data)",
        "data_source_type": "simulated",
        "maturity": 40,
        "maturity_note": "Crowdsourcing via extension implemente. Fallback sur seed "
        "tant que pas assez de donnees reelles collectees.",
    },
    {
        "id": "L6",
        "name": "Telephone",
        "description": "Analyse le numero de telephone : format francais, "
        "mobile/fixe, indicatif etranger.",
        "data_source": "Donnees de l'annonce",
        "data_source_type": "real",
        "maturity": 100,
        "maturity_note": "Validation regex, aucune donnee externe",
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
        "indicatif etranger, anomalie de prix.",
        "data_source": "Donnees de l'annonce + heuristiques",
        "data_source_type": "real",
        "maturity": 85,
        "maturity_note": "Heuristique prix < 3000 EUR trop simpliste, "
        "a affiner avec des seuils par segment",
    },
    {
        "id": "L9",
        "name": "Evaluation globale",
        "description": "Evalue les signaux de confiance transversaux : qualite de "
        "description, type de vendeur, completude.",
        "data_source": "Donnees de l'annonce + resultats des autres filtres",
        "data_source_type": "real",
        "maturity": 90,
        "maturity_note": "Pourrait integrer plus de signaux (photos, historique vendeur)",
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

    # Cartes resume
    total_filters = len(_FILTER_META)
    real_count = sum(1 for f in _FILTER_META if f["data_source_type"] == "real")
    simulated_count = total_filters - real_count
    avg_maturity = round(
        sum(f["maturity"] for f in _FILTER_META) / total_filters,
    )

    return render_template(
        "admin/filters.html",
        filter_meta=_FILTER_META,
        filter_stats=filter_stats,
        total_filters=total_filters,
        real_count=real_count,
        simulated_count=simulated_count,
        avg_maturity=avg_maturity,
    )


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
