"""Configuration de la journalisation pour Co-Pilot.

Configure le logging standard Python avec un handler console.
Un DBHandler pour le tableau de bord admin sera ajoute dans une story ulterieure.
"""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure le logger racine de l'application."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
