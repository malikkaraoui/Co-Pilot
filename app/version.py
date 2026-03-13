"""Gestion du numero de version de l'application.

La version est lue depuis le fichier VERSION a la racine du projet.
Ce fichier est la source de verite unique — package.json et manifest.json
doivent rester synchronises (voir scripts/bump-version.sh).
"""

import os

# Cache module-level pour eviter de relire le fichier a chaque appel.
# En pratique, get_version() est appele une seule fois au demarrage
# dans create_app(), mais le cache protege contre les appels multiples.
_VERSION_CACHE: str | None = None


def get_version() -> str:
    """Lit le numero de version depuis le fichier VERSION a la racine du projet.

    Retourne '0.0.0' si le fichier n'existe pas (cas improbable,
    mais ca evite de planter au demarrage).
    """
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
