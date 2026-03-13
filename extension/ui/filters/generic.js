/**
 * Rendu generique pour les filtres qui n'ont pas de template dedie.
 * Affiche le message + les details bruts en fallback.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';
import { buildDetailsHTML } from '../../utils/format.js';

/**
 * Body par defaut : message du filtre + dump des details si presents.
 * Utilise quand aucun renderer specifique (L1-L10) ne correspond.
 * @param {Object} f - Filtre {message, details}
 * @returns {string} HTML du body generique
 */
export function buildGenericBody(f) {
  const msgHTML = `<p class="okazcar-filter-message">${escapeHTML(f.message)}</p>`;
  const detailsHTML = f.details ? buildDetailsHTML(f.details) : "";
  return msgHTML + detailsHTML;
}
