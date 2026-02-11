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

    setup_logging(app.config.get("LOG_LEVEL", "INFO"))

    # Initialisation des extensions
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin.login"
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])

    # Enregistrement des blueprints
    from app.api import api_bp

    app.register_blueprint(api_bp, url_prefix="/api")

    logger.info("Co-Pilot app created with config '%s'", config_name)
    return app
