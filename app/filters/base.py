"""Classe abstraite BaseFilter et dataclass FilterResult.

Chaque filtre DOIT heriter de BaseFilter et implementer run().
Chaque filtre DOIT retourner un FilterResult -- ne jamais lever d'exception non geree.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FilterResult:
    """Type de retour uniforme pour tous les filtres.

    Attributs :
        filter_id: Identifiant du filtre, ex. "L1", "L2", ..., "L9".
        status: Un parmi "pass", "warning", "fail", "skip".
        score: Contribution au score global, de 0.0 a 1.0.
        message: Message destine a l'utilisateur (lisible sans expertise).
        details: Donnees supplementaires optionnelles pour la vue detaillee.
    """

    filter_id: str
    status: str  # "pass" | "warning" | "fail" | "skip"
    score: float
    message: str
    details: dict[str, Any] | None = field(default=None)


class BaseFilter(ABC):
    """Classe de base abstraite pour tous les filtres Co-Pilot.

    Les sous-classes doivent implementer :
        - filter_id: attribut de classe identifiant le filtre (ex. "L1")
        - run(data): execute la logique du filtre et retourne un FilterResult
    """

    filter_id: str = ""

    @abstractmethod
    def run(self, data: dict[str, Any]) -> FilterResult:
        """Execute le filtre sur les donnees extraites de l'annonce.

        Args:
            data: Dictionnaire normalise des donnees de l'annonce provenant du service d'extraction.

        Returns:
            Un FilterResult contenant le verdict du filtre.
        """

    def skip(
        self,
        message: str = "Filtre non applicable",
        details: dict[str, Any] | None = None,
    ) -> FilterResult:
        """Retourne un resultat skip pour ce filtre."""
        return FilterResult(
            filter_id=self.filter_id,
            status="skip",
            score=0.0,
            message=message,
            details=details,
        )
