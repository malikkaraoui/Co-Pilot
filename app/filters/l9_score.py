"""Filtre L9 Evaluation Globale -- evalue les signaux de confiance transversaux."""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

MIN_DESCRIPTION_LENGTH = 50


class L9GlobalAssessmentFilter(BaseFilter):
    """Evalue les signaux de confiance globaux : qualite de description, type de vendeur, completude de l'annonce."""

    filter_id = "L9"

    def run(self, data: dict[str, Any]) -> FilterResult:
        points_forts = []
        points_faibles = []

        # Qualite de la description
        description = data.get("description") or ""
        desc_len = len(description.strip())
        if desc_len >= 200:
            points_forts.append("Description détaillée")
        elif desc_len >= MIN_DESCRIPTION_LENGTH:
            pass  # neutral
        elif desc_len > 0:
            points_faibles.append("Description très courte")
        else:
            points_faibles.append("Pas de description")

        # Type de vendeur
        owner_type = data.get("owner_type")
        if owner_type == "pro":
            points_forts.append("Vendeur professionnel")
        elif owner_type == "private":
            pass  # neutral

        # Photos : >3 = annonce payante (vendeur investi)
        image_count = data.get("image_count") or 0
        if image_count > 3:
            points_forts.append(f"Annonce avec {image_count} photos (option payante)")
        elif image_count == 0:
            points_faibles.append("Aucune photo")

        # Options payantes LBC : signe d'investissement du vendeur
        paid_options = []
        if data.get("has_urgent"):
            paid_options.append("Badge Urgent")
        if data.get("has_highlight"):
            paid_options.append("A la Une")
        if data.get("has_boost"):
            paid_options.append("Remontée")
        if paid_options:
            points_forts.append(f"Options payantes : {', '.join(paid_options)}")

        # Telephone : LBC cache le numero derriere "Voir le numero" (API authentifiee).
        # L'extension tente de cliquer le bouton pour reveler le numero.
        phone_login_hint = None
        if data.get("phone"):
            points_forts.append("Numéro de téléphone visible")
        elif data.get("has_phone"):
            # Le tel existe mais n'a pas pu etre revele (utilisateur non connecte)
            phone_login_hint = "Connectez-vous sur LeBonCoin pour révéler le numéro"
        # Pas de penalite si absent : presque toutes les annonces ont un tel cache

        # Localisation disponible
        location = data.get("location") or {}
        if location.get("city"):
            points_forts.append("Localisation précise")
        else:
            points_faibles.append("Localisation non précisée")

        # Calcul du score
        total = len(points_forts) + len(points_faibles)
        if total == 0:
            score = 0.5
        else:
            score = len(points_forts) / total

        if not points_faibles:
            status = "pass"
            message = "Annonce complète et détaillée"
        elif len(points_faibles) <= 1:
            status = "warning"
            message = points_faibles[0]
        else:
            status = "fail"
            message = f"{len(points_faibles)} signaux faibles détectés"

        return FilterResult(
            filter_id=self.filter_id,
            status=status,
            score=round(score, 2),
            message=message,
            details={
                "points_forts": points_forts,
                "points_faibles": points_faibles,
                **({"phone_login_hint": phone_login_hint} if phone_login_hint else {}),
            },
        )
