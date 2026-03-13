/**
 * L2 — Verification du modele : est-ce que marque/modele/generation sont reconnus ?
 * Affichage booleen : badge vert si match, message d'erreur sinon.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Rendu du filtre L2 : badge de validation du modele.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {brand, model, generation}
 * @returns {string} HTML du body L2
 */
export function buildL2Body(f, d) {
  if (f.status === "skip") {
    return `<div class="okazcar-l2-body"><span class="okazcar-l2-na">${escapeHTML(f.message)}</span></div>`;
  }

  if (f.status === "pass") {
    const brand = d.brand || "";
    const model = d.model || "";
    const gen = d.generation ? ` \u00B7 ${d.generation}` : "";
    return `<div class="okazcar-l2-body">
      <span class="okazcar-l2-badge okazcar-l2-badge-ok">\u2713 ${escapeHTML(brand)} ${escapeHTML(model)}${escapeHTML(gen)}</span>
    </div>`;
  }

  return `<div class="okazcar-l2-body">
    <span class="okazcar-l2-msg">${escapeHTML(f.message)}</span>
  </div>`;
}
