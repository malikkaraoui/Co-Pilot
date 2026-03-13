"""Configuration de la journalisation pour OKazCar.

Configure le logging standard Python avec un handler console sur stdout.
Le DBHandler (persistence des logs WARNING+ en base) est branche
separement dans create_app() pour avoir acces au contexte Flask.
"""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure le logger racine de l'application.

    Appele une seule fois au demarrage par create_app().
    On n'ajoute un handler que si le root logger n'en a pas deja,
    pour eviter les doublons quand les tests creent plusieurs apps.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    # Pas de handler existant = premier demarrage, on en cree un
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
