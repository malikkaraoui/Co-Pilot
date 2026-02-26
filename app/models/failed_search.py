"""Modele FailedSearch -- recherches LBC qui ont retourne 0 annonces."""

import json
from datetime import datetime, timezone

from app.extensions import db


class FailedSearch(db.Model):
    """Recherche LBC echouee (0 annonces sur toutes les strategies).

    Permet d'inspecter les URLs qui n'ont rien retourne, diagnostiquer
    les problemes de tokens/filtres, et ameliorer la construction d'URL.
    """

    __tablename__ = "failed_searches"

    id = db.Column(db.Integer, primary_key=True)
    make = db.Column(db.String(80), nullable=False, index=True)
    model = db.Column(db.String(120), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(80), nullable=False)
    fuel = db.Column(db.String(30))
    hp_range = db.Column(db.String(20))
    # Tokens utilises pour construire l'URL (pour diagnostiquer les erreurs)
    brand_token_used = db.Column(db.String(120))
    model_token_used = db.Column(db.String(200))
    token_source = db.Column(db.String(20))  # "DOM", "serveur", "fallback"
    # Log complet des strategies tentees (JSON)
    search_log = db.Column(db.Text)
    # Nombre total d'annonces trouvees (0 = echec total)
    total_ads_found = db.Column(db.Integer, default=0)
    # Resolu ? (admin peut marquer comme traite apres correction)
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    resolved_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def get_search_log(self) -> list[dict] | None:
        """Deserialise le search_log JSON."""
        if not self.search_log:
            return None
        try:
            return json.loads(self.search_log)
        except (json.JSONDecodeError, TypeError):
            return None

    def __repr__(self):
        return f"<FailedSearch {self.make} {self.model} {self.year} {self.region}>"
