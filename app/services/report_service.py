"""Service de generation de rapport PDF pour un scan OKazCar.

Genere un PDF complet a partir d'un ScanLog : score circulaire, mini-cards resume,
insight prix/km, fiches filtres, infos vehicule, pneus, fiabilite moteur, email.

Le PDF suit la charte graphique OKazCar (navy/bleu/orange) et utilise fpdf2.
La classe OKazCarPDF herite de FPDF pour gerer les headers/footers personnalises.

Contrainte fpdf2 : tout le texte doit etre compatible latin-1, d'ou _safe_str()
qui remplace les caracteres Unicode problematiques avant injection.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import current_app
from fpdf import FPDF
from fpdf.enums import RenderStyle

from app.extensions import db
from app.models.email_draft import EmailDraft
from app.models.filter_result import FilterResultDB
from app.models.scan import ScanLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Verdict textuel affiche sous le score circulaire dans le PDF.
# Les seuils sont alignes sur ceux de l'extension Chrome.
VERDICTS = {
    range(80, 101): "Excellente annonce",
    range(60, 80): "Bonne annonce",
    range(40, 60): "Annonce correcte",
    range(0, 40): "Annonce risquée",
}

# Labels humains pour chaque status de filtre, affiches dans les badges PDF.
# Plusieurs status internes ("skip", "neutral", "missing", "skipped") sont
# regroupes sous "Manquant" pour simplifier la lecture utilisateur.
STATUS_LABELS = {
    "pass": "OK",
    "warning": "Attention",
    "fail": "Alerte",
    "skip": "Manquant",
    "neutral": "Manquant",
    "missing": "Manquant",
    "skipped": "Manquant",
    "error": "Erreur",
}

# Noms lisibles des filtres pour l'affichage dans les cards du rapport.
# Doit rester synchronise avec les filter_id du moteur (engine.py).
FILTER_NAMES = {
    "L1": "Extraction des données",
    "L2": "Véhicule reconnu",
    "L3": "Cohérence km/année",
    "L4": "Prix vs marché",
    "L5": "Analyse statistique",
    "L6": "Téléphone vendeur",
    "L7": "SIRET / vendeur pro",
    "L8": "Détection import",
    "L9": "Évaluation globale",
    "L10": "Ancienneté annonce",
    "L11": "Rappels constructeur",
}

# Ordre d'affichage garanti L1 -> L11 dans le PDF
FILTER_SEQUENCE = tuple(f"L{i}" for i in range(1, 12))

# Labels humains pour les sources de prix (affiches dans la section marche)
SOURCE_LABELS = {
    "marche_leboncoin": "LeBonCoin",
    "marche_autoscout24": "AutoScout24",
    "argus_seed": "Argus",
    "estimation_lbc": "Estimation LeBonCoin",
    "cote_lacentrale": "Côte La Centrale",
    "allopneus": "Allopneus",
    "wheel-size": "Wheel-Size",
}

# Sites officiels des constructeurs -- utilises pour le lien "site officiel"
# dans le rapport et pour generer l'URL du logo via Clearbit.
BRAND_WEBSITES = {
    "alfa romeo": "https://www.alfaromeo.com",
    "audi": "https://www.audi.com",
    "bmw": "https://www.bmw.com",
    "citroen": "https://www.citroen.com",
    "cupra": "https://www.cupraofficial.com",
    "dacia": "https://www.dacia.com",
    "ds": "https://www.dsautomobiles.com",
    "fiat": "https://www.fiat.com",
    "ford": "https://www.ford.com",
    "honda": "https://www.honda.com",
    "hyundai": "https://www.hyundai.com",
    "jeep": "https://www.jeep.com",
    "kia": "https://www.kia.com",
    "land rover": "https://www.landrover.com",
    "mazda": "https://www.mazda.com",
    "mercedes": "https://www.mercedes-benz.com",
    "mini": "https://www.mini.com",
    "nissan": "https://www.nissan-global.com",
    "opel": "https://www.opel.com",
    "peugeot": "https://www.peugeot.com",
    "porsche": "https://www.porsche.com",
    "renault": "https://www.renault.com",
    "seat": "https://www.seat.com",
    "skoda": "https://www.skoda-auto.com",
    "suzuki": "https://www.globalsuzuki.com",
    "tesla": "https://www.tesla.com",
    "toyota": "https://www.toyota.com",
    "volkswagen": "https://www.volkswagen.com",
    "volvo": "https://www.volvocars.com",
}

# ---------------------------------------------------------------------------
# Palette OKazCar (charte site web + extension)
# ---------------------------------------------------------------------------
COLOR_NAVY = (15, 23, 42)  # #0f172a — header, textes forts
COLOR_BLUE = (59, 130, 246)  # #3b82f6 — accent "OKaz", liens
COLOR_ORANGE = (249, 115, 22)  # #f97316 — accent "Car"
COLOR_GREEN = (34, 197, 94)  # #22c55e — OK / pass
COLOR_AMBER = (245, 158, 11)  # #f59e0b — warning / attention
COLOR_RED = (239, 68, 68)  # #ef4444 — fail / alerte
COLOR_WHITE = (255, 255, 255)
COLOR_LIGHT_GRAY = (241, 245, 249)  # #f1f5f9 — fond cards
COLOR_GRAY_TEXT = (100, 116, 139)  # #64748b — texte secondaire
COLOR_GRAY_BORDER = (226, 232, 240)  # #e2e8f0 — bordures
COLOR_SOFT_GREEN = (240, 253, 244)
COLOR_SOFT_AMBER = (255, 251, 235)
COLOR_SOFT_RED = (254, 242, 242)
COLOR_SOFT_BLUE = (239, 246, 255)

# Filtres affiches dans la grille 2x3 de mini-cards en page 1.
# On ne met que les filtres les plus parlants pour l'utilisateur.
_SUMMARY_CARD_FILTERS = [
    ("L4", "Prix marche"),
    ("L3", "Kilometrage"),
    ("L6", "Telephone"),
    ("L7", "Vendeur"),
    ("L8", "Import"),
    ("L9", "Evaluation"),
]


def _verdict_for_score(score: int | None) -> str:
    """Retourne le verdict textuel correspondant au score (0-100)."""
    if score is None:
        return "Score indisponible"
    for rng, label in VERDICTS.items():
        if score in rng:
            return label
    return "Score indisponible"


def _verdict_color(score: int | None) -> tuple[int, int, int]:
    """Couleur RGB associee au score -- vert/bleu/ambre/rouge selon les seuils."""
    if score is None:
        return COLOR_GRAY_TEXT
    if score >= 80:
        return COLOR_GREEN
    if score >= 60:
        return COLOR_BLUE
    if score >= 40:
        return COLOR_AMBER
    return COLOR_RED


def _status_color(status: str) -> tuple[int, int, int]:
    """Retourne la couleur RGB du dot de status dans les mini-cards."""
    mapping = {
        "pass": COLOR_GREEN,
        "warning": COLOR_AMBER,
        "fail": COLOR_RED,
        "skip": COLOR_GRAY_TEXT,
        "neutral": COLOR_GRAY_TEXT,
        "missing": COLOR_GRAY_TEXT,
        "skipped": COLOR_GRAY_TEXT,
        "error": COLOR_RED,
    }
    return mapping.get(status, COLOR_GRAY_TEXT)


def _status_palette(status: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Retourne (couleur_accent, couleur_fond) pour un status -- sert aux cards teintees."""
    if status == "pass":
        return COLOR_GREEN, COLOR_SOFT_GREEN
    if status == "fail":
        return COLOR_RED, COLOR_SOFT_RED
    if status == "warning":
        return COLOR_AMBER, COLOR_SOFT_AMBER
    # default — gray
    return COLOR_GRAY_TEXT, COLOR_LIGHT_GRAY


def _safe_str(value: object) -> str:
    """Convertit en string compatible latin-1 pour fpdf2, retourne '' si None."""
    if value is None:
        return ""
    text = str(value)
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "\u2022": "-",
        "\u2605": "*",
        "\u2606": "*",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _filter_sort_key(filter_id: str) -> tuple[int, str]:
    """Cle de tri pour afficher les filtres dans l'ordre L1..L11."""
    if filter_id in FILTER_SEQUENCE:
        return FILTER_SEQUENCE.index(filter_id), filter_id

    match = re.fullmatch(r"L(\d+)", filter_id or "")
    if match:
        return int(match.group(1)) - 1, filter_id

    return 999, filter_id or ""


def _format_number(value: object) -> str:
    """Formate un nombre avec separateur de milliers (espace). Ex: 12500 -> '12 500'."""
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return _safe_str(value)


def _format_price(value: object, currency: str = "EUR") -> str:
    """Formate un prix avec devise. Ex: 15000 -> '15 000 EUR'."""
    if value in (None, ""):
        return ""
    return f"{_format_number(value)} {currency}"


def _source_label(source: str | None) -> str:
    """Convertit un identifiant source interne en label lisible."""
    if not source:
        return ""
    return SOURCE_LABELS.get(source, source.replace("_", " ").title())


def _brand_website(brand: str | None) -> str | None:
    """Retourne l'URL du site officiel du constructeur, ou None."""
    if not brand:
        return None
    from app.services.vehicle_lookup import normalize_brand

    canonical = normalize_brand(brand)
    return BRAND_WEBSITES.get(canonical)


def _brand_logo_url(brand: str | None) -> str | None:
    """Genere l'URL du logo constructeur via l'API Clearbit (gratuite, basee sur le domaine)."""
    website = _brand_website(brand)
    if not website:
        return None

    domain = urlparse(website).netloc.lower().replace("www.", "")
    if not domain:
        return None

    return f"https://logo.clearbit.com/{domain}"


def _brand_display(brand: str | None) -> str:
    """Forme d'affichage canonique de la marque (ex: 'bmw' -> 'BMW')."""
    if not brand:
        return ""
    from app.services.vehicle_lookup import display_brand

    return display_brand(brand)


def _model_display(model: str | None) -> str:
    """Forme d'affichage canonique du modele (ex: 'chr' -> 'C-HR')."""
    if not model:
        return ""
    from app.services.vehicle_lookup import display_model

    return display_model(model)


def _find_filter_result(results: list[FilterResultDB], filter_id: str) -> FilterResultDB | None:
    """Cherche un FilterResultDB par filter_id dans la liste."""
    for result in results:
        if result.filter_id == filter_id:
            return result
    return None


def _get_tire_sizes_safe(make: str, model: str, year: int | None) -> dict | None:
    """Récupère les pneus depuis le cache uniquement, sans appel réseau."""
    if not make or not model or not year:
        return None
    try:
        from app.services.tire_service import get_cached_tire_sizes

        return get_cached_tire_sizes(make, model, year)
    except (ImportError, ValueError, TypeError, RuntimeError, OSError):
        logger.debug("Tire sizes lookup failed for %s %s %s", make, model, year)
        return None


def _get_engine_reliability_safe(raw_data: dict | None, make: str | None, model: str | None):
    """Appel best-effort au service de fiabilite moteur.

    Cherche le vehicule, itere sur ses specs pour trouver un engine code
    avec des donnees de fiabilite. Retourne None silencieusement en cas d'echec
    pour ne jamais bloquer la generation du PDF.
    """
    if not raw_data or not make or not model:
        return None
    try:
        from app.models.vehicle import VehicleSpec
        from app.services.engine_reliability_service import get_engine_reliability
        from app.services.vehicle_lookup import find_vehicle

        veh = find_vehicle(make, model)
        if not veh:
            return None

        specs = (
            VehicleSpec.query.filter_by(vehicle_id=veh.id)
            .order_by(VehicleSpec.power_hp.desc())
            .all()
        )
        if not specs:
            return None

        fuel_type = raw_data.get("fuel") or raw_data.get("fuel_type")
        for spec in specs:
            if not spec.engine:
                continue
            rel = get_engine_reliability(spec.engine, fuel_type)
            if rel:
                return rel
        return None
    except (ImportError, ValueError, TypeError, RuntimeError, AttributeError, OSError):
        logger.debug("Engine reliability lookup failed for %s %s", make, model)
        return None


# ---------------------------------------------------------------------------
# Mini-cards summary helpers
# ---------------------------------------------------------------------------


def _summary_short_message(fr: FilterResultDB | None) -> str:
    """Retourne un message court pour une mini-card résumé."""
    if fr is None:
        return "Non analyse"
    status = fr.status or ""
    label = STATUS_LABELS.get(status, status)
    msg = _safe_str(fr.message or "")
    if len(msg) > 30:
        msg = msg[:27] + "..."
    return msg if msg else label


def _summary_price_label(fr: FilterResultDB | None) -> str:
    """Label court pour la mini-card prix."""
    if fr is None:
        return "N/A"
    details = fr.details if isinstance(fr.details, dict) else {}
    delta = details.get("delta_eur")
    delta_pct = details.get("delta_pct")
    if isinstance(delta, (int, float)) and isinstance(delta_pct, (int, float)):
        sign = "+" if delta > 0 else ""
        return f"{sign}{_format_number(delta)} EUR ({delta_pct:+.1f}%)"
    return _summary_short_message(fr)


def _summary_km_label(fr: FilterResultDB | None) -> str:
    """Label court pour la mini-card kilométrage."""
    if fr is None:
        return "N/A"
    details = fr.details if isinstance(fr.details, dict) else {}
    actual = details.get("mileage_km")
    expected = details.get("expected_km")
    if actual is not None and expected is not None:
        return f"{_format_number(actual)} / {_format_number(expected)} km"
    return _summary_short_message(fr)


# ---------------------------------------------------------------------------
# Classe PDF OKazCar
# ---------------------------------------------------------------------------


class OKazCarPDF(FPDF):
    """PDF personnalise avec header/footer OKazCar.

    Herite de FPDF (fpdf2) pour surcharger header() et footer().
    Page 1 : header complet (bande navy, logo OKaz/Car, badge marque).
    Pages 2+ : header light (fine bande, numero de page).
    Footer : ligne de separation + horodatage + scan ID.
    """

    def __init__(
        self,
        scan_id: int | None = None,
        brand_name: str | None = None,
        brand_website: str | None = None,
        brand_logo_url: str | None = None,
    ):
        super().__init__()
        self.scan_id = scan_id
        self.brand_name = brand_name
        self.brand_website = brand_website
        self.brand_logo_url = brand_logo_url
        self.set_auto_page_break(auto=True, margin=25)

    # --- Brand badge ---

    def _render_brand_badge(self, x: float, y: float, width: float, height: float) -> None:
        self.set_fill_color(*COLOR_SOFT_BLUE)
        self.set_draw_color(*COLOR_BLUE)
        self.rect(x, y, width, height, style="DF")
        self.set_xy(x, y + 3)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(*COLOR_BLUE)
        self.cell(width, 5, _safe_str(self.brand_name or "MARQUE"), align="C")

    # --- Task 3: Header full (page 1) / light (pages 2+) ---

    def _header_full(self):
        """Header complet pour la page 1 — bande navy, logo OKazCar, sous-titre."""
        # Bande navy pleine largeur
        self.set_fill_color(*COLOR_NAVY)
        self.rect(0, 0, 210, 28, style="F")

        # "OKaz" en bleu + "Car" en orange
        self.set_xy(10, 6)
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*COLOR_BLUE)
        okaz_w = self.get_string_width("OKaz")
        self.cell(okaz_w, 10, "OKaz")
        self.set_text_color(*COLOR_ORANGE)
        self.cell(30, 10, "Car")

        # Badge marque en haut à droite
        logo_drawn = False
        if self.brand_logo_url and not current_app.testing:
            try:
                self.image(self.brand_logo_url, x=170, y=4, w=24, h=20, link=self.brand_website)
                logo_drawn = True
            except (RuntimeError, OSError, ValueError):
                logger.debug("Brand logo render skipped for %s", self.brand_logo_url)

        if not logo_drawn and self.brand_name:
            self._render_brand_badge(164, 8, 30, 12)

        # Sous-titre
        self.set_xy(10, 18)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*COLOR_GRAY_TEXT)
        self.cell(0, 5, "Rapport d'analyse d'annonce automobile")

        # Passe sous la bande
        self.set_y(30)

        # Ligne bleue séparatrice
        self.set_draw_color(*COLOR_BLUE)
        self.set_line_width(0.7)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def _header_light(self):
        """Header allégé pour les pages 2+ — fine bande navy + numéro de page."""
        # Fine bande navy
        self.set_fill_color(*COLOR_NAVY)
        self.rect(0, 0, 210, 12, style="F")

        # "OKazCar" petit
        self.set_xy(10, 2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*COLOR_BLUE)
        okaz_w = self.get_string_width("OKaz")
        self.cell(okaz_w, 8, "OKaz")
        self.set_text_color(*COLOR_ORANGE)
        self.cell(20, 8, "Car")

        # Numéro de page à droite
        self.set_xy(170, 2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*COLOR_WHITE)
        self.cell(30, 8, f"Page {self.page}", align="R")

        self.set_y(14)
        # Ligne bleue
        self.set_draw_color(*COLOR_BLUE)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def header(self):
        if self.page == 1:
            self._header_full()
        else:
            self._header_light()

    # --- Task 10: Footer amélioré ---

    def footer(self):
        self.set_y(-20)
        self.set_draw_color(*COLOR_GRAY_BORDER)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(*COLOR_GRAY_TEXT)
        now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        left_text = f"Genere par OKazCar | okazcar.com | {now_str}"
        if self.scan_id:
            left_text += f" | Scan #{self.scan_id}"
        self.cell(0, 5, left_text, align="C")

    # --- Task 10: section_title amélioré ---

    def section_title(self, title: str):
        self.ln(6)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*COLOR_NAVY)
        self.cell(0, 9, _safe_str(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*COLOR_BLUE)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 55, self.get_y())
        self.ln(5)

    def info_row(self, label: str, value: str, bold_value: bool = False):
        """Affiche une ligne label/valeur dans la section infos vehicule."""
        if not value:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*COLOR_GRAY_TEXT)
        self.cell(50, 6, _safe_str(label), new_x="END")
        self.set_font("Helvetica", "B" if bold_value else "", 9)
        self.set_text_color(*COLOR_NAVY)
        self.cell(0, 6, _safe_str(value), new_x="LMARGIN", new_y="NEXT")


# ---------------------------------------------------------------------------
# Génération du rapport
# ---------------------------------------------------------------------------


def generate_scan_report_pdf(scan_id: int) -> bytes:
    """Point d'entree principal : genere le PDF complet pour un scan.

    Architecture du rapport :
    - Page 1 : score circulaire, grille resume 2x3, insight prix, insight km
    - Page 2+ : fiche vehicule, cards filtres L1-L11, pneus, fiabilite, email

    Retourne le PDF sous forme de bytes (pret a servir en reponse HTTP).
    """
    scan = db.session.get(ScanLog, scan_id)
    if not scan:
        raise ValueError(f"Scan {scan_id} introuvable")

    filter_results = FilterResultDB.query.filter_by(scan_id=scan_id).all()
    filter_results.sort(key=lambda item: _filter_sort_key(item.filter_id))

    email_draft = (
        EmailDraft.query.filter_by(scan_id=scan_id).order_by(EmailDraft.created_at.desc()).first()
    )

    raw = scan.raw_data or {}

    pdf = OKazCarPDF(
        scan_id=scan_id,
        brand_name=_brand_display(scan.vehicle_make),
        brand_website=_brand_website(scan.vehicle_make),
        brand_logo_url=_brand_logo_url(scan.vehicle_make),
    )

    # -- Page 1 : vue d'ensemble rapide --
    pdf.add_page()
    _render_score_box(pdf, scan.score)
    _render_summary_cards(pdf, filter_results)
    _render_market_insight(pdf, scan, filter_results)
    _render_km_insight(pdf, filter_results)

    # -- Pages suivantes : details complets --
    # Saut de page seulement si on est encore sur la page 1
    # (le contenu km peut deja avoir declenche un saut automatique)
    if pdf.page == 1:
        pdf.add_page()
    _render_vehicle_info(pdf, scan, raw)

    if filter_results:
        _render_filter_cards(pdf, filter_results)

    year = raw.get("year") or raw.get("annee")
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    tire_data = _get_tire_sizes_safe(scan.vehicle_make or "", scan.vehicle_model or "", year)
    if tire_data:
        _render_tire_section(pdf, tire_data)

    reliability = _get_engine_reliability_safe(raw, scan.vehicle_make, scan.vehicle_model)
    if reliability:
        _render_reliability_section(pdf, reliability)

    if email_draft and email_draft.generated_text:
        _render_email_section(pdf, email_draft)

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Task 4: Score circulaire
# ---------------------------------------------------------------------------


def _render_score_box(pdf: OKazCarPDF, score: int | None):
    """Dessine le cercle de score avec arc colore proportionnel + verdict texte a droite.

    Le cercle gris de fond represente 100%, l'arc colore la portion atteinte.
    L'arc est dessine dans le sens horaire en partant de 12h (90 degres en coordonnees fpdf).
    """
    color = _verdict_color(score)
    verdict = _verdict_for_score(score)
    y_start = pdf.get_y()

    # Cercle de fond gris
    circle_x = 40
    circle_y = y_start + 20
    circle_r = 16

    pdf.set_draw_color(*COLOR_GRAY_BORDER)
    pdf.set_line_width(3)
    pdf.circle(circle_x, circle_y, circle_r, style="D")

    # Arc coloré proportionnel au score
    if score is not None and score > 0:
        end_angle = 90 - (score / 100) * 360
        start_angle = 90
        pdf.set_draw_color(*color)
        pdf.set_line_width(3)
        pdf.arc(
            circle_x, circle_y, circle_r, start_angle=end_angle, end_angle=start_angle, style="D"
        )

    # Score au centre
    score_text = str(score) if score is not None else "N/A"
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*color)
    score_w = pdf.get_string_width(score_text)
    pdf.set_xy(circle_x - score_w / 2, circle_y - 9)
    pdf.cell(score_w, 10, score_text, align="C")

    # "/100" sous le score
    if score is not None:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        sub_text = "/100"
        sub_w = pdf.get_string_width(sub_text)
        pdf.set_xy(circle_x - sub_w / 2, circle_y + 2)
        pdf.cell(sub_w, 6, sub_text, align="C")

    # Verdict à droite du cercle
    pdf.set_xy(circle_x + circle_r + 10, circle_y - 8)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*color)
    pdf.cell(100, 10, verdict)

    # Sous-texte verdict
    pdf.set_xy(circle_x + circle_r + 10, circle_y + 2)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_GRAY_TEXT)
    pdf.cell(100, 6, "Score de confiance OKazCar")

    pdf.set_y(y_start + 44)


# ---------------------------------------------------------------------------
# Task 5: Mini-cards résumé grille 2x3
# ---------------------------------------------------------------------------


def _render_summary_cards(pdf: OKazCarPDF, results: list[FilterResultDB]):
    """Grille 2x3 de mini-cards résumant les filtres clés."""
    if not results:
        return

    card_w = 58
    card_h = 18
    gap_x = 5
    gap_y = 4
    cols = 3
    x_start = pdf.l_margin
    y_start = pdf.get_y() + 2

    for idx, (fid, card_title) in enumerate(_SUMMARY_CARD_FILTERS):
        col = idx % cols
        row = idx // cols
        x = x_start + col * (card_w + gap_x)
        y = y_start + row * (card_h + gap_y)

        fr = _find_filter_result(results, fid)
        status = fr.status if fr else "skip"
        dot_color = _status_color(status)

        # Valeur affichée
        if fid == "L4":
            value_text = _summary_price_label(fr)
        elif fid == "L3":
            value_text = _summary_km_label(fr)
        else:
            value_text = _summary_short_message(fr)

        # Card arrondie blanche
        pdf.set_fill_color(*COLOR_WHITE)
        pdf.set_draw_color(*COLOR_GRAY_BORDER)
        pdf._draw_rounded_rect(x, y, card_w, card_h, style=RenderStyle.DF, round_corners=True, r=3)

        # Dot de status
        pdf.set_fill_color(*dot_color)
        pdf.ellipse(x + 3, y + 3, 3, 3, style="F")

        # Titre en petit gris
        pdf.set_xy(x + 8, y + 2)
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(card_w - 10, 4, _safe_str(card_title).upper())

        # Valeur en gras
        pdf.set_xy(x + 3, y + 8)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*COLOR_NAVY)
        truncated = value_text[:35] + "..." if len(value_text) > 38 else value_text
        pdf.cell(card_w - 6, 6, _safe_str(truncated))

    total_rows = (len(_SUMMARY_CARD_FILTERS) + cols - 1) // cols
    pdf.set_y(y_start + total_rows * (card_h + gap_y) + 2)


# ---------------------------------------------------------------------------
# Task 6: Info cards arrondies + Argus section
# ---------------------------------------------------------------------------


def _draw_info_card(
    pdf: OKazCarPDF,
    title: str,
    headline: str,
    subheadline: str,
    accent_color: tuple[int, int, int],
    background_color: tuple[int, int, int],
):
    """Dessine une card arrondie avec titre de section, headline et sous-texte.

    Reutilisee par les sections prix marche et km pour un rendu uniforme.
    La couleur d'accent et le fond sont choisis selon le status du filtre.
    """
    pdf.section_title(title)
    x = 10
    y = pdf.get_y()
    width = 190
    height = 24
    pdf.set_fill_color(*background_color)
    pdf.set_draw_color(*accent_color)
    pdf._draw_rounded_rect(x, y, width, height, style=RenderStyle.DF, round_corners=True, r=4)
    pdf.set_xy(x + 4, y + 4)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*accent_color)
    pdf.cell(width - 8, 6, _safe_str(headline), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x + 4)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*COLOR_NAVY)
    pdf.multi_cell(width - 8, 5, _safe_str(subheadline))
    pdf.ln(2)


def _body_multi_cell(pdf: OKazCarPDF, text: str) -> None:
    """Ecrit un bloc de texte multi-ligne sur toute la largeur utile."""
    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(content_width, 5, _safe_str(text))


def _render_market_insight(pdf: OKazCarPDF, scan: ScanLog, results: list[FilterResultDB]):
    """Section prix marche : card info + barre de positionnement + details Argus.

    Affiche une barre horizontale avec le prix marche au centre et le prix annonce
    positionne en fonction de l'ecart en %. Le dot de couleur (vert/ambre/rouge)
    indique visuellement si le prix est bon, acceptable ou risque.
    """
    l4 = _find_filter_result(results, "L4")
    details = l4.details if l4 and isinstance(l4.details, dict) else None
    if not l4 or not details:
        return

    ref_price = details.get("price_reference")
    if ref_price is None:
        primary = details.get("reference_primary") or {}
        if isinstance(primary, dict):
            ref_price = primary.get("price")
    if ref_price is None:
        return

    announce_price = details.get("price_annonce") or scan.price_eur
    delta = details.get("delta_eur")
    delta_pct = details.get("delta_pct")
    source_label = _source_label(details.get("source"))
    sample_count = details.get("sample_count")
    accent_color, background_color = _status_palette(l4.status)

    if isinstance(delta, (int, float)):
        direction = "au-dessus" if delta > 0 else "en dessous"
        headline = f"{_format_price(abs(delta))} {direction} du marche"
    else:
        headline = l4.message

    subheadline = l4.message
    if delta_pct is not None:
        subheadline += f" - Ecart {float(delta_pct):+.1f}%"

    _draw_info_card(
        pdf,
        "Prix vs marche",
        headline,
        subheadline,
        accent_color,
        background_color,
    )

    # -- Barre de positionnement prix --
    # Barre grise horizontale avec le prix marche au centre (trait navy)
    # et le prix annonce positionne en % de l'ecart (dot colore)
    bar_y = pdf.get_y() + 2
    line_x1 = 25
    line_x2 = 185
    center_x = (line_x1 + line_x2) / 2

    # Fond gris de la barre
    pdf.set_draw_color(210, 214, 220)
    pdf.set_line_width(1.4)
    pdf.line(line_x1, bar_y, line_x2, bar_y)

    # Trait vertical navy = prix de reference marche
    pdf.set_draw_color(*COLOR_NAVY)
    pdf.set_line_width(0.8)
    pdf.line(center_x, bar_y - 5, center_x, bar_y + 5)

    # Position du dot annonce : borne a +/- 50% pour eviter de sortir de la barre
    announce_x = center_x
    try:
        delta_pct_float = float(delta_pct or 0)
        bounded_pct = max(min(delta_pct_float, 50.0), -50.0)
        announce_x = center_x + bounded_pct / 50.0 * 55
    except (TypeError, ValueError):
        announce_x = center_x

    # Dot colore = prix de l'annonce
    pdf.set_fill_color(*accent_color)
    pdf.ellipse(announce_x - 2.3, bar_y - 2.3, 4.6, 4.6, style="F")

    # Labels sous la barre
    pdf.set_xy(16, bar_y + 5)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*accent_color)
    pdf.cell(60, 6, _format_price(announce_price), align="L")

    pdf.set_xy(center_x - 28, bar_y + 5)
    pdf.set_text_color(*COLOR_NAVY)
    pdf.cell(56, 6, "MARCHE", align="C")
    pdf.set_xy(center_x - 28, bar_y + 11)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*COLOR_GRAY_TEXT)
    pdf.cell(56, 6, _format_price(ref_price), align="C")
    pdf.ln(24)
    pdf.set_x(pdf.l_margin)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_NAVY)
    if source_label or sample_count:
        source_line = source_label
        if sample_count:
            source_line += f" - base sur {sample_count} annonces"
        _body_multi_cell(pdf, source_line.strip(" -"))

    # Sous-section Argus : card grise arrondie avec la fourchette de cote
    # Affichee uniquement si le filtre L4 a trouve une reference Argus
    if details.get("price_argus_mid"):
        low = details.get("price_argus_low")
        mid = details.get("price_argus_mid")
        high = details.get("price_argus_high")
        argus_line = f"Reference Argus : {_format_price(mid)}"
        if low and high:
            argus_line += f" (fourchette {_format_price(low)} a {_format_price(high)})"

        argus_y = pdf.get_y() + 2
        pdf.set_fill_color(*COLOR_LIGHT_GRAY)
        pdf.set_draw_color(*COLOR_GRAY_BORDER)
        pdf._draw_rounded_rect(
            pdf.l_margin,
            argus_y,
            190,
            14,
            style=RenderStyle.DF,
            round_corners=True,
            r=3,
        )
        pdf.set_xy(pdf.l_margin + 4, argus_y + 3)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(40, 5, "ARGUS")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(140, 5, _safe_str(argus_line))
        pdf.set_y(argus_y + 18)

    # References secondaires (ex: estimation LBC, cote La Centrale)
    secondary = details.get("reference_secondary") or []
    if isinstance(secondary, list):
        for reference in secondary:
            if not isinstance(reference, dict):
                continue
            sec_source = _source_label(reference.get("source"))
            sec_price = reference.get("price")
            if sec_source and sec_price:
                _body_multi_cell(
                    pdf,
                    f"Reference secondaire - {sec_source} : {_format_price(sec_price)}",
                )

    pdf.ln(2)


def _render_km_insight(pdf: OKazCarPDF, results: list[FilterResultDB]):
    """Section km : card info + barre de positionnement km reel vs attendu.

    Meme logique visuelle que la section prix : barre horizontale avec seuil
    attendu au centre et km reel positionne proportionnellement.
    """
    l3 = _find_filter_result(results, "L3")
    details = l3.details if l3 and isinstance(l3.details, dict) else None
    if not l3 or not details:
        return

    actual_km = details.get("mileage_km")
    expected_km = details.get("expected_km")
    if actual_km is None or expected_km in (None, ""):
        return

    accent_color, background_color = _status_palette(l3.status)
    age = details.get("age")
    category = details.get("category")
    avg_km = details.get("avg_km_per_year")
    km_per_year = details.get("km_per_year")

    headline = f"{_format_number(actual_km)} km releves"
    subheadline = l3.message + f" - attendu {_format_number(expected_km)} km"

    _draw_info_card(
        pdf,
        "Kilometrage attendu",
        headline,
        subheadline,
        accent_color,
        background_color,
    )

    # -- Barre de positionnement km --
    # Echelle adaptative : le max de la barre = 125% du plus grand entre reel et attendu
    # Ca garantit que les deux points sont toujours visibles sur la barre
    bar_y = pdf.get_y() + 2
    line_x1 = 25
    line_x2 = 185
    max_km = max(float(actual_km or 0), float(expected_km or 0), 1.0)
    scale_max = max_km * 1.25
    expected_x = line_x1 + (min(float(expected_km), scale_max) / scale_max) * (line_x2 - line_x1)
    actual_x = line_x1 + (min(float(actual_km), scale_max) / scale_max) * (line_x2 - line_x1)
    page_right = pdf.w - pdf.r_margin

    # Fond gris de la barre
    pdf.set_draw_color(210, 214, 220)
    pdf.set_line_width(1.4)
    pdf.line(line_x1, bar_y, line_x2, bar_y)

    pdf.set_draw_color(*COLOR_NAVY)
    pdf.set_line_width(0.8)
    pdf.line(expected_x, bar_y - 5, expected_x, bar_y + 5)

    pdf.set_fill_color(*accent_color)
    pdf.ellipse(actual_x - 2.3, bar_y - 2.3, 4.6, 4.6, style="F")

    pdf.set_xy(16, bar_y + 5)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_GRAY_TEXT)
    pdf.cell(35, 5, "0 km", align="L")

    expected_label_x = max(pdf.l_margin, min(expected_x - 20, page_right - 40))
    pdf.set_xy(expected_label_x, bar_y + 5)
    pdf.cell(40, 5, "Seuil attendu", align="C")

    actual_label_x = max(pdf.l_margin, min(actual_x - 18, page_right - 36))
    pdf.set_xy(actual_label_x, bar_y + 11)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*accent_color)
    pdf.cell(36, 5, _format_number(actual_km), align="C")
    pdf.ln(14)

    # Détails compacts sur une ligne sous le slider
    details_parts = []
    if age is not None:
        details_parts.append(f"{_safe_str(age)} ans")
    if avg_km:
        details_parts.append(f"ref. {_format_number(avg_km)} km/an")
    if km_per_year:
        details_parts.append(f"obs. {_format_number(km_per_year)} km/an")
    if category:
        details_parts.append(_safe_str(category).replace("_", " ").title())

    if details_parts:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(0, 4, " | ".join(details_parts), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


# ---------------------------------------------------------------------------
# Task 7: Filtres en cards visuelles
# ---------------------------------------------------------------------------


def _render_filter_cards(pdf: OKazCarPDF, results: list[FilterResultDB]):
    """Affiche chaque filtre comme une mini-card horizontale arrondie."""
    pdf.section_title("Resultats des filtres")

    for filter_result in results:
        # Gestion saut de page
        if pdf.get_y() + 20 > pdf.h - 30:
            pdf.add_page()

        status = filter_result.status or "skip"
        dot_color, bg_color = _status_palette(status)
        status_label = STATUS_LABELS.get(status, status)
        filter_name = FILTER_NAMES.get(filter_result.filter_id, filter_result.filter_id)
        message = _safe_str(filter_result.message or "")
        if len(message) > 90:
            message = message[:87] + "..."

        x = pdf.l_margin
        y = pdf.get_y()
        w = pdf.w - pdf.l_margin - pdf.r_margin
        h = 16

        # Card arrondie avec fond teinté
        pdf.set_fill_color(*bg_color)
        pdf.set_draw_color(*COLOR_GRAY_BORDER)
        pdf._draw_rounded_rect(x, y, w, h, style=RenderStyle.DF, round_corners=True, r=3)

        # Dot de couleur
        pdf.set_fill_color(*dot_color)
        pdf.ellipse(x + 3, y + 3, 3.5, 3.5, style="F")

        # Titre : "L4 - Prix vs marché" en gras
        pdf.set_xy(x + 9, y + 2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_NAVY)
        title_text = f"{filter_result.filter_id} - {filter_name}"
        pdf.cell(120, 5, _safe_str(title_text))

        # Badge statut à droite
        badge_w = pdf.get_string_width(status_label) + 6
        badge_x = x + w - badge_w - 4
        pdf.set_xy(badge_x, y + 2)
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*dot_color)
        pdf.cell(badge_w, 5, status_label, align="C")

        # Message en dessous
        pdf.set_xy(x + 9, y + 8)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(w - 14, 5, message)

        pdf.set_y(y + h + 2)


# ---------------------------------------------------------------------------
# Task 8: Infos véhicule grille 2 colonnes
# ---------------------------------------------------------------------------


def _render_vehicle_info(pdf: OKazCarPDF, scan: ScanLog, raw: dict):
    """Section infos vehicule : titre, grille 2 colonnes, champs pleine largeur, URL.

    Les donnees viennent du ScanLog (prix, source, pays) et du raw_data (tous les
    champs extraits par L1). La grille 2 colonnes evite que la page soit trop longue.
    """
    pdf.section_title("Informations du vehicule")

    make = _brand_display(scan.vehicle_make or raw.get("make", ""))
    model = _model_display(scan.vehicle_model or raw.get("model", ""))
    year = raw.get("year") or raw.get("annee")

    # Titre véhicule
    title = f"{make} {model}".strip()
    if year:
        title += f" ({year})"
    if title:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(0, 7, _safe_str(title), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # Grille 2 colonnes
    km = raw.get("km") or raw.get("mileage_km") or raw.get("mileage")
    km_str = ""
    if km:
        try:
            km_str = f"{int(km):,} km".replace(",", " ")
        except (ValueError, TypeError):
            km_str = str(km)

    left_col = [
        ("Prix", f"{scan.price_eur:,} EUR".replace(",", " ") if scan.price_eur else ""),
        ("Kilometrage", km_str),
        ("Annee", _safe_str(year)),
        ("Source", _safe_str(scan.source)),
        ("Pays", _safe_str(scan.country)),
    ]

    right_col = [
        ("Carburant", _safe_str(raw.get("fuel") or raw.get("fuel_type") or "")),
        ("Boite", _safe_str(raw.get("gearbox") or raw.get("transmission") or "")),
        ("Puissance", _safe_str(raw.get("power") or raw.get("power_hp") or "")),
        ("Couleur", _safe_str(raw.get("color") or raw.get("couleur") or "")),
        ("Portes", _safe_str(raw.get("doors") or "")),
        ("Carrosserie", _safe_str(raw.get("body_type") or "")),
    ]

    col_w = 90
    y_grid = pdf.get_y()
    left_y = y_grid
    right_y = y_grid

    # Colonne gauche
    for label, value in left_col:
        if not value:
            continue
        pdf.set_xy(pdf.l_margin, left_y)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(35, 5, _safe_str(label))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(col_w - 35, 5, value)
        left_y += 6

    # Colonne droite
    right_x = pdf.l_margin + col_w + 5
    for label, value in right_col:
        if not value:
            continue
        pdf.set_xy(right_x, right_y)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(35, 5, _safe_str(label))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(col_w - 35, 5, value)
        right_y += 6

    pdf.set_y(max(left_y, right_y) + 2)

    # Champs pleine largeur
    full_width_fields = [
        ("Vendeur", _safe_str(raw.get("seller_name") or raw.get("seller") or "")),
        ("Localisation", _safe_str(raw.get("location") or raw.get("city") or "")),
        ("Controle technique", _safe_str(raw.get("technical_inspection") or raw.get("ct") or "")),
        ("Premiere main", _safe_str(raw.get("first_hand") or "")),
    ]

    for label, value in full_width_fields:
        if not value:
            continue
        pdf.info_row(label, value)

    # URL
    if scan.url:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(50, 6, "URL", new_x="END")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*COLOR_BLUE)
        url_display = scan.url if len(scan.url) <= 80 else scan.url[:77] + "..."
        pdf.cell(0, 6, url_display, new_x="LMARGIN", new_y="NEXT")

    # Site officiel
    website = _brand_website(scan.vehicle_make or raw.get("make"))
    if website:
        pdf.info_row("Site officiel", website)


# ---------------------------------------------------------------------------
# Task 9: Pneus en card arrondie verte pâle
# ---------------------------------------------------------------------------


def _render_tire_section(pdf: OKazCarPDF, tire_data: dict):
    """Section pneus : card arrondie verte pale avec les dimensions recommandees.

    Affiche jusqu'a 6 dimensions (au-dela c'est du bruit). La source est
    indiquee en italique en bas de la card (Allopneus ou Wheel-Size).
    """
    dimensions = tire_data.get("dimensions", [])
    if not dimensions:
        return

    pdf.section_title("Dimensions de pneus recommandees")

    x = pdf.l_margin
    y = pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    # Calculer hauteur
    line_count = min(len(dimensions), 6)
    h = 10 + line_count * 6 + (8 if tire_data.get("source") else 0)

    pdf.set_fill_color(*COLOR_SOFT_GREEN)
    pdf.set_draw_color(*COLOR_GREEN)
    pdf._draw_rounded_rect(x, y, w, h, style=RenderStyle.DF, round_corners=True, r=4)

    pdf.set_xy(x + 4, y + 4)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_NAVY)
    for dimension in dimensions[:6]:
        size = dimension.get("size", "")
        if size:
            pdf.set_x(x + 6)
            pdf.cell(0, 5, f"- {size}", new_x="LMARGIN", new_y="NEXT")

    source = tire_data.get("source")
    if source:
        pdf.set_x(x + 6)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(0, 5, f"Source : {_source_label(source)}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(y + h + 4)


# ---------------------------------------------------------------------------
# Task 9: Fiabilité en card arrondie jaune pâle
# ---------------------------------------------------------------------------


def _render_reliability_section(pdf: OKazCarPDF, reliability):
    """Section fiabilite moteur : card arrondie jaune pale avec score et note.

    Affiche le code moteur, la marque, le score /5 et une note textuelle.
    Hauteur dynamique calculee selon les champs presents.
    """
    pdf.section_title("Fiabilite moteur")

    x = pdf.l_margin
    y = pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    # Calculer hauteur approximative
    h = 12
    if hasattr(reliability, "engine_code") and reliability.engine_code:
        h += 6
    if hasattr(reliability, "brand") and reliability.brand:
        h += 6
    if hasattr(reliability, "score") and reliability.score is not None:
        h += 6
    if hasattr(reliability, "note") and reliability.note:
        h += 14

    # Card jaune pâle arrondie
    pdf.set_fill_color(*COLOR_SOFT_AMBER)
    pdf.set_draw_color(*COLOR_AMBER)
    pdf._draw_rounded_rect(x, y, w, h, style=RenderStyle.DF, round_corners=True, r=4)

    inner_y = y + 4
    pdf.set_xy(x + 4, inner_y)

    if hasattr(reliability, "engine_code") and reliability.engine_code:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.set_xy(x + 4, inner_y)
        pdf.cell(35, 5, "Moteur")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(100, 5, _safe_str(reliability.engine_code))
        inner_y += 6

    if hasattr(reliability, "brand") and reliability.brand:
        pdf.set_xy(x + 4, inner_y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(35, 5, "Marque")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(100, 5, _safe_str(reliability.brand))
        inner_y += 6

    if hasattr(reliability, "score") and reliability.score is not None:
        score_val = reliability.score
        stars_str = ""
        if hasattr(reliability, "stars") and reliability.stars is not None:
            stars_str = f" ({_safe_str(reliability.stars)})"
        pdf.set_xy(x + 4, inner_y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.cell(35, 5, "Score fiabilite")
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_NAVY)
        pdf.cell(100, 5, f"{score_val:.1f} / 5{stars_str}")
        inner_y += 6

    if hasattr(reliability, "note") and reliability.note:
        note_text = _safe_str(reliability.note)
        if len(note_text) > 200:
            note_text = note_text[:197] + "..."
        pdf.set_xy(x + 4, inner_y)
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*COLOR_GRAY_TEXT)
        pdf.multi_cell(w - 8, 4, f"Note : {note_text}")

    pdf.set_y(y + h + 4)


# ---------------------------------------------------------------------------
# Email section (inchangée)
# ---------------------------------------------------------------------------


def _render_email_section(pdf: OKazCarPDF, email_draft: EmailDraft):
    """Section email : affiche le brouillon genere par Gemini (tronque a 1500 chars)."""
    pdf.section_title("Email suggere au vendeur")

    pdf.set_fill_color(*COLOR_LIGHT_GRAY)
    pdf.rect(10, pdf.get_y(), 190, 4, style="F")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*COLOR_NAVY)

    text = _safe_str(email_draft.edited_text or email_draft.generated_text)
    if len(text) > 1500:
        text = text[:1497] + "..."

    pdf.multi_cell(0, 4, text)
