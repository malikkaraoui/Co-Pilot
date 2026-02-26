"""Schemas Pydantic pour le point d'acces /api/analyze."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.filter_result import FilterResultSchema


class AnalyzeRequest(BaseModel):
    """Corps de la requete pour POST /api/analyze.

    L'extension Chrome envoie le payload JSON brut __NEXT_DATA__.
    """

    url: str | None = None
    next_data: dict[str, Any] = Field(..., description="Leboncoin __NEXT_DATA__ JSON")


class AnalyzeResponse(BaseModel):
    """Donnees de reponse pour une analyse reussie."""

    scan_id: int | None = None
    score: int = Field(..., ge=0, le=100)
    is_partial: bool = False
    filters: list[FilterResultSchema] = []
    vehicle: dict[str, Any] | None = None
    featured_video: dict[str, Any] | None = None
