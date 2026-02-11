"""Schema Pydantic pour les resultats de filtre dans les reponses API."""

from typing import Any

from pydantic import BaseModel


class FilterResultSchema(BaseModel):
    """Schema d'un resultat de filtre individuel dans la reponse API."""

    filter_id: str
    status: str
    score: float
    message: str
    details: dict[str, Any] | None = None
