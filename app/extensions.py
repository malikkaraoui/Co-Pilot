"""Extensions Flask -- instanciees ici, initialisees dans create_app().

On suit le pattern classique Flask : les extensions sont creees au niveau
du module (sans app), puis liees a l'app via init_app() dans la factory.
Ca permet d'importer ``db``, ``limiter``, etc. depuis n'importe ou sans
import circulaire.
"""

import unicodedata

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.services.vehicle_lookup_keys import lookup_compact_key

# Extensions globales — on les importe dans __init__.py pour les init
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


def _sqlite_vehicle_lookup_key(text: str | None) -> str | None:
    """Produit une cle compacte de lookup vehicule.

    Permet de retrouver un vehicule dans la DB meme si l'annonce
    ecrit le modele differemment (tirets, espaces, casse...).
    Delegue la logique a lookup_compact_key() pour rester DRY.
    """
    if text is None:
        return None
    return lookup_compact_key(text)


@event.listens_for(Engine, "connect")
def _register_sqlite_functions(dbapi_conn, _connection_record):
    """Enregistre nos fonctions custom a chaque nouvelle connexion SQLite.

    SQLAlchemy cree potentiellement plusieurs connexions (pool), donc
    on doit re-enregistrer sur chacune. Le listener "connect" est
    appele automatiquement par SQLAlchemy.
    """
    if hasattr(dbapi_conn, "create_function"):
        dbapi_conn.create_function("strip_accents", 1, _sqlite_strip_accents)
        dbapi_conn.create_function("vehicle_lookup_key", 1, _sqlite_vehicle_lookup_key)
