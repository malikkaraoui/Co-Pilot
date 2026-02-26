"""Extensions Flask -- instanciees ici, initialisees dans create_app()."""

import unicodedata

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
login_manager = LoginManager()
cors = CORS()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def _sqlite_strip_accents(text: str | None) -> str | None:
    """Fonction SQLite custom : supprime les accents/diacritiques.

    Necessaire car SQLite lower() ne gere que ASCII (A-Z → a-z).
    Sans cela, lower('Î') reste 'Î' au lieu de devenir 'i',
    ce qui casse les comparaisons case-insensitive pour les regions
    comme Île-de-France.
    """
    if text is None:
        return None
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@event.listens_for(Engine, "connect")
def _register_sqlite_functions(dbapi_conn, _connection_record):
    """Enregistre les fonctions custom SQLite a chaque nouvelle connexion."""
    if hasattr(dbapi_conn, "create_function"):
        dbapi_conn.create_function("strip_accents", 1, _sqlite_strip_accents)
