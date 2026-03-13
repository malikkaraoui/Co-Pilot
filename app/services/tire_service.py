"""Service Dimensions Pneus.

- Cache permanent en DB via TireSize
- Scrape Allopneus en temps reel si absent
- Remplit en fond via Wheel-Size API (quota journalier)

Concu pour etre silencieux : en cas d'echec, retourne None (pas de crash cote API).

Architecture en cascade :
1. DB cache (gratuit, instantane)
2. Wheel-Size API (fiable mais quota limite)
3. Allopneus scraping (gratuit mais bloque par Cloudflare depuis le backend)
4. Cache negatif si rien trouve (evite de re-tenter)

Le fill_next_missing_vehicle() tourne en tache de fond pour remplir
progressivement le cache des vehicules populaires via Wheel-Size.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from flask import current_app
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app.extensions import db
from app.models.scan import ScanLog
from app.models.tire_size import TireSize
from app.models.vehicle import Vehicle
from app.services.vehicle_lookup import normalize_brand, normalize_model

logger = logging.getLogger(__name__)


# ── Allopneus config ────────────────────────────────────────────

ALLOPNEUS_BASE_URL = "https://www.allopneus.com"

# Mapping marque normalisee -> slug Allopneus quand le nom differe
ALLOPNEUS_BRAND_SLUGS: dict[str, str] = {
    "mercedes": "mercedes-benz",
    "alfa romeo": "alfa-romeo",
    "land rover": "land-rover",
    "aston martin": "aston-martin",
    "rolls royce": "rolls-royce",
    "kg mobility": "kg-mobility",
    "lynk co": "lynk-co",
}

# Idem pour les modeles dont le slug Allopneus est specifique
ALLOPNEUS_MODEL_SLUGS: dict[str, str] = {
    "serie 3": "serie-3",
    "classe a": "classe-a",
    "model 3": "model-3",
    "id.3": "id.3",
}

# Headers navigateur pour passer le WAF Cloudflare d'Allopneus
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


# ── Wheel-Size config ───────────────────────────────────────────

# Mapping marque -> nom Wheel-Size.
# Wheel-Size exige des tirets (pas d'espaces) pour les marques multi-mots.
WHEEL_SIZE_BRAND_MAP: dict[str, str] = {
    "alfa romeo": "alfa-romeo",
    "land rover": "land-rover",
    "aston martin": "aston-martin",
    "rolls royce": "rolls-royce",
}

# Modeles dont le nom LBC/AS24 ne correspond pas au nom Wheel-Size.
WHEEL_SIZE_MODEL_MAP: dict[str, str] = {
    # Audi variantes
    "a4 allroad": "a4",
    "a6 allroad": "a6",
    "allroad": "a6",
    # BMW : "Serie X" → "X-series"
    "serie 1": "1-series",
    "serie 2": "2-series",
    "serie 3": "3-series",
    "serie 4": "4-series",
    "serie 5": "5-series",
    "serie 6": "6-series",
    "serie 7": "7-series",
    "serie 8": "8-series",
    # Mercedes : "Classe X" → "X-class"
    "classe a": "a-class",
    "classe b": "b-class",
    "classe c": "c-class",
    "classe e": "e-class",
    "classe g": "g-class",
    "classe s": "s-class",
    "classe v": "v-class",
    "classe gl": "gl-class",
    "glc 220": "glc",
    "glc 250": "glc",
    "glc 300": "glc",
    "glc 350": "glc",
    "gle 250": "gle",
    "gle 350": "gle",
    "gla 200": "gla",
    "gla 250": "gla",
    # Mazda : "3" → "mazda3"
    "3": "mazda3",
    "6": "mazda6",
    # Peugeot variantes
    "206+": "206",
    # Land Rover composites
    "range rover sport": "range-rover-sport",
    "range rover evoque": "range-rover-evoque",
    "range rover velar": "range-rover-velar",
    "range rover": "range-rover",
}


def _wheel_size_key() -> str:
    return current_app.config.get("WHEEL_SIZE_API_KEY", "")


def _wheel_size_base_url() -> str:
    return current_app.config.get("WHEEL_SIZE_BASE_URL", "https://api.wheel-size.com/v2")


def _wheel_size_daily_budget() -> int:
    try:
        return int(current_app.config.get("WHEEL_SIZE_DAILY_BUDGET", 50))
    except (TypeError, ValueError):
        return 50


# ── Public API ─────────────────────────────────────────────────


def get_tire_sizes(make: str, model: str, year: int) -> dict[str, Any] | None:
    """Retourne les dimensions pneus pour un vehicule.

    C'est le point d'entree principal appele par le filtre pneus et le rapport PDF.

    Cascade :
    1) Check DB (cache permanent)
    2) Wheel-Size API (fiable, pas de WAF)
    3) Fallback Allopneus scrape (peut etre bloque par Cloudflare)
    4) Stocke en DB pour ne plus jamais refaire la requete

    Returns:
        dict: {"dimensions": [...], "source": "...", ...} ou None
    """
    if not make or not model or not year:
        return None

    make_norm = normalize_brand(make).lower()
    model_norm = normalize_model(model).lower()

    # 1) Cache DB
    tire = _find_tire_size_in_db(make_norm, model_norm, year)
    if tire:
        _increment_request_count(tire)
        if tire.dimension_count == 0:
            # Cache negatif — vehicule deja cherche, pas de donnees
            return None
        return _to_payload(tire)

    # 2) Wheel-Size API (prioritaire : API propre, pas de WAF)
    fetched = None
    if _wheel_size_key() and not _wheel_size_budget_reached():
        fetched = _fetch_wheel_size(make_norm, model_norm, int(year))
        if fetched:
            return _store_and_return(make_norm, model_norm, fetched, source="wheel-size")

    # 3) Fallback Allopneus (peut echouer : 403 Cloudflare depuis le backend)
    scraped = _scrape_allopneus(make_norm, model_norm, year)
    if scraped:
        return _store_and_return(make_norm, model_norm, scraped, source="allopneus")

    # Rien trouve — cache negatif pour ne pas re-tenter
    _store_negative_cache(make_norm, model_norm, year)
    return None


def get_cached_tire_sizes(make: str, model: str, year: int) -> dict[str, Any] | None:
    """Retourne les dimensions pneus depuis le cache DB uniquement.

    Aucun appel reseau n'est effectue. Utilise par la generation PDF pour
    reutiliser les donnees deja collectees lors de l'analyse initiale.
    Le rapport ne doit jamais attendre un scrape reseau.
    """
    if not make or not model or not year:
        return None

    make_norm = normalize_brand(make).lower()
    model_norm = normalize_model(model).lower()

    tire = _find_tire_size_in_db(make_norm, model_norm, year)
    if not tire:
        return None

    _increment_request_count(tire)
    if tire.dimension_count == 0:
        return None

    return _to_payload(tire)


def _store_and_return(
    make: str, model: str, data: dict[str, Any], source: str
) -> dict[str, Any] | None:
    """Stocke les dimensions et retourne le payload."""
    try:
        stored = store_tire_sizes(
            make=make,
            model=model,
            generation=data.get("generation") or "",
            year_start=data.get("year_start"),
            year_end=data.get("year_end"),
            dimensions=data.get("dimensions") or [],
            source=source,
            source_url=data.get("source_url"),
        )
        _increment_request_count(stored)
        return _to_payload(stored)
    except (IntegrityError, OperationalError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Failed to store tire sizes (%s): %s", source, exc)
        db.session.rollback()
        return None


def fill_next_missing_vehicle(exclude_make_model: tuple[str, str] | None = None) -> bool:
    """Pioche un vehicule du referentiel sans TireSize et le remplit via Wheel-Size API.

    Appele en tache de fond apres chaque scan. Priorise les vehicules les plus
    scannes (populaires) pour maximiser l'utilite du budget API quotidien.

    - Respecte un budget journalier (WHEEL_SIZE_DAILY_BUDGET)
    - Exclut le véhicule courant (celui traité via Allopneus) pour éviter la double source

    Retourne True si un véhicule a été traité, False sinon.

    Note: doit être exécuté dans un app_context (thread background: wrapper côté caller).
    """
    if not _wheel_size_key():
        return False

    if _wheel_size_budget_reached():
        return False

    candidate = _pick_next_missing_vehicle(exclude_make_model=exclude_make_model)
    if not candidate:
        return False

    make_norm, model_norm, year_start = candidate

    fetched = _fetch_wheel_size(make_norm, model_norm, year_start)
    if not fetched:
        return False

    try:
        store_tire_sizes(
            make=make_norm,
            model=model_norm,
            generation=fetched.get("generation") or "",
            year_start=fetched.get("year_start"),
            year_end=fetched.get("year_end"),
            dimensions=fetched.get("dimensions") or [],
            source="wheel-size",
            source_url=fetched.get("source_url"),
        )
        return True
    except (IntegrityError, OperationalError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Failed to store tire sizes (wheel-size): %s", exc)
        db.session.rollback()
        return False


def store_tire_sizes(
    make: str,
    model: str,
    generation: str,
    year_start: int | None,
    year_end: int | None,
    dimensions: list[dict],
    source: str,
    source_url: str | None = None,
) -> TireSize:
    """Stocke ou met a jour les dimensions pneus pour un vehicule/generation.

    Upsert par (make, model, generation). Dedup et tri des dimensions avant stockage.
    """
    make_norm = (make or "").strip().lower()
    model_norm = (model or "").strip().lower()
    generation_norm = (generation or "").strip() or None

    dims = _dedup_dimensions(dimensions)
    dims = _sort_dimensions(dims)

    existing = TireSize.query.filter_by(
        make=make_norm,
        model=model_norm,
        generation=generation_norm,
    ).first()

    if existing:
        existing.year_start = year_start
        existing.year_end = year_end
        existing.source = source
        existing.source_url = source_url
        existing.set_dimensions_list(dims)
        existing.collected_at = datetime.now(timezone.utc)
        db.session.commit()
        return existing

    tire = TireSize(
        make=make_norm,
        model=model_norm,
        generation=generation_norm,
        year_start=year_start,
        year_end=year_end,
        source=source,
        source_url=source_url,
        dimensions=json.dumps(dims, ensure_ascii=False),
        dimension_count=len(dims),
        collected_at=datetime.now(timezone.utc),
        request_count=0,
    )
    db.session.add(tire)
    db.session.commit()
    return tire


# ── DB helpers ────────────────────────────────────────────────


def _find_tire_size_in_db(make: str, model: str, year: int) -> TireSize | None:
    """Cherche en DB un TireSize dont la plage year_start/year_end couvre l'annee demandee."""
    q = TireSize.query.filter(
        TireSize.make == make,
        TireSize.model == model,
        and_(or_(TireSize.year_start.is_(None), TireSize.year_start <= year)),
        and_(or_(TireSize.year_end.is_(None), TireSize.year_end >= year)),
    )
    return q.order_by(TireSize.collected_at.desc()).first()


def _increment_request_count(tire: TireSize) -> None:
    try:
        tire.request_count = (tire.request_count or 0) + 1
        db.session.commit()
    except (IntegrityError, OperationalError) as exc:
        logger.debug("Failed to increment tire request_count: %s", exc)
        db.session.rollback()


def _store_negative_cache(make: str, model: str, year: int) -> None:
    """Stocke un record vide pour eviter de re-scraper un vehicule introuvable."""
    try:
        existing = TireSize.query.filter_by(
            make=make, model=model, generation=f"_not_found_{year}"
        ).first()
        if existing:
            return
        tire = TireSize(
            make=make,
            model=model,
            generation=f"_not_found_{year}",
            year_start=year,
            year_end=year,
            dimensions="[]",
            dimension_count=0,
            source="negative_cache",
            collected_at=datetime.now(timezone.utc),
            request_count=0,
        )
        db.session.add(tire)
        db.session.commit()
    except (IntegrityError, OperationalError) as exc:
        logger.debug("Failed to store negative tire cache: %s", exc)
        db.session.rollback()


def _to_payload(tire: TireSize) -> dict[str, Any]:
    dims = tire.get_dimensions_list()
    year_range = None
    if tire.year_start or tire.year_end:
        ys = tire.year_start or "?"
        ye = tire.year_end or "?"
        year_range = f"{ys}-{ye}"

    return {
        "dimensions": dims,
        "source": tire.source,
        "source_url": tire.source_url,
        "generation": tire.generation,
        "year_range": year_range,
    }


# ── Allopneus scraping ────────────────────────────────────────

_YEAR_RANGE_RE = re.compile(
    r"(?:(?:de|du)\s*)?(?:\d{2}[-/])?(\d{4})\s*(?:a|à|-)\s*(?:\d{2}[-/])?(\d{4})",
    re.IGNORECASE,
)

_TIRE_TEXT_RE = re.compile(
    r"(\d{3})\s*/\s*(\d{2})\s*R\s*(\d{2})\s*(?:\s+|\s*)(\d{2,3})\s*([A-Z])",
)


def _scrape_allopneus(make: str, model: str, year: int) -> dict[str, Any] | None:
    """Scrape Allopneus en 2 etapes : page modele -> page generation.

    Etape 1 : on charge la page modele pour lister les generations disponibles.
    Etape 2 : on charge la page generation qui correspond a l'annee pour extraire
    les dimensions de pneus. Peut echouer si Cloudflare bloque (403).
    """
    make_slug = _allopneus_make_slug(make)
    model_slug = _allopneus_model_slug(model)

    model_url = f"{ALLOPNEUS_BASE_URL}/vehicule/{make_slug}/{model_slug}"

    try:
        resp = httpx.get(model_url, headers=HEADERS, timeout=_HTTP_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.debug("Allopneus model page error: %s", exc)
        return None

    if resp.status_code == 404:
        return None
    if resp.status_code in (403, 429):
        logger.warning("Allopneus blocked (status=%d)", resp.status_code)
        return None
    if resp.status_code != 200:
        logger.debug("Allopneus unexpected status=%d", resp.status_code)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    gen = _extract_generation_for_year(soup, make_slug, model_slug, year)
    if not gen:
        return None

    generation_slug = gen["slug"]
    generation_label = gen.get("label") or generation_slug
    year_start = gen.get("year_start")
    year_end = gen.get("year_end")

    gen_url = f"{ALLOPNEUS_BASE_URL}/vehicule/{make_slug}/{model_slug}/{generation_slug}"
    try:
        resp2 = httpx.get(gen_url, headers=HEADERS, timeout=_HTTP_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        logger.debug("Allopneus generation page error: %s", exc)
        return None

    if resp2.status_code == 404:
        return None
    if resp2.status_code in (403, 429):
        logger.warning("Allopneus blocked (status=%d)", resp2.status_code)
        return None
    if resp2.status_code != 200:
        logger.debug("Allopneus generation unexpected status=%d", resp2.status_code)
        return None

    soup2 = BeautifulSoup(resp2.text, "lxml")
    dims = _extract_tire_dimensions_from_generation_page(soup2)
    if not dims:
        return None

    return {
        "dimensions": dims,
        "source_url": gen_url,
        "generation": generation_label,
        "year_start": year_start,
        "year_end": year_end,
    }


def _allopneus_make_slug(make: str) -> str:
    key = (make or "").strip().lower()
    if key in ALLOPNEUS_BRAND_SLUGS:
        return ALLOPNEUS_BRAND_SLUGS[key]
    return re.sub(r"\s+", "-", key)


def _allopneus_model_slug(model: str) -> str:
    key = (model or "").strip().lower()
    if key in ALLOPNEUS_MODEL_SLUGS:
        return ALLOPNEUS_MODEL_SLUGS[key]
    # Allopneus accepte souvent les points dans les slugs (ex: id.3)
    key = re.sub(r"\s+", "-", key)
    return key


def _extract_generation_for_year(
    soup: BeautifulSoup,
    make_slug: str,
    model_slug: str,
    year: int,
) -> dict[str, Any] | None:
    """Retourne {slug,label,year_start,year_end} pour l'année donnée."""
    href_re = re.compile(rf"/vehicule/{re.escape(make_slug)}/{re.escape(model_slug)}/([^/?#\"']+)")

    candidates: list[dict[str, Any]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        m = href_re.search(href)
        if not m:
            continue

        slug = m.group(1).strip("/")
        # Texte autour du lien (souvent contient la plage d'années)
        context_text = " ".join(
            (
                a.get_text(" ", strip=True) or "",
                a.parent.get_text(" ", strip=True) if a.parent else "",
            )
        ).strip()

        yr = _parse_year_range(context_text)
        candidates.append(
            {
                "slug": slug,
                "label": _clean_generation_label(a.get_text(" ", strip=True)),
                "year_start": yr[0] if yr else None,
                "year_end": yr[1] if yr else None,
                "_context": context_text,
            }
        )

    # Dedup par slug (garder le plus riche)
    by_slug: dict[str, dict[str, Any]] = {}
    for c in candidates:
        prev = by_slug.get(c["slug"])
        if not prev:
            by_slug[c["slug"]] = c
            continue
        # Preferer celui qui a year_start/year_end
        prev_score = int(bool(prev.get("year_start"))) + int(bool(prev.get("year_end")))
        cur_score = int(bool(c.get("year_start"))) + int(bool(c.get("year_end")))
        if cur_score > prev_score:
            by_slug[c["slug"]] = c

    candidates = list(by_slug.values())

    # Tenter un matching par année
    matched = []
    for c in candidates:
        ys, ye = c.get("year_start"), c.get("year_end")
        if ys and ye and ys <= year <= ye:
            matched.append(c)

    if matched:
        # Si plusieurs, prendre la plus récente (year_start max)
        matched.sort(key=lambda x: (x.get("year_start") or 0), reverse=True)
        return matched[0]

    # Fallback : si une seule génération, prendre la seule
    if len(candidates) == 1:
        return candidates[0]

    # Fallback : prendre la génération la plus proche (year_start max)
    candidates.sort(key=lambda x: (x.get("year_start") or 0), reverse=True)
    return candidates[0] if candidates else None


def _parse_year_range(text: str) -> tuple[int, int] | None:
    if not text:
        return None
    m = _YEAR_RANGE_RE.search(text)
    if not m:
        return None
    try:
        ys = int(m.group(1))
        ye = int(m.group(2))
        if 1900 <= ys <= 2100 and 1900 <= ye <= 2100 and ys <= ye:
            return ys, ye
    except (TypeError, ValueError):
        return None
    return None


def _clean_generation_label(text: str) -> str:
    if not text:
        return ""
    # Ex: "VOLKSWAGEN GOLF VII" -> "GOLF VII" (on enlève marque si répétée)
    t = re.sub(r"\s+", " ", text.strip())
    return t.title()


def _extract_tire_dimensions_from_generation_page(soup: BeautifulSoup) -> list[dict[str, Any]]:
    dims: list[dict[str, Any]] = []

    # Scraper les <a> qui contiennent la dimension dans le texte
    for a in soup.find_all("a"):
        txt = a.get_text(" ", strip=True) or ""
        m = _TIRE_TEXT_RE.search(txt)
        if not m:
            continue
        size = f"{m.group(1)}/{m.group(2)}R{m.group(3)}"
        load_index = int(m.group(4))
        speed_index = m.group(5)
        dims.append(
            {
                "size": size,
                "load_index": load_index,
                "speed_index": speed_index,
                "is_stock": None,  # Allopneus ne distingue pas stock/non-stock
            }
        )

    # Dedup et tri
    return _sort_dimensions(_dedup_dimensions(dims))


# ── Wheel-Size API ─────────────────────────────────────────────


def _fetch_wheel_size(make: str, model: str, year: int) -> dict[str, Any] | None:
    """Appelle l'API Wheel-Size pour un vehicule.

    2 appels API : modifications (pour trouver la variante) puis search/by_model
    (pour les dimensions). Le budget quotidien est controle par _wheel_size_budget_reached.
    """
    key = _wheel_size_key()
    if not key:
        return None

    base = _wheel_size_base_url().rstrip("/")

    # Mapping marque/modele vers les noms Wheel-Size
    ws_make = WHEEL_SIZE_BRAND_MAP.get(make, make)
    ws_model = WHEEL_SIZE_MODEL_MAP.get(model, model)

    # 1) Modifications
    mods_url = f"{base}/modifications/"
    params = {
        "make": ws_make,
        "model": ws_model,
        "year": year,
        "region": "eudm",
        "user_key": key,
    }

    try:
        resp = httpx.get(mods_url, params=params, timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as exc:
        logger.debug("Wheel-Size modifications error: %s", exc)
        return None

    if resp.status_code != 200:
        logger.debug("Wheel-Size modifications status=%d", resp.status_code)
        return None

    mods_data = resp.json()
    modifications = mods_data.get("data") if isinstance(mods_data, dict) else mods_data
    if not isinstance(modifications, list) or not modifications:
        return None

    mod_slug = modifications[0].get("slug") or modifications[0].get("id")

    # 2) Wheels search
    search_url = f"{base}/search/by_model/"
    params2 = {
        "make": ws_make,
        "model": ws_model,
        "year": year,
        "region": "eudm",
        "user_key": key,
    }
    if mod_slug:
        params2["modification"] = mod_slug

    try:
        resp2 = httpx.get(search_url, params=params2, timeout=_HTTP_TIMEOUT)
    except httpx.HTTPError as exc:
        logger.debug("Wheel-Size search error: %s", exc)
        return None

    if resp2.status_code != 200:
        logger.debug("Wheel-Size search status=%d", resp2.status_code)
        return None

    payload = resp2.json()
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list) or not data:
        return None

    item0 = data[0] or {}

    generation_name = None
    gen_obj = item0.get("generation") or {}
    if isinstance(gen_obj, dict):
        generation_name = gen_obj.get("name")
        year_start = gen_obj.get("start")
        year_end = gen_obj.get("end")
    else:
        year_start = None
        year_end = None

    wheels = item0.get("wheels") or []
    dims: list[dict[str, Any]] = []

    if isinstance(wheels, list):
        for w in wheels:
            if not isinstance(w, dict):
                continue
            front = w.get("front") or {}
            if not isinstance(front, dict):
                continue

            size = front.get("tire")
            tire_full = front.get("tire_full") or ""
            if not size and isinstance(tire_full, str):
                m = re.search(r"(\d{3}/\d{2}R\d{2})", tire_full)
                size = m.group(1) if m else None

            if not size:
                continue

            dims.append(
                {
                    "size": str(size),
                    "load_index": front.get("load_index"),
                    "speed_index": front.get("speed_index"),
                    "is_stock": bool(w.get("is_stock", True)),
                }
            )

    dims = _sort_dimensions(_dedup_dimensions(dims))
    if not dims:
        return None

    # Ne PAS stocker l'URL Wheel-Size : elle contient la cle API (user_key)
    source_url = None

    return {
        "dimensions": dims,
        "generation": generation_name,
        "year_start": int(year_start) if year_start else None,
        "year_end": int(year_end) if year_end else None,
        "source_url": source_url,
    }


def _wheel_size_budget_reached() -> bool:
    """True si on a deja utilise tout le budget Wheel-Size pour aujourd'hui."""
    budget = _wheel_size_daily_budget()
    if budget <= 0:
        return True

    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)

    used = (
        db.session.query(func.count(TireSize.id))
        .filter(
            TireSize.source == "wheel-size",
            TireSize.collected_at >= today_start,
        )
        .scalar()
        or 0
    )
    return used >= budget


def _pick_next_missing_vehicle(
    exclude_make_model: tuple[str, str] | None,
) -> tuple[str, str, int] | None:
    """Choisit le prochain Vehicle sans TireSize, trie par popularite (ScanLog) decroissante.

    On priorise les vehicules les plus scannes pour maximiser l'impact du budget API.
    Les vehicules deja couverts par TireSize sont exclus via un LEFT JOIN / IS NULL.
    """
    subq = db.session.query(TireSize.make.label("make"), TireSize.model.label("model")).subquery()

    # Compteur de demandes issu de l'historique de scans (meilleur proxy "popularité")
    scan_counts = (
        db.session.query(
            func.lower(ScanLog.vehicle_make).label("make"),
            func.lower(ScanLog.vehicle_model).label("model"),
            func.count(ScanLog.id).label("cnt"),
        )
        .filter(ScanLog.vehicle_make.isnot(None), ScanLog.vehicle_model.isnot(None))
        .group_by(func.lower(ScanLog.vehicle_make), func.lower(ScanLog.vehicle_model))
        .subquery()
    )

    q = (
        db.session.query(
            Vehicle.brand.label("brand"),
            Vehicle.model.label("model"),
            Vehicle.year_start.label("year_start"),
            func.coalesce(scan_counts.c.cnt, 0).label("demand"),
        )
        .outerjoin(
            subq,
            and_(
                func.lower(Vehicle.brand) == subq.c.make,
                func.lower(Vehicle.model) == subq.c.model,
            ),
        )
        .outerjoin(
            scan_counts,
            and_(
                func.lower(Vehicle.brand) == scan_counts.c.make,
                func.lower(Vehicle.model) == scan_counts.c.model,
            ),
        )
        .filter(subq.c.make.is_(None))
    )

    if exclude_make_model:
        ex_make, ex_model = exclude_make_model
        q = q.filter(
            or_(
                func.lower(Vehicle.brand) != (ex_make or "").lower(),
                func.lower(Vehicle.model) != (ex_model or "").lower(),
            )
        )

    row = q.order_by(func.coalesce(scan_counts.c.cnt, 0).desc(), Vehicle.id.asc()).limit(1).first()

    if not row or not row.year_start:
        return None

    make_norm = normalize_brand(row.brand).lower()
    model_norm = normalize_model(row.model).lower()
    return make_norm, model_norm, int(row.year_start)


# ── Dimension utils ───────────────────────────────────────────


def _dedup_dimensions(dimensions: list[dict]) -> list[dict[str, Any]]:
    """Dedup par `size` (cle unique).

    Fusionne les metadonnees (load_index, speed_index, is_stock) quand
    une meme dimension apparait plusieurs fois avec des infos complementaires.
    """
    seen: dict[str, dict[str, Any]] = {}
    for d in dimensions or []:
        if not isinstance(d, dict):
            continue
        size = (d.get("size") or "").strip()
        if not size:
            continue
        key = size.replace(" ", "")
        existing = seen.get(key)
        if not existing:
            seen[key] = {
                "size": key,
                "load_index": d.get("load_index"),
                "speed_index": d.get("speed_index"),
                "is_stock": d.get("is_stock"),
            }
            continue

        # Fusion légère : préserver le load/speed si manquants
        if existing.get("load_index") in (None, "") and d.get("load_index"):
            existing["load_index"] = d.get("load_index")
        if existing.get("speed_index") in (None, "") and d.get("speed_index"):
            existing["speed_index"] = d.get("speed_index")
        # Fusionner is_stock : True gagne sur None, None gagne sur False
        if d.get("is_stock") is True:
            existing["is_stock"] = True
        elif existing.get("is_stock") is None and d.get("is_stock") is not None:
            existing["is_stock"] = d.get("is_stock")

    return list(seen.values())


_RIM_RE = re.compile(r"R(\d{2})")


def _rim_diameter(size: str) -> int:
    m = _RIM_RE.search(size or "")
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def _sort_dimensions(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trie les dimensions par diametre de jante croissant puis par taille."""
    return sorted(
        dimensions or [],
        key=lambda d: (
            _rim_diameter(str(d.get("size") or "")),
            str(d.get("size") or ""),
        ),
    )
