"""Classes de configuration pour l'application Co-Pilot."""

import os
from pathlib import Path

from sqlalchemy.pool import StaticPool

basedir = Path(__file__).resolve().parent


class Config:
    """Configuration de base."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
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


class TestConfig(Config):
    """Configuration de test."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # StaticPool partage une connexion unique entre les threads
    # (necessaire car FilterEngine utilise ThreadPoolExecutor)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    WTF_CSRF_ENABLED = False
    LOG_LEVEL = "DEBUG"


config_by_name = {
    "development": DevConfig,
    "testing": TestConfig,
    "production": Config,
}
