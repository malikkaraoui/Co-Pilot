"""Filtre L9 Evaluation Globale -- evalue les signaux de confiance transversaux.

Contrairement aux autres filtres qui analysent un aspect precis (prix, km, tel...),
L9 prend du recul et regarde la "qualite" globale de l'annonce :
- Est-ce que la description est detaillee ou vide ?
- Est-ce qu'il y a des photos ?
- Est-ce que le vendeur a investi dans des options payantes ?
- Est-ce que la localisation est precisee ?

L'idee : une annonce bien redigee avec des photos = vendeur sérieux.
Une annonce vide sans photo ni localisation = vendeur qui cache quelque chose ou arnaque.
"""

import logging
from typing import Any

from app.filters.base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)

# En dessous de 50 caracteres, la description est trop courte pour etre utile
MIN_DESCRIPTION_LENGTH = 50


class L9GlobalAssessmentFilter(BaseFilter):
    """Evalue les signaux de confiance globaux : qualite de description, type de vendeur, completude de l'annonce.

    Le score est le ratio points forts / total des signaux.
    Pas de points forts et pas de points faibles = score neutre (0.5).
    """

    filter_id = "L9"

    def run(self, data: dict[str, Any]) -> FilterResult:
        points_forts = []
        points_faibles = []

        # Qualite de la description : un bon indicateur de serieux du vendeur
        description = data.get("description") or ""
        desc_len = len(description.strip())
        if desc_len >= 200:
            points_forts.append("Description détaillée")
        elif desc_len >= MIN_DESCRIPTION_LENGTH:
            pass  # neutral -- ni bien ni mal
        elif desc_len > 0:
            points_faibles.append("Description très courte")
        else:
            points_faibles.append("Pas de description")

        # Type de vendeur : un pro est generalement plus fiable (garantie, SAV...)
        owner_type = data.get("owner_type")
        if owner_type == "pro":
            points_forts.append("Vendeur professionnel")
        elif owner_type == "private":
            pass  # neutral -- un particulier n'est pas un red flag

        # Photos : >3 = annonce payante sur LBC (vendeur investi financierement)
        image_count = data.get("image_count") or 0
        if image_count > 3:
            points_forts.append(f"Annonce avec {image_count} photos (option payante)")
        elif image_count == 0:
            points_faibles.append("Aucune photo")

        # Options payantes LBC : signe d'investissement du vendeur
        # Un arnaqueur ne paye pas pour mettre son annonce en avant
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

        # Localisation disponible (city, zipcode, ou department suffisent)
        location = data.get("location") or {}
        if location.get("city"):
            points_forts.append("Localisation précise")
        elif location.get("zipcode") or location.get("department"):
            pass  # neutral -- localisation partielle (commune non precisee)
        else:
            points_faibles.append("Localisation non précisée")

        # Calcul du score : ratio de points forts sur le total
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
