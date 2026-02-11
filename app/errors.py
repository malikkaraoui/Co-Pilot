"""Hierarchie d'exceptions Co-Pilot.

Regles :
  - Ne jamais utiliser ``except Exception`` nu. Toujours attraper un type specifique.
  - Chaque filtre doit attraper FilterError et retourner un FilterResult avec status="skip".
"""


class CoPilotError(Exception):
    """Exception de base pour toutes les erreurs Co-Pilot."""


class FilterError(CoPilotError):
    """Une erreur est survenue dans un filtre."""


class ExtractionError(CoPilotError):
    """Echec de l'extraction des donnees d'une annonce Leboncoin."""


class ExternalAPIError(CoPilotError):
    """Un appel API externe a echoue (SIRET, etc.)."""


class ValidationError(CoPilotError):
    """Les donnees d'entree n'ont pas passe la validation."""
