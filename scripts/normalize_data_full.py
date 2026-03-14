#!/usr/bin/env python3
"""Normalise le référentiel brut `docs/data FULL` en staging canonique.

Objectifs :
- supprimer les URLs source ;
- séparer proprement famille modèle / génération / variante carrosserie ;
- produire des lookup keys stables pour le matching futur ;
- agréger les années contiguës en intervalles pour éviter les doublons annuels.

Le script réécrit :
- ``docs/data FULL/structure.json``
- ``docs/data FULL/structure_checkpoint.json``

Il n'intègre rien en base : il prépare seulement un socle normalisé.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.vehicle_lookup import (  # noqa: E402
    display_brand,
    display_model,
    normalize_brand,
    normalize_model,
)
from app.services.vehicle_lookup_keys import (  # noqa: E402
    lookup_compact_key,
    normalize_canonical_text,
)

logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "docs" / "data FULL"
STRUCTURE_PATH = DATA_DIR / "structure.json"
CHECKPOINT_PATH = DATA_DIR / "structure_checkpoint.json"

PARENTHESIS_RE = re.compile(r"\(([^)]+)\)")
YEAR_RE = re.compile(r"^\d{4}$")
ROMAN_RE = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)
ALNUM_TOKEN_RE = re.compile(r"^[a-z]*\d+[a-z0-9.-]*$", re.IGNORECASE)


@dataclass(frozen=True)
class RawVehicle:
    """Ligne brute telle qu'extraite de la source Caradisiac."""

    marque: str
    generation: str
    modele: str
    annee: int


@dataclass(frozen=True)
class NormalizedVehicle:
    """Entrée staging prête pour le matching et la future fusion."""

    brand: str
    model: str
    generation: str | None
    body_variant: str | None
    year_start: int
    year_end: int
    years: list[int]
    brand_lookup_key: str
    model_lookup_key: str
    generation_lookup_key: str | None
    body_variant_lookup_key: str | None
    referential_key: str
    source_brand: str
    source_generation: str
    source_model: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _parse_raw_vehicle(row: dict[str, Any]) -> RawVehicle:
    year = str(row.get("annee", "")).strip()
    if not YEAR_RE.fullmatch(year):
        raise ValueError(f"Année invalide: {year!r}")

    return RawVehicle(
        marque=str(row.get("marque", "")).strip(),
        generation=str(row.get("generation", "")).strip(),
        modele=str(row.get("modele", "")).strip(),
        annee=int(year),
    )


def _display_or_title_brand(raw_brand: str) -> str:
    compact_source = raw_brand.strip()
    if (
        compact_source
        and " " not in compact_source
        and compact_source.isupper()
        and any(char.isalpha() for char in compact_source)
        and len(compact_source) <= 3
    ):
        return compact_source

    canonical = display_brand(raw_brand)
    if raw_brand.strip().upper() == canonical.upper() and "-" in raw_brand:
        return _smart_title(raw_brand)
    return canonical


def _display_or_title_model(raw_model: str) -> str:
    compact_source = raw_model.strip()
    if (
        compact_source
        and " " not in compact_source
        and compact_source.isupper()
        and any(char.isalpha() for char in compact_source)
    ):
        return compact_source

    canonical = display_model(raw_model)
    raw_compact = lookup_compact_key(raw_model)
    canonical_compact = lookup_compact_key(canonical)
    if raw_compact and raw_compact != canonical_compact:
        return canonical
    return _smart_title(raw_model)


def _smart_title(text: str) -> str:
    normalized = normalize_canonical_text(text)
    if not normalized:
        return ""

    words: list[str] = []
    for token in normalized.split():
        if token.isdigit() or ALNUM_TOKEN_RE.fullmatch(token):
            words.append(token.upper())
            continue
        if ROMAN_RE.fullmatch(token):
            words.append(token.upper())
            continue
        if token in {"gti", "gtd", "gt", "rs", "st", "ev", "hev", "phev", "suv"}:
            words.append(token.upper())
            continue
        if "-" in token:
            parts = [part for part in token.split("-") if part]
            words.append("-".join(_smart_title(part) for part in parts))
            continue
        if "." in token and any(part.isdigit() for part in token.split(".")):
            words.append(token.upper())
            continue
        words.append(token.capitalize())
    return " ".join(words)


def _extract_generation_label(source_model: str) -> str | None:
    match = PARENTHESIS_RE.search(source_model)
    if not match:
        return None
    label = normalize_canonical_text(match.group(1)).upper()
    return label or None


def _strip_generation_parenthesis(source_model: str) -> str:
    return PARENTHESIS_RE.sub("", source_model).strip()


def _extract_body_variant(source_generation: str, source_model: str) -> str | None:
    cleaned_model = _strip_generation_parenthesis(source_model)
    generation_prefix = source_generation.strip()

    if not cleaned_model:
        return None

    if generation_prefix:
        prefix_norm = normalize_canonical_text(generation_prefix)
        model_norm = normalize_canonical_text(cleaned_model)
        if model_norm.startswith(prefix_norm):
            suffix = cleaned_model[len(generation_prefix) :].strip(" -")
        else:
            suffix = cleaned_model
    else:
        suffix = cleaned_model

    suffix = normalize_canonical_text(suffix).strip()
    if not suffix:
        return None

    suffix_compact = lookup_compact_key(suffix)
    family_compact = lookup_compact_key(source_generation)
    if suffix_compact == family_compact:
        return None

    return _smart_title(suffix)


def normalize_vehicle(raw_vehicle: RawVehicle) -> dict[str, Any]:
    """Normalise une ligne brute en structure intermédiaire."""
    brand = _display_or_title_brand(raw_vehicle.marque)
    model = _display_or_title_model(raw_vehicle.generation)
    generation_label = _extract_generation_label(raw_vehicle.modele)
    body_variant = _extract_body_variant(raw_vehicle.generation, raw_vehicle.modele)

    brand_key = lookup_compact_key(normalize_brand(raw_vehicle.marque))
    model_key = lookup_compact_key(normalize_model(raw_vehicle.generation))
    generation_key = lookup_compact_key(generation_label) if generation_label else None
    body_key = lookup_compact_key(body_variant) if body_variant else None

    referential_parts = [brand_key, model_key]
    if generation_key:
        referential_parts.append(generation_key)
    if body_key:
        referential_parts.append(body_key)

    return {
        "brand": brand,
        "model": model,
        "generation": generation_label,
        "body_variant": body_variant,
        "year": raw_vehicle.annee,
        "brand_lookup_key": brand_key,
        "model_lookup_key": model_key,
        "generation_lookup_key": generation_key,
        "body_variant_lookup_key": body_key,
        "referential_key": ":".join(referential_parts),
        "source_brand": raw_vehicle.marque,
        "source_generation": raw_vehicle.generation,
        "source_model": raw_vehicle.modele,
    }


def _split_contiguous_years(years: list[int]) -> list[list[int]]:
    if not years:
        return []

    sorted_years = sorted(set(years))
    groups: list[list[int]] = [[sorted_years[0]]]
    for year in sorted_years[1:]:
        if year == groups[-1][-1] + 1:
            groups[-1].append(year)
        else:
            groups.append([year])
    return groups


def normalize_vehicles(rows: list[dict[str, Any]]) -> list[NormalizedVehicle]:
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}

    for row in rows:
        raw_vehicle = _parse_raw_vehicle(row)
        normalized = normalize_vehicle(raw_vehicle)
        group_key = (
            normalized["brand_lookup_key"],
            normalized["model_lookup_key"],
            normalized["generation_lookup_key"] or "",
            normalized["body_variant_lookup_key"] or "",
            normalized["source_brand"],
            normalized["source_generation"],
            normalized["source_model"],
        )

        current = grouped.setdefault(
            group_key,
            {
                **normalized,
                "years": [],
            },
        )
        current["years"].append(normalized["year"])

    output: list[NormalizedVehicle] = []
    for current in grouped.values():
        for year_group in _split_contiguous_years(current["years"]):
            output.append(
                NormalizedVehicle(
                    brand=current["brand"],
                    model=current["model"],
                    generation=current["generation"],
                    body_variant=current["body_variant"],
                    year_start=year_group[0],
                    year_end=year_group[-1],
                    years=year_group,
                    brand_lookup_key=current["brand_lookup_key"],
                    model_lookup_key=current["model_lookup_key"],
                    generation_lookup_key=current["generation_lookup_key"],
                    body_variant_lookup_key=current["body_variant_lookup_key"],
                    referential_key=current["referential_key"],
                    source_brand=current["source_brand"],
                    source_generation=current["source_generation"],
                    source_model=current["source_model"],
                )
            )

    output.sort(
        key=lambda vehicle: (
            vehicle.brand_lookup_key,
            vehicle.model_lookup_key,
            vehicle.generation_lookup_key or "",
            vehicle.body_variant_lookup_key or "",
            vehicle.year_start,
        )
    )
    return output


def _build_meta(source_rows: int, normalized_rows: int) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "normalized_at": date.today().isoformat(),
        "source_vehicle_count": source_rows,
        "normalized_vehicle_count": normalized_rows,
        "removed_fields": ["url"],
        "notes": [
            "Staging normalisé pour matching et future fusion.",
            "Aucune intégration base effectuée par ce script.",
            "Les années annuelles sont agrégées en intervalles contigus.",
        ],
    }


def _rebuild_raw_rows_from_v2(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for vehicle in payload.get("vehicles", []):
        source_brand = vehicle.get("source_brand")
        source_generation = vehicle.get("source_generation")
        source_model = vehicle.get("source_model")
        if not source_brand or not source_generation or not source_model:
            continue

        years = vehicle.get("years")
        if not isinstance(years, list) or not years:
            year_start = int(vehicle.get("year_start"))
            year_end = int(vehicle.get("year_end"))
            years = list(range(year_start, year_end + 1))

        for year in years:
            rows.append(
                {
                    "marque": source_brand,
                    "generation": source_generation,
                    "modele": source_model,
                    "annee": str(year),
                }
            )
    return rows


def transform_payload(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta")
    source_vehicle_count = None
    if isinstance(meta, dict) and meta.get("schema_version") == 2:
        meta_source_count = meta.get("source_vehicle_count")
        if isinstance(meta_source_count, int):
            source_vehicle_count = meta_source_count
        raw_rows = _rebuild_raw_rows_from_v2(payload)
        if not raw_rows:
            return payload
    else:
        raw_rows = payload.get("vehicles", [])

    if source_vehicle_count is None:
        source_vehicle_count = len(raw_rows)

    normalized_rows = [asdict(vehicle) for vehicle in normalize_vehicles(raw_rows)]
    transformed: dict[str, Any] = {
        "meta": _build_meta(source_vehicle_count, len(normalized_rows)),
        "vehicles": normalized_rows,
    }

    if "done" in payload:
        transformed["done"] = payload["done"]

    return transformed


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalise docs/data FULL/*.json")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Réécrit les fichiers en place. Sans ce flag : aperçu seulement.",
    )
    args = parser.parse_args()

    structure_payload = transform_payload(_read_json(STRUCTURE_PATH))
    checkpoint_payload = transform_payload(_read_json(CHECKPOINT_PATH))

    logger.info(
        "structure.json: %s -> %s entrées",
        structure_payload["meta"]["source_vehicle_count"],
        structure_payload["meta"]["normalized_vehicle_count"],
    )
    logger.info(
        "structure_checkpoint.json: %s -> %s entrées",
        checkpoint_payload["meta"]["source_vehicle_count"],
        checkpoint_payload["meta"]["normalized_vehicle_count"],
    )

    if not args.write:
        print(json.dumps(structure_payload["meta"], ensure_ascii=False, indent=2))
        return

    _write_json(STRUCTURE_PATH, structure_payload)
    _write_json(CHECKPOINT_PATH, checkpoint_payload)
    print(
        json.dumps(
            {
                "structure": structure_payload["meta"],
                "checkpoint": checkpoint_payload["meta"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
