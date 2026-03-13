/**
 * L10 — Anciennete de l'annonce en ligne.
 * Affiche une timeline avec le nombre de jours en ligne,
 * un seuil adaptatif (base sur le marche ou le prix),
 * et detecte les republications (remise en ligne pour paraitre recent).
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Rendu du filtre L10 : big number + timeline + verdict + detection republication.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {days_online, threshold_days, ratio, republished, market_median_days, ...}
 * @returns {string} HTML du body L10
 */
export function buildL10Body(f, d) {
  const days = d.days_online;
  const threshold = d.threshold_days || 35;
  const ratio = d.ratio || 0;
  const republished = d.republished;
  const thresholdSource = d.threshold_source === "marche" ? "marché" : "prix";
  const marketMedian = d.market_median_days;

  if (days == null) {
    return '<p class="okazcar-filter-message">Ancienneté non disponible</p>';
  }

  // Verdict selon le ratio jours_en_ligne / seuil : < 1 = normal, > 2 = stagnante
  let barColor, verdictText;
  if (ratio <= 0.3) {
    barColor = "#22c55e";
    verdictText = "Annonce très récente";
  } else if (ratio <= 1.0) {
    barColor = "#22c55e";
    verdictText = "Durée de mise en vente normale";
  } else if (ratio <= 2.0) {
    barColor = "#f59e0b";
    verdictText = "Au-delà de la durée normale pour ce segment";
  } else {
    barColor = "#ef4444";
    verdictText = "Annonce stagnante — pourquoi personne n'a acheté ?";
  }

  // Echelle de la timeline : 2.5x le seuil, curseur clamp entre 2% et 98%
  const maxDisplay = threshold * 2.5;
  const cursorPct = Math.min(Math.max((days / maxDisplay) * 100, 2), 98);
  const thresholdPct = Math.min((threshold / maxDisplay) * 100, 95);

  const bigNumber = `<div class="okazcar-l10-big"><span class="okazcar-l10-days" style="color:${barColor}">${days}</span><span class="okazcar-l10-days-label">jour${days > 1 ? "s" : ""} en ligne</span></div>`;

  const barHTML = `
    <div class="okazcar-l10-timeline">
      <div class="okazcar-l10-track">
        <div class="okazcar-l10-fill" style="width:${cursorPct}%;background:${barColor}"></div>
        <div class="okazcar-l10-threshold" style="left:${thresholdPct}%">
          <div class="okazcar-l10-threshold-line"></div>
          <span class="okazcar-l10-threshold-label">Seuil ${threshold}j</span>
        </div>
        <div class="okazcar-l10-cursor" style="left:${cursorPct}%;background:${barColor}"></div>
      </div>
      <div class="okazcar-l10-scale">
        <span>0j</span>
        <span>${Math.round(maxDisplay)}j</span>
      </div>
    </div>
  `;

  const verdictHTML = `<div class="okazcar-l10-verdict" style="color:${barColor}">${escapeHTML(verdictText)}</div>`;

  let metaHTML = `<div class="okazcar-l10-meta">Seuil basé sur le ${escapeHTML(thresholdSource)}</div>`;
  if (marketMedian != null) {
    metaHTML += `<div class="okazcar-l10-meta">Médiane marché : ${marketMedian} jours</div>`;
  }

  let republishedHTML = "";
  if (republished) {
    republishedHTML = '<div class="okazcar-l10-republished">Republication détectée — l\'annonce a été remise en ligne pour paraître récente</div>';
  }

  return `<div class="okazcar-l10-body">${bigNumber}${barHTML}${verdictHTML}${metaHTML}${republishedHTML}</div>`;
}
