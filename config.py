"""Classes de configuration pour l'application Co-Pilot."""

import os
import tempfile
from pathlib import Path

basedir = Path(__file__).resolve().parent


class Config:
    """Configuration de base (production)."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{basedir / 'data' / 'copilot.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # CORS -- uniquement l'origine de l'extension Chrome
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "chrome-extension://*").split(",")

    # Identifiants admin
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "malik")
    ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")

    # API externes
    SIRET_API_TIMEOUT = int(os.environ.get("SIRET_API_TIMEOUT", "5"))

    # Journalisation
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


class DevConfig(Config):
    """Configuration de developpement."""

    DEBUG = True
    LOG_LEVEL = "DEBUG"
    CORS_ORIGINS = ["*"]


class TestConfig(Config):
    """Configuration de test."""

    TESTING = True
    # Fichier temporaire au lieu de :memory: car FilterEngine utilise
    # ThreadPoolExecutor et SQLite in-memory ne supporte pas les acces
    # concurrents meme avec StaticPool.
    _test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{_test_db.name}"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
    }
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    LOG_LEVEL = "DEBUG"


config_by_name = {
    "development": DevConfig,
    "testing": TestConfig,
    "production": Config,
}
