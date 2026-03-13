/**
 * L9 — Synthese globale de l'analyse.
 * Resume les points forts et faibles de l'annonce,
 * affiche le taux de couverture (combien de filtres ont pu etre evalues),
 * et propose un lien de connexion LBC si le telephone est manquant.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Rendu du filtre L9 : couverture + points forts/faibles + hint connexion.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {points_forts, points_faibles, phone_login_hint}
 * @param {Array} allFilters - Tous les filtres (pour calculer la couverture)
 * @returns {string} HTML du body L9
 */
export function buildL9Body(f, d, allFilters) {
  const forts = d.points_forts || [];
  const faibles = d.points_faibles || [];

  // Couverture : combien de filtres (hors L9 lui-meme) ont ete evalues
  const others = (allFilters || []).filter((x) => x.filter_id !== "L9");
  const total = others.length;
  const evaluated = others.filter((x) => x.status !== "skip").length;

  let coverageHTML = "";
  if (total > 0) {
    const coverageColor = evaluated === total ? "#22c55e" : evaluated >= total * 0.7 ? "#f59e0b" : "#ef4444";
    const coverageText = evaluated === total
      ? "Analyse complète"
      : `Analyse partielle — ${total - evaluated} filtre${total - evaluated > 1 ? "s" : ""} non évalué${total - evaluated > 1 ? "s" : ""} (données absentes de l'annonce)`;
    coverageHTML = `
      <div class="okazcar-l9-coverage">
        <span class="okazcar-l9-coverage-count" style="color:${coverageColor}">${evaluated}/${total} filtres évalués</span>
        <span class="okazcar-l9-coverage-text">${escapeHTML(coverageText)}</span>
      </div>
    `;
  }

  let fortsHTML = "";
  if (forts.length > 0) {
    const items = forts.map((p) => `<li class="okazcar-l9-fort">${escapeHTML(p)}</li>`).join("");
    fortsHTML = `<div class="okazcar-l9-list"><div class="okazcar-l9-list-title okazcar-l9-fort-title">Points forts</div><ul>${items}</ul></div>`;
  }

  let faiblesHTML = "";
  if (faibles.length > 0) {
    const items = faibles.map((p) => `<li class="okazcar-l9-faible">${escapeHTML(p)}</li>`).join("");
    faiblesHTML = `<div class="okazcar-l9-list"><div class="okazcar-l9-list-title okazcar-l9-faible-title">Points faibles</div><ul>${items}</ul></div>`;
  }

  let phoneHintHTML = "";
  if (d.phone_login_hint) {
    const hintText = typeof d.phone_login_hint === "string"
      ? d.phone_login_hint
      : "Connectez-vous sur LeBonCoin pour accéder au numéro";
    phoneHintHTML = `
      <div class="okazcar-phone-login-hint">
        <span class="okazcar-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="okazcar-phone-login-link">Se connecter</a>
      </div>
    `;
  }

  return `<div class="okazcar-l9-body">${coverageHTML}${fortsHTML}${faiblesHTML}${phoneHintHTML}</div>`;
}
