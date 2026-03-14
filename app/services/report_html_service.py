"""Service de generation de rapport PDF via Markdown/HTML + WeasyPrint.

Genere un PDF complet a partir d'un ScanLog en construisant des sections
HTML (certaines depuis du Markdown, d'autres en HTML brut), assemblees
dans le template report_base.html avec le CSS report.css inline.

Architecture :
  1. Collecte des donnees (ScanLog, FilterResultDB, EmailDraft)
  2. Construction des sections HTML (_build_*_section)
  3. Assemblage dans le template (_assemble_html)
  4. Rendu PDF via WeasyPrint
"""

import logging
import os
import re
from datetime import datetime, timezone

import markdown
from flask import current_app

from app.extensions import db
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog
from app.services.report_service import (
    FILTER_NAMES,
    STATUS_LABELS,
    _brand_display,
    _brand_logo_url,
    _filter_sort_key,
    _find_filter_result,
    _format_number,
    _format_price,
    _get_engine_reliability_safe,
    _get_tire_sizes_safe,
    _model_display,
    _safe_str,
    _source_label,
    _verdict_for_score,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers HTML
# ---------------------------------------------------------------------------


def _badge_html(status: str, *, label: str | None = None) -> str:
    """Retourne un badge HTML colore selon le status du filtre.

    >>> _badge_html("pass")
    '<span class="badge badge-pass">OK</span>'
    """
    css_class = {
        "pass": "badge-pass",
        "warning": "badge-warning",
        "fail": "badge-fail",
    }.get(status, "badge-skip")
    display_label = label if label is not None else STATUS_LABELS.get(status, status)
    return f'<span class="badge {css_class}">{display_label}</span>'


def _score_color_class(score: int | None) -> str:
    """Retourne la classe CSS de couleur associee au score."""
    if score is None:
        return "text-gray"
    if score >= 80:
        return "text-green"
    if score >= 60:
        return "text-blue"
    if score >= 40:
        return "text-amber"
    return "text-red"


def _stars_html(rating: float, max_stars: int = 5) -> str:
    """Retourne une chaine d'etoiles Unicode : ★★★★☆."""
    filled = int(round(rating))
    filled = max(0, min(filled, max_stars))
    return "\u2605" * filled + "\u2606" * (max_stars - filled)


def _phone_link(phone: str) -> str:
    """Retourne un lien HTML tel: cliquable."""
    clean = re.sub(r"[^\d+]", "", phone)
    if clean.startswith("0"):
        clean = "+33" + clean[1:]
    elif not clean.startswith("+"):
        clean = "+33" + clean
    return f'<a class="phone-link" href="tel:{clean}">{_safe_str(phone)}</a>'


def _md_to_html(text: str) -> str:
    """Convertit du Markdown en HTML via python-markdown."""
    return markdown.markdown(text, extensions=["tables"])


# ---------------------------------------------------------------------------
# Sections du rapport
# ---------------------------------------------------------------------------


def _build_hero_section(scan: ScanLog, raw: dict, filter_results: list[FilterResultDB]) -> str:
    """Section 1 — Hero (fiche vehicule)."""
    brand = _brand_display(scan.vehicle_make)
    model = _model_display(scan.vehicle_model)
    price = _format_price(scan.price_eur) if scan.price_eur else ""
    power = _safe_str(raw.get("power") or raw.get("puissance") or "")

    # Photo
    photo_url = raw.get("image_url") or raw.get("photo_url") or raw.get("thumbnail")
    if photo_url:
        photo_html = f'<img class="hero-photo" src="{photo_url}" alt="{brand} {model}">'
    else:
        photo_html = '<div class="hero-photo-placeholder">Pas de photo</div>'

    # Prix : couleur selon position marche
    l4 = _find_filter_result(filter_results, "L4")
    price_class = ""
    if l4 and isinstance(l4.details, dict):
        delta = l4.details.get("delta_eur")
        if isinstance(delta, (int, float)):
            price_class = "text-green" if delta < 0 else "text-red" if delta > 0 else ""

    # Telephone
    phone = raw.get("phone") or ""
    if not phone:
        l6 = _find_filter_result(filter_results, "L6")
        if l6 and isinstance(l6.details, dict):
            phone = l6.details.get("phone", "")
    phone_html = _phone_link(phone) if phone else ""

    # SIRET
    siret_html = ""
    l7 = _find_filter_result(filter_results, "L7")
    if l7 and isinstance(l7.details, dict):
        siret = l7.details.get("siret", "")
        company = l7.details.get("company_name") or l7.details.get("nom_complet", "")
        if siret or company:
            parts = []
            if siret:
                parts.append(f"SIRET {_safe_str(siret)}")
            if company:
                parts.append(_safe_str(company))
            siret_html = f'<div class="siret-info">{" — ".join(parts)}</div>'

    return f"""
<div class="hero">
    {photo_html}
    <div class="hero-info">
        <p class="vehicle-name">{_safe_str(brand)} {_safe_str(model)}</p>
        <p class="vehicle-power">{_safe_str(power)}</p>
        <p class="vehicle-price {price_class}">{_safe_str(price)}</p>
        {phone_html}
        {siret_html}
    </div>
</div>
"""


def _build_score_section(score: int | None) -> str:
    """Section 2 — Score global avec barre gradient."""
    score_val = score if score is not None else 0
    verdict = _verdict_for_score(score)
    color_class = _score_color_class(score)
    marker_pct = max(0, min(100, score_val))

    return f"""
<div class="score-section">
    <span class="score-value {color_class}">{score_val}</span>
    <span class="score-label"> / 100</span>
    <div class="score-verdict {color_class}">{_safe_str(verdict)}</div>
    <div class="score-bar">
        <div class="score-marker" style="left: {marker_pct}%;"></div>
    </div>
</div>
"""


def _build_vehicle_info_section(scan: ScanLog, raw: dict) -> str:
    """Section 3 — Infos vehicule (tableau Markdown)."""
    fields = [
        ("Annee", raw.get("year") or raw.get("annee")),
        ("Carburant", raw.get("fuel") or raw.get("fuel_type")),
        ("Boite", raw.get("gearbox") or raw.get("transmission")),
        (
            "Km",
            _format_number(raw.get("km") or raw.get("mileage"))
            if raw.get("km") or raw.get("mileage")
            else None,
        ),
        ("Puissance", raw.get("power") or raw.get("puissance")),
        ("Couleur", raw.get("color") or raw.get("couleur")),
        ("Portes", raw.get("doors") or raw.get("portes")),
        ("Carrosserie", raw.get("body_type") or raw.get("carrosserie")),
        ("Source", _source_label(scan.source)),
        ("Pays", scan.country),
        ("Vendeur", raw.get("seller_name")),
        ("Type vendeur", raw.get("seller_type")),
        ("Localisation", raw.get("location") or raw.get("localisation")),
        ("CT", raw.get("ct") or raw.get("controle_technique")),
    ]

    # Filtrer les champs vides
    rows = [(label, _safe_str(val)) for label, val in fields if val]

    if not rows:
        return ""

    md_lines = ["## Informations véhicule\n"]
    md_lines.append("| Champ | Valeur |")
    md_lines.append("|-------|--------|")
    for label, val in rows:
        md_lines.append(f"| {label} | {val} |")

    # Lien vers l'annonce
    if scan.url:
        md_lines.append(f"\n[Voir l'annonce originale]({scan.url})")

    return _md_to_html("\n".join(md_lines))


def _build_market_section(scan: ScanLog, l4: FilterResultDB | None) -> str:
    """Section 4 — Prix vs marche."""
    if not l4 or not isinstance(l4.details, dict):
        return ""

    details = l4.details
    price_annonce = details.get("price_annonce", scan.price_eur or 0)
    price_ref = details.get("price_reference", 0)
    delta_eur = details.get("delta_eur", 0)
    delta_pct = details.get("delta_pct", 0)
    source = _source_label(details.get("source", ""))
    sample_count = details.get("sample_count", "")

    # Couleur du delta
    delta_class = "text-green" if delta_eur <= 0 else "text-red"
    sign = "+" if delta_eur > 0 else ""

    # Position du prix sur la barre (0-100%)
    if price_ref and price_ref > 0:
        ratio = price_annonce / price_ref
        bar_pct = max(5, min(95, ratio * 50))
    else:
        bar_pct = 50

    # Argus
    argus_html = ""
    argus_mid = details.get("price_argus_mid")
    if argus_mid:
        argus_low = details.get("price_argus_low", "")
        argus_high = details.get("price_argus_high", "")
        argus_html = f"""
        <p class="text-small text-gray">
            Argus : {_format_price(argus_low)} — {_format_price(argus_mid)} — {_format_price(argus_high)}
        </p>"""

    return f"""
<h2>Prix vs marché</h2>
<div class="card">
    <p>
        <strong>Delta :</strong>
        <span class="{delta_class}">{sign}{_format_number(delta_eur)} EUR ({delta_pct:+.1f}%)</span>
    </p>
    <div class="progress-bar-container">
        <div class="progress-bar-fill" style="width: {bar_pct}%;"></div>
        <div class="progress-bar-marker" style="left: {bar_pct}%;"></div>
    </div>
    <p class="progress-bar-label">
        Prix annonce : {_format_price(price_annonce)} | Référence : {_format_price(price_ref)}
    </p>
    {argus_html}
    <p class="text-small text-gray">Source : {_safe_str(source)} | Échantillon : {_safe_str(sample_count)}</p>
</div>
"""


def _build_km_section(l3: FilterResultDB | None) -> str:
    """Section 5 — Kilometrage."""
    if not l3 or not isinstance(l3.details, dict):
        return ""

    details = l3.details
    km = details.get("mileage_km", 0)
    expected = details.get("expected_km", 0)
    age = details.get("age", "")
    km_per_year = details.get("km_per_year", "")
    category = details.get("category", "")

    # Barre de progression km
    if expected and expected > 0:
        ratio = km / expected
        bar_pct = max(5, min(95, ratio * 50))
    else:
        bar_pct = 50

    bar_class = "text-green" if km <= (expected or 0) else "text-amber"

    return f"""
<h2>Kilométrage</h2>
<div class="card">
    <p class="{bar_class}" style="font-size: 16pt; font-weight: 700;">
        {_format_number(km)} km
    </p>
    <div class="progress-bar-container">
        <div class="progress-bar-fill" style="width: {bar_pct}%;"></div>
        <div class="progress-bar-marker" style="left: {bar_pct}%;"></div>
    </div>
    <p class="progress-bar-label">
        Observé : {_format_number(km)} km | Attendu : {_format_number(expected)} km
    </p>
    <p class="text-small text-gray">
        Age : {_safe_str(age)} ans | {_format_number(km_per_year)} km/an | Catégorie : {_safe_str(category)}
    </p>
</div>
"""


def _build_filters_section(results: list[FilterResultDB]) -> str:
    """Section 6 — Tableau des resultats de filtres."""
    if not results:
        return ""

    sorted_results = sorted(results, key=lambda r: _filter_sort_key(r.filter_id))

    md_lines = ["## Résultats des filtres\n"]
    md_lines.append("| Filtre | Statut | Message |")
    md_lines.append("|--------|--------|---------|")

    for fr in sorted_results:
        name = FILTER_NAMES.get(fr.filter_id, fr.filter_id)
        badge = _badge_html(fr.status)
        message = _safe_str(fr.message or "")
        md_lines.append(f"| {name} | {badge} | {message} |")

    return _md_to_html("\n".join(md_lines))


def _build_reliability_section(reliability: object | None) -> str:
    """Section 7 — Fiabilite moteur."""
    if reliability is None:
        return ""

    rating = getattr(reliability, "rating", None) or getattr(reliability, "score", None)
    engine_code = getattr(reliability, "engine_code", None) or getattr(reliability, "engine", "")
    note = getattr(reliability, "note", "") or getattr(reliability, "notes", "")

    if rating is None:
        return ""

    rating_float = float(rating) if rating else 0.0
    stars = _stars_html(rating_float)

    return f"""
<h2>Fiabilité moteur</h2>
<div class="card">
    <p class="stars">{stars}</p>
    <p><strong>Score :</strong> {rating_float:.1f} / 5</p>
    <p class="text-small text-gray">Code moteur : {_safe_str(engine_code)}</p>
    <p class="text-small">{_safe_str(note)}</p>
</div>
"""


def _build_tire_section(tire_data: dict | None) -> str:
    """Section 8 — Pneus."""
    if not tire_data:
        return ""

    sizes = tire_data.get("sizes") or tire_data.get("dimensions") or []
    source = tire_data.get("source", "")

    if not sizes:
        return ""

    md_lines = ["## Pneus\n"]
    for size in sizes:
        if isinstance(size, dict):
            dim = size.get("dimension") or size.get("size", "")
            md_lines.append(f"- {_safe_str(dim)}")
        else:
            md_lines.append(f"- {_safe_str(size)}")

    if source:
        md_lines.append(f"\n*Source : {_safe_str(source)}*")

    return _md_to_html("\n".join(md_lines))


def _build_signals_section(warnings: list[FilterResultDB]) -> str:
    """Section 9 — Signaux d'alerte."""
    if not warnings:
        return ""

    html_parts = ["<h2>Signaux d'alerte</h2>"]

    # Trier : fail d'abord, warning ensuite
    sorted_warnings = sorted(warnings, key=lambda w: (0 if w.status == "fail" else 1))

    for fr in sorted_warnings:
        name = FILTER_NAMES.get(fr.filter_id, fr.filter_id)
        badge = _badge_html(fr.status)
        message = _safe_str(fr.message or "")
        card_class = "card-danger" if fr.status == "fail" else "card-warning"

        # Takata prominent display
        details = fr.details if isinstance(fr.details, dict) else {}
        is_takata = details.get("type") == "takata_airbag" or details.get("takata_airbag") is True

        if is_takata and details.get("severite") == "critical":
            card_class = "card-danger"

        takata_warning = ""
        if is_takata:
            takata_warning = (
                '<p style="font-weight: 700; color: var(--red);">'
                "RAPPEL CRITIQUE — Airbag Takata"
                "</p>"
            )

        html_parts.append(f"""
<div class="card {card_class}">
    <p><strong>{_safe_str(name)}</strong> {badge}</p>
    {takata_warning}
    <p>{message}</p>
</div>
""")

    return "\n".join(html_parts)


def _build_email_section(email_draft: EmailDraft | None) -> str:
    """Section 10 — Email vendeur."""
    if not email_draft:
        return ""

    text = email_draft.edited_text or email_draft.generated_text or ""
    if not text.strip():
        return ""

    # Nettoyer le texte (retirer bullets/puces parasites en fin de texte)
    clean = text.strip().rstrip("•·\u2022\u2023\u25cf\u25cb -")
    # Convertir en blockquote Markdown (garder les lignes vides pour les paragraphes)
    quoted_lines = []
    for line in clean.strip().splitlines():
        quoted_lines.append(f"> {line}" if line.strip() else ">")
    md_text = "\n".join(quoted_lines)

    header = "## Email vendeur\n\n*Email généré automatiquement par Gemini*\n\n"
    return _md_to_html(header + md_text)


# ---------------------------------------------------------------------------
# Assemblage
# ---------------------------------------------------------------------------


def _build_report_sections(
    scan: ScanLog,
    filter_results: list[FilterResultDB],
    email_draft: EmailDraft | None,
) -> list[str]:
    """Genere la liste des sections HTML du rapport."""
    raw = scan.raw_data or {}
    sections: list[str] = []

    # 1. Hero
    sections.append(_build_hero_section(scan, raw, filter_results))

    # 2. Score
    sections.append(_build_score_section(scan.score))

    # 3. Infos vehicule
    info_section = _build_vehicle_info_section(scan, raw)
    if info_section:
        sections.append(info_section)

    # 4. Prix vs marche
    l4 = _find_filter_result(filter_results, "L4")
    market_section = _build_market_section(scan, l4)
    if market_section:
        sections.append(market_section)

    # 5. Kilometrage
    l3 = _find_filter_result(filter_results, "L3")
    km_section = _build_km_section(l3)
    if km_section:
        sections.append(km_section)

    # 6. Resultats filtres
    filters_section = _build_filters_section(filter_results)
    if filters_section:
        sections.append(filters_section)

    # 7. Fiabilite moteur
    year = raw.get("year") or raw.get("annee")
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    reliability = _get_engine_reliability_safe(raw, scan.vehicle_make, scan.vehicle_model)
    rel_section = _build_reliability_section(reliability)
    if rel_section:
        sections.append(rel_section)

    # 8. Pneus
    tire_data = _get_tire_sizes_safe(scan.vehicle_make or "", scan.vehicle_model or "", year)
    tire_section = _build_tire_section(tire_data)
    if tire_section:
        sections.append(tire_section)

    # 9. Signaux d'alerte
    warning_results = [fr for fr in filter_results if fr.status in ("warning", "fail")]
    signals_section = _build_signals_section(warning_results)
    if signals_section:
        sections.append(signals_section)

    # 10. Email vendeur
    email_section = _build_email_section(email_draft)
    if email_section:
        sections.append(email_section)

    return sections


def _assemble_html(scan: ScanLog, sections: list[str]) -> str:
    """Assemble les sections dans le template HTML avec CSS inline."""
    # Lire le template
    template_dir = os.path.join(current_app.root_path, "templates")
    template_path = os.path.join(template_dir, "report_base.html")
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()

    # Lire le CSS
    css_path = os.path.join(current_app.root_path, "static", "report.css")
    with open(css_path, encoding="utf-8") as fh:
        css_content = fh.read()

    # Inliner le CSS (remplacer le link par un <style>)
    template = re.sub(
        r'<link\s+rel="stylesheet"\s+href="report\.css"\s*/?>',
        f"<style>\n{css_content}\n</style>",
        template,
    )

    # Contenu assemble
    content_html = "\n".join(sections)

    # Remplacements de variables template
    brand = _brand_display(scan.vehicle_make)
    logo_url = _brand_logo_url(scan.vehicle_make)
    generated_date = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    template = template.replace("{{ content }}", content_html)
    template = template.replace("{{ brand_name }}", _safe_str(brand))
    template = template.replace("{{ generated_date }}", generated_date)
    template = template.replace("{{ scan_id }}", str(scan.id))

    if logo_url:
        template = template.replace("{{ brand_logo_url }}", logo_url)
    else:
        # Supprimer la balise img si pas de logo
        template = re.sub(
            r'<img\s+class="brand-logo"[^>]*>',
            "",
            template,
        )

    # Nettoyer tout template tag restant
    template = re.sub(r"\{\{[^}]*\}\}", "", template)

    return template


# ---------------------------------------------------------------------------
# Point d'entree public
# ---------------------------------------------------------------------------


def generate_scan_report_pdf(scan_id: int) -> bytes:
    """Genere le rapport PDF complet pour un scan et retourne les bytes.

    Raises:
        ValueError: si le scan n'existe pas.
    """
    scan = db.session.get(ScanLog, scan_id)
    if not scan:
        raise ValueError(f"Scan {scan_id} introuvable")

    filter_results = FilterResultDB.query.filter_by(scan_id=scan_id).all()
    filter_results.sort(key=lambda item: _filter_sort_key(item.filter_id))

    # Email draft — chercher le plus recent
    email_draft = (
        EmailDraft.query.filter_by(scan_id=scan_id).order_by(EmailDraft.created_at.desc()).first()
    )

    # Auto-generation si pas de draft et pas en mode test
    if email_draft is None and not current_app.testing:
        try:
            from app.services.email_service import generate_email_draft

            email_draft = generate_email_draft(scan_id)
        except (
            ConnectionError,
            ValueError,
            RuntimeError,
            OSError,
            TypeError,
            ImportError,
            AttributeError,
        ):
            logger.warning("Auto-generation email echouee pour scan %s", scan_id, exc_info=True)

    # Construction des sections
    sections = _build_report_sections(scan, filter_results, email_draft)

    # Assemblage HTML
    html_content = _assemble_html(scan, sections)

    # Rendu PDF (import lazy pour eviter une dependance native au chargement du module)
    from weasyprint import HTML as WeasyprintHTML

    pdf_bytes: bytes = WeasyprintHTML(string=html_content).write_pdf()

    return pdf_bytes
