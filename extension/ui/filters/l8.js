/**
 * L8 — Detection d'import (vehicule importe de l'etranger).
 * Analyse plusieurs signaux (plaque etrangere, description, prix anormal)
 * et les classe en forts/faibles pour determiner la probabilite d'import.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Rendu du filtre L8 : alerte import + liste des signaux detectes.
 * Affichage booleen : clean (aucun signal) ou alerte avec indices.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {signals, strong_count}
 * @returns {string} HTML du body L8
 */
export function buildL8Body(f, d) {
  const signals = d.signals || [];
  const strongCount = d.strong_count || 0;

  if (f.status === "pass" || signals.length === 0) {
    return `<div class="okazcar-l8-body">
      <div class="okazcar-l8-clean">
        <span class="okazcar-l8-clean-icon">\u2705</span>
        <span>Aucun signal d'import d\u00E9tect\u00E9</span>
      </div>
    </div>`;
  }

  let headerText = strongCount >= 2
    ? "Import probable"
    : strongCount === 1
      ? "Signal d'import d\u00E9tect\u00E9"
      : "Signal faible d'import";
  const headerClass = f.status === "fail" ? "okazcar-l8-alert-fail" : "okazcar-l8-alert-warn";

  let html = `<div class="okazcar-l8-body">`;
  html += `<div class="okazcar-l8-alert ${headerClass}">`;
  html += `<span class="okazcar-l8-alert-icon">${f.status === "fail" ? "\uD83D\uDEA8" : "\u26A0\uFE0F"}</span>`;
  html += `<span class="okazcar-l8-alert-text">${escapeHTML(headerText)} (${signals.length} indice${signals.length > 1 ? "s" : ""})</span>`;
  html += `</div>`;

  html += `<ul class="okazcar-l8-signals">`;
  for (const sig of signals) {
    html += `<li class="okazcar-l8-signal">${escapeHTML(sig)}</li>`;
  }
  html += `</ul></div>`;
  return html;
}
