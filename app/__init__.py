"""Fabrique d'application Flask pour OKazCar.

Tout passe par create_app() : config, extensions, blueprints, securite.
On utilise le pattern "application factory" de Flask pour pouvoir creer
des instances distinctes (prod, test) sans effets de bord globaux.
"""

import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Flask, send_from_directory

from app.extensions import cors, csrf, db, limiter, login_manager
from app.logging_config import setup_logging
from app.version import get_version
from config import config_by_name

_PARIS_TZ = ZoneInfo("Europe/Paris")


def _to_paris(dt: datetime) -> datetime:
    """Convertit un datetime UTC (ou naive UTC) en heure de Paris.

    Tous les timestamps en base sont stockes en UTC. Ce helper
    est utilise par les filtres Jinja pour afficher l'heure locale
    dans le dashboard admin.
    """
    if dt is None:
        return dt
    utc_dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    return utc_dt.astimezone(_PARIS_TZ)


logger = logging.getLogger(__name__)


def create_app(config_name: str | None = None) -> Flask:
    """Cree et configure l'application Flask.

    Etapes dans l'ordre :
      1. Charger la config (dev/test/prod)
      2. Verifier les secrets en prod
      3. Init extensions (DB, CORS, CSRF, rate limiter, login)
      4. Brancher le DBHandler pour persister les logs WARNING+ en base
      5. Enregistrer les blueprints (API + admin)
      6. Creer les tables et l'utilisateur admin si besoin

    Args:
        config_name: Un parmi 'development', 'testing', 'production'.
                     Par defaut, utilise la variable d'env FLASK_ENV ou 'development'.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Garde-fous production : on refuse de demarrer sans secrets
    # pour eviter de se retrouver en prod avec la cle de dev
    if config_name == "production":
        if app.config["SECRET_KEY"] == "dev-only-insecure-key":
            raise RuntimeError(
                "SECRET_KEY non definie. Definir la variable d'environnement SECRET_KEY."
            )
        if not app.config.get("ADMIN_PASSWORD_HASH"):
            raise RuntimeError(
                "ADMIN_PASSWORD_HASH non defini. Definir la variable d'environnement."
            )

    app.config["APP_VERSION"] = get_version()

    setup_logging(app.config.get("LOG_LEVEL", "INFO"))

    # Initialisation des extensions — elles ont ete instanciees dans extensions.py
    # et sont maintenant liees a cette app specifique
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])
    csrf.init_app(app)
    limiter.init_app(app)

    # Headers de securite HTTP — bonne pratique OWASP, on les met par defaut
    # sur toutes les reponses
    @app.after_request
    def add_security_headers(resp):
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    # DBHandler : persiste WARNING/ERROR dans app_logs pour le dashboard admin.
    # Desactive en tests pour eviter le bruit et les problemes de transaction.
    if not app.config.get("TESTING"):
        from app.logging_db import DBHandler

        db_handler = DBHandler(app=app, level=logging.WARNING)
        db_handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logging.getLogger().addHandler(db_handler)

    # User loader pour Flask-Login — retrouve l'admin par son ID de session
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Filtres Jinja pour afficher les dates en heure de Paris dans les templates
    @app.template_filter("localtime")
    def localtime_filter(dt):
        return _to_paris(dt) if dt else dt

    @app.template_filter("localdatetime")
    def localdatetime_filter(dt, fmt="%d/%m/%Y %H:%M"):
        """Convertit UTC -> Paris et formate. Retourne '-' si None."""
        if dt is None:
            return "-"
        return _to_paris(dt).strftime(fmt)

    # Enregistrement des blueprints
    from app.admin import admin_bp
    from app.api import api_bp

    # Les routes API recoivent du JSON depuis l'extension Chrome, pas des formulaires,
    # donc le CSRF n'a pas de sens ici (et bloquerait les requetes)
    csrf.exempt(api_bp)

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Page d'accueil publique — juste un placeholder, l'app vit dans l'extension
    @app.route("/")
    def home():
        return (
            "<html><head><title>OKazCar</title></head>"
            "<body style='font-family:system-ui;max-width:600px;margin:4rem auto;text-align:center'>"
            "<h1>OKazCar</h1>"
            "<p>Analysez vos annonces auto en 1 clic.</p>"
            "<p><a href='/privacy'>Politique de confidentialite</a></p>"
            "</body></html>"
        )

    # Privacy policy statique — obligatoire pour la publication Chrome Web Store
    @app.route("/privacy")
    def privacy_policy():
        return send_from_directory(app.static_folder, "privacy-policy.html")

    # Bootstrap de la DB : creer les tables et l'admin au premier lancement
    with app.app_context():
        from app.admin.routes import ensure_admin_user

        db.create_all()
        ensure_admin_user()

    logger.info("OKazCar app created with config '%s'", config_name)
    return app
