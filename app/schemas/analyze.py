"""Schemas Pydantic pour le point d'acces /api/analyze."""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.filter_result import FilterResultSchema


class AnalyzeRequest(BaseModel):
    """Corps de la requete pour POST /api/analyze.

    Accepte soit next_data (LBC legacy) soit ad_data (pre-normalise, multi-site).
    """

    url: str | None = None
    next_data: dict[str, Any] | None = Field(None, description="Leboncoin __NEXT_DATA__ JSON")
    ad_data: dict[str, Any] | None = Field(None, description="Pre-normalized vehicle data")
    source: str | None = Field(None, description="Site source (leboncoin, autoscout24)")


class AnalyzeResponse(BaseModel):
    """Donnees de reponse pour une analyse reussie."""

    scan_id: int | None = None
    score: int = Field(..., ge=0, le=100)
    is_partial: bool = False
    filters: list[FilterResultSchema] = []
    vehicle: dict[str, Any] | None = None
    featured_video: dict[str, Any] | None = None
