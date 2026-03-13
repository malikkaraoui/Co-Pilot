/**
 * Composants visuels SVG : jauge de score et graphe radar.
 * Ces composants sont purement visuels — pas de logique metier ici.
 */

"use strict";

import { scoreColor, statusColor } from '../utils/styles.js';
import { escapeHTML } from '../utils/format.js';

// Labels courts pour les axes du radar — un par filtre actif
export const RADAR_SHORT_LABELS = {
  L1: "Donn\u00E9es", L2: "Mod\u00E8le", L3: "Km", L4: "Prix",
  L5: "Confiance", L6: "T\u00E9l\u00E9phone", L7: "SIRET", L8: "Import",
  L9: "Scan", L10: "Anciennet\u00E9",
};

/**
 * Jauge circulaire SVG avec le score global (0-100).
 * Le cercle se remplit proportionnellement via stroke-dasharray.
 * @param {number} score - Score global de l'annonce (0-100)
 * @returns {string} SVG de la jauge
 */
export function buildGaugeSVG(score) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = scoreColor(score);

  return `
    <svg class="okazcar-gauge" viewBox="0 0 120 120" width="140" height="140">
      <circle cx="60" cy="60" r="${radius}" fill="none" stroke="#e5e7eb" stroke-width="10"/>
      <circle cx="60" cy="60" r="${radius}" fill="none" stroke="${color}" stroke-width="10"
        stroke-dasharray="${progress} ${circumference}"
        stroke-linecap="round"
        transform="rotate(-90 60 60)"
        class="okazcar-gauge-progress"/>
      <text x="60" y="55" text-anchor="middle" class="okazcar-gauge-score" fill="${color}">${score}</text>
      <text x="60" y="72" text-anchor="middle" class="okazcar-gauge-label">/ 100</text>
    </svg>
  `;
}

/**
 * Graphe radar SVG montrant les scores de chaque filtre.
 * On exclut les filtres neutral/skip pour ne garder que les axes pertinents.
 * La couleur du polygone depend du score global (vert/orange/rouge).
 * @param {Array} filters - Tableau de filtres {filter_id, status, score}
 * @param {number} overallScore - Score global pour la couleur du polygone
 * @returns {string} SVG du radar ou chaine vide
 */
export function buildRadarSVG(filters, overallScore) {
  if (!filters || !filters.length) return "";

  // On ne garde que les filtres evaluables pour dessiner le radar
  const activeFilters = filters.filter((f) => f.status !== "neutral" && f.status !== "skip");
  if (!activeFilters.length) return "";

  const cx = 160, cy = 145, R = 100;
  const n = activeFilters.length;
  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2; // Demarre en haut (12h)

  const mainColor = overallScore >= 70 ? "#22c55e"
    : overallScore >= 45 ? "#f59e0b" : "#ef4444";

  /** Coordonnees d'un point sur l'axe i a distance r du centre. */
  function pt(i, r) {
    const angle = startAngle + i * angleStep;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  }

  // Grille : 5 niveaux concentriques (20%, 40%, 60%, 80%, 100%)
  let gridSVG = "";
  for (const pct of [0.2, 0.4, 0.6, 0.8, 1.0]) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const p = pt(i, R * pct);
      pts.push(`${p.x},${p.y}`);
    }
    const cls = pct === 1.0 ? "okazcar-radar-grid-outer" : "okazcar-radar-grid";
    gridSVG += `<polygon points="${pts.join(" ")}" class="${cls}"/>`;
  }

  // Axes : lignes du centre vers chaque sommet
  let axesSVG = "";
  for (let i = 0; i < n; i++) {
    const p = pt(i, R);
    axesSVG += `<line x1="${cx}" y1="${cy}" x2="${p.x}" y2="${p.y}" class="okazcar-radar-axis-line"/>`;
  }

  // Polygone des donnees : chaque sommet positionne selon le score du filtre (0-1)
  const dataPts = [];
  for (let i = 0; i < n; i++) {
    const p = pt(i, R * activeFilters[i].score);
    dataPts.push(`${p.x},${p.y}`);
  }
  const dataStr = dataPts.join(" ");

  // Points et labels sur chaque axe du radar
  let dotsSVG = "";
  let labelsSVG = "";
  const labelPad = 18; // Decalage des labels par rapport au bord
  for (let i = 0; i < n; i++) {
    const f = activeFilters[i];
    const score = f.score;
    const dp = pt(i, R * score);

    // Couleur du point selon le statut du filtre
    let dotColor = "#22c55e";
    if (f.status === "fail") dotColor = "#ef4444";
    else if (f.status === "warning") dotColor = "#f59e0b";
    else if (f.status === "skip") dotColor = "#9ca3af";
    dotsSVG += `<circle cx="${dp.x}" cy="${dp.y}" r="4" fill="${dotColor}" class="okazcar-radar-dot"/>`;

    // Ancrage du label : gauche/droite/centre selon la position sur le radar
    const lp = pt(i, R + labelPad);
    let anchor = "middle";
    if (lp.x < cx - 10) anchor = "end";
    else if (lp.x > cx + 10) anchor = "start";

    const statusCls = f.status === "fail" ? "fail"
      : f.status === "warning" ? "warning" : "pass";
    const shortLabel = escapeHTML(RADAR_SHORT_LABELS[f.filter_id] || f.filter_id);
    const pctLabel = Math.round(score * 100) + "%";

    labelsSVG += `<text x="${lp.x}" y="${lp.y}" text-anchor="${anchor}" dominant-baseline="central" class="okazcar-radar-axis-label ${statusCls}">`;
    labelsSVG += `<tspan>${shortLabel}</tspan>`;
    labelsSVG += `<tspan x="${lp.x}" dy="12" font-size="9" font-weight="700">${pctLabel}</tspan>`;
    labelsSVG += `</text>`;
  }

  return `
    <svg class="okazcar-radar-svg" width="320" height="310" viewBox="0 0 320 310">
      ${gridSVG}
      ${axesSVG}
      <polygon points="${dataStr}" fill="${mainColor}" opacity="0.15"/>
      <polygon points="${dataStr}" fill="none" stroke="${mainColor}" stroke-width="2" stroke-linejoin="round"/>
      ${dotsSVG}
      ${labelsSVG}
      <text x="${cx}" y="${cy - 6}" text-anchor="middle" class="okazcar-radar-score" fill="${mainColor}">${overallScore}</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="okazcar-radar-score-label">/100</text>
    </svg>
  `;
}

// Filtres affiches en mode booleen (OK/NOK) au lieu d'une barre de score
const BOOLEAN_FILTERS = ["L2", "L8"];

/**
 * Barre de score individuelle pour un filtre dans la liste.
 * Trois modes d'affichage selon le type et le statut :
 *  - N/A pour les filtres neutral
 *  - Badge OK/NOK pour les filtres booleens (L2, L8)
 *  - Barre de pourcentage pour tous les autres
 * @param {Object} f - Filtre {filter_id, status, score}
 * @returns {string} HTML de la barre de score
 */
export function buildScoreBar(f) {
  const color = statusColor(f.status);
  if (f.status === "neutral") {
    return '<span class="okazcar-filter-score okazcar-score-na">N/A</span>';
  }
  if (f.status === "skip") {
    return '<div class="okazcar-filter-score-bar"><div class="okazcar-score-track"><div class="okazcar-score-fill" style="width:0%;background:#d1d5db"></div></div><span class="okazcar-score-text" style="color:#9ca3af">skip</span></div>';
  }
  if (BOOLEAN_FILTERS.includes(f.filter_id)) {
    const badgeClass = f.status === "pass" ? "okazcar-bool-pass" : f.status === "fail" ? "okazcar-bool-fail" : "okazcar-bool-warn";
    const badgeText = f.status === "pass" ? "\u2713 OK" : f.status === "fail" ? "\u2717 NOK" : "\u26A0";
    return `<span class="okazcar-bool-badge ${badgeClass}">${badgeText}</span>`;
  }
  const pct = Math.round(f.score * 100);
  return `<div class="okazcar-filter-score-bar"><div class="okazcar-score-track"><div class="okazcar-score-fill" style="width:${pct}%;background:${color}"></div></div><span class="okazcar-score-text" style="color:${color}">${pct}%</span></div>`;
}
