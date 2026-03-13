"""Hierarchie d'exceptions OKazCar.

Toutes les exceptions custom heritent de OKazCarError pour pouvoir
les attraper en bloc quand necessaire, tout en gardant la granularite
par type dans les handlers specifiques.

Regles :
  - Ne jamais utiliser ``except Exception`` nu. Toujours attraper un type specifique.
  - Chaque filtre doit attraper FilterError et retourner un FilterResult avec status="skip".
"""


class OKazCarError(Exception):
    """Exception de base pour toutes les erreurs OKazCar.

    Permet de distinguer nos erreurs metier des exceptions Python standard
    dans les handlers globaux.
    """


class FilterError(OKazCarError):
    """Une erreur est survenue dans un filtre.

    Levee quand un filtre du moteur d'analyse ne peut pas produire
    de resultat fiable (donnees manquantes, logique impossible, etc.).
    Le moteur la catch et marque le filtre en "skip".
    """


class ExtractionError(OKazCarError):
    """Echec de l'extraction des donnees d'une annonce Leboncoin.

    Levee quand le parsing du HTML/JSON de l'annonce echoue — en general
    parce que Leboncoin a change sa structure de page.
    """


class ExternalAPIError(OKazCarError):
    """Un appel API externe a echoue (SIRET, Wheel-Size, etc.).

    Couvre les timeouts, les erreurs HTTP, et les reponses inattendues
    des APIs tierces.
    """


class ValidationError(OKazCarError):
    """Les donnees d'entree n'ont pas passe la validation.

    Levee par les schemas Pydantic ou les validations manuelles
    avant le traitement metier.
    """
