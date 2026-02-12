"""Fabrique d'application Flask pour Co-Pilot."""

import logging
import os

from flask import Flask

from app.extensions import cors, db, login_manager
from app.logging_config import setup_logging
from config import config_by_name

logger = logging.getLogger(__name__)


def create_app(config_name: str | None = None) -> Flask:
    """Cree et configure l'application Flask.

    Args:
        config_name: Un parmi 'development', 'testing', 'production'.
                     Par defaut, utilise la variable d'env FLASK_ENV ou 'development'.
    """
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Garde-fous production : interdire les secrets par defaut
    if config_name == "production":
        if app.config["SECRET_KEY"] == "dev-only-insecure-key":
            raise RuntimeError(
                "SECRET_KEY non definie. Definir la variable d'environnement SECRET_KEY."
            )
        if not app.config.get("ADMIN_PASSWORD_HASH"):
            raise RuntimeError(
                "ADMIN_PASSWORD_HASH non defini. Definir la variable d'environnement."
            )

    setup_logging(app.config.get("LOG_LEVEL", "INFO"))

    # Initialisation des extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])

    # User loader pour Flask-Login
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Enregistrement des blueprints
    from app.admin import admin_bp
    from app.api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Creer l'utilisateur admin s'il n'existe pas
    with app.app_context():
        from app.admin.routes import ensure_admin_user

        db.create_all()
        ensure_admin_user()

    logger.info("Co-Pilot app created with config '%s'", config_name)
    return app
