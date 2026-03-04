"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL10Body(f, d) {
  const days = d.days_online;
  const threshold = d.threshold_days || 35;
  const ratio = d.ratio || 0;
  const republished = d.republished;
  const thresholdSource = d.threshold_source === "marche" ? "marché" : "prix";
  const marketMedian = d.market_median_days;

  if (days == null) {
    return '<p class="copilot-filter-message">Ancienneté non disponible</p>';
  }

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

  const maxDisplay = threshold * 2.5;
  const cursorPct = Math.min(Math.max((days / maxDisplay) * 100, 2), 98);
  const thresholdPct = Math.min((threshold / maxDisplay) * 100, 95);

  const bigNumber = `<div class="copilot-l10-big"><span class="copilot-l10-days" style="color:${barColor}">${days}</span><span class="copilot-l10-days-label">jour${days > 1 ? "s" : ""} en ligne</span></div>`;

  const barHTML = `
    <div class="copilot-l10-timeline">
      <div class="copilot-l10-track">
        <div class="copilot-l10-fill" style="width:${cursorPct}%;background:${barColor}"></div>
        <div class="copilot-l10-threshold" style="left:${thresholdPct}%">
          <div class="copilot-l10-threshold-line"></div>
          <span class="copilot-l10-threshold-label">Seuil ${threshold}j</span>
        </div>
        <div class="copilot-l10-cursor" style="left:${cursorPct}%;background:${barColor}"></div>
      </div>
      <div class="copilot-l10-scale">
        <span>0j</span>
        <span>${Math.round(maxDisplay)}j</span>
      </div>
    </div>
  `;

  const verdictHTML = `<div class="copilot-l10-verdict" style="color:${barColor}">${escapeHTML(verdictText)}</div>`;

  let metaHTML = `<div class="copilot-l10-meta">Seuil basé sur le ${escapeHTML(thresholdSource)}</div>`;
  if (marketMedian != null) {
    metaHTML += `<div class="copilot-l10-meta">Médiane marché : ${marketMedian} jours</div>`;
  }

  let republishedHTML = "";
  if (republished) {
    republishedHTML = '<div class="copilot-l10-republished">Republication détectée — l\'annonce a été remise en ligne pour paraître récente</div>';
  }

  return `<div class="copilot-l10-body">${bigNumber}${barHTML}${verdictHTML}${metaHTML}${republishedHTML}</div>`;
}
