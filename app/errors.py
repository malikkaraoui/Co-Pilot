"""Hierarchie d'exceptions OKazCar.

Regles :
  - Ne jamais utiliser ``except Exception`` nu. Toujours attraper un type specifique.
  - Chaque filtre doit attraper FilterError et retourner un FilterResult avec status="skip".
"""


class OKazCarError(Exception):
    """Exception de base pour toutes les erreurs OKazCar."""


class FilterError(OKazCarError):
    """Une erreur est survenue dans un filtre."""


class ExtractionError(OKazCarError):
    """Echec de l'extraction des donnees d'une annonce Leboncoin."""


class ExternalAPIError(OKazCarError):
    """Un appel API externe a echoue (SIRET, etc.)."""


class ValidationError(OKazCarError):
    """Les donnees d'entree n'ont pas passe la validation."""
