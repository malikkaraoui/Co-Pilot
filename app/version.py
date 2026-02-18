"""Gestion du numero de version de l'application."""

import os

_VERSION_CACHE: str | None = None


def get_version() -> str:
    """Lit le numero de version depuis le fichier VERSION a la racine du projet."""
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE

    version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
    try:
        with open(version_file) as f:
            _VERSION_CACHE = f.read().strip()
    except FileNotFoundError:
        _VERSION_CACHE = "0.0.0"
    return _VERSION_CACHE
