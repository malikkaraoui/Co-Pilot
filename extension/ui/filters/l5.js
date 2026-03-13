/**
 * L5 — Indice de confiance statistique.
 * Detecte les anomalies de prix via z-scores (outliers, marges suspectes)
 * et affiche une echelle visuelle "Louche -> RAS -> Fiable".
 * Signale aussi les diesel en zone urbaine dense (risque FAP).
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/** @returns {string|null} 'autoscout24', 'leboncoin' ou null */
function _detectCurrentSite() {
  try {
    const host = String(window.location.hostname || '').toLowerCase();
    if (host.includes('autoscout24.')) return 'autoscout24';
    if (host.includes('leboncoin.')) return 'leboncoin';
  } catch { /* ignore */ }
  return null;
}

/**
 * Rendu du filtre L5 : echelle de confiance + verdict + alerte diesel urbain.
 * La position du curseur sur l'echelle depend du type d'anomalie detecte.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {z_scores, anomalies, ref_count, diesel_urban, source}
 * @returns {string} HTML du body L5
 */
export function buildL5Body(f, d) {
  if (f.status === "skip") {
    return `<div class="okazcar-l5-body"><span class="okazcar-l5-na">${escapeHTML(f.message)}</span></div>`;
  }

  const zPrice = d.z_scores?.price;
  const anomalies = d.anomalies || [];
  const refCount = d.ref_count || 0;
  const hasOutlier = anomalies.some(a => a.includes("outlier"));
  const hasMargin = anomalies.some(a => a.includes("marge"));
  const dieselOnly = anomalies.length > 0 && anomalies.every(a => a.includes("Diesel"));

  // Position du curseur sur l'echelle selon le type d'anomalie
  let cursorPct, zoneClass, verdictText;
  if (hasOutlier) {
    cursorPct = zPrice > 0 ? 8 : 12;
    zoneClass = "okazcar-l5-zone-red";
    verdictText = "Anomalie d\u00E9tect\u00E9e \u2014 prix tr\u00E8s \u00E9loign\u00E9 de la distribution";
  } else if (hasMargin) {
    cursorPct = zPrice > 0 ? 22 : 28;
    zoneClass = "okazcar-l5-zone-orange";
    verdictText = "Signal faible \u2014 prix en marge de la distribution";
  } else if (anomalies.length === 0 || dieselOnly) {
    const bonus = Math.min(refCount, 20) / 20 * 20;
    cursorPct = 60 + bonus;
    zoneClass = refCount >= 10 ? "okazcar-l5-zone-green" : "okazcar-l5-zone-neutral";
    verdictText = refCount >= 10
      ? `RAS \u2014 aucune anomalie (${refCount} v\u00E9hicules compar\u00E9s)`
      : `RAS \u2014 confiance mod\u00E9r\u00E9e (${refCount} r\u00E9f\u00E9rences)`;
  } else {
    cursorPct = 35;
    zoneClass = "okazcar-l5-zone-orange";
    verdictText = anomalies[0];
  }

  let html = `<div class="okazcar-l5-body">`;
  html += `<div class="okazcar-l5-scale">`;
  html += `  <div class="okazcar-l5-track">`;
  html += `    <div class="okazcar-l5-zone-left"></div>`;
  html += `    <div class="okazcar-l5-zone-center"></div>`;
  html += `    <div class="okazcar-l5-zone-right"></div>`;
  html += `    <div class="okazcar-l5-cursor ${zoneClass}" style="left:${cursorPct}%"></div>`;
  html += `  </div>`;
  html += `  <div class="okazcar-l5-labels">`;
  html += `    <span class="okazcar-l5-label-left">Louche</span>`;
  html += `    <span class="okazcar-l5-label-center">RAS</span>`;
  html += `    <span class="okazcar-l5-label-right">Fiable</span>`;
  html += `  </div>`;
  html += `</div>`;

  html += `<div class="okazcar-l5-verdict">${escapeHTML(verdictText)}</div>`;

  if (d.diesel_urban) {
    html += `<div class="okazcar-l5-diesel">`;
    html += `  <span class="okazcar-l5-diesel-icon">\u2699\uFE0F</span>`;
    html += `  <div>`;
    html += `    <div class="okazcar-l5-diesel-title">Diesel en zone urbaine dense</div>`;
    html += `    <div class="okazcar-l5-diesel-text">Risque FAP, injecteurs, vanne EGR \u2014 les r\u00E9g\u00E9n\u00E9rations ne se font pas en ville</div>`;
    html += `  </div>`;
    html += `</div>`;
  }

  const src = d.source || "";
  let srcLabel = "";
  if (src === "marche_leboncoin") srcLabel = "LBC";
  else if (src === "marche_autoscout24") srcLabel = "AS24";
  else if (src === "argus_seed") srcLabel = "Argus Seed";
  const currentSite = _detectCurrentSite();
  const marketSite = src === 'marche_leboncoin'
    ? 'leboncoin'
    : src === 'marche_autoscout24'
      ? 'autoscout24'
      : null;
  if (srcLabel && currentSite && marketSite && currentSite !== marketSite) {
    srcLabel += ' · marché externe';
  }
  if (srcLabel || refCount) {
    html += `<div class="okazcar-l5-footer">`;
    if (srcLabel) html += `<span class="okazcar-l5-src">${escapeHTML(srcLabel)}</span>`;
    if (refCount) html += `<span class="okazcar-l5-refs">Bas\u00E9 sur ${refCount} v\u00E9hicule${refCount > 1 ? "s" : ""}</span>`;
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}
