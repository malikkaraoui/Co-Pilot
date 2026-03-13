/**
 * L1 — Completude des donnees de l'annonce.
 * Affiche une barre de progression (X/10 champs renseignes) et liste
 * les champs manquants classes par criticite.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';
import { statusColor } from '../../utils/styles.js';

// Traduction des noms de champs techniques en labels lisibles
const FIELD_LABELS_FR = {
  price_eur: "Prix", make: "Marque", model: "Modèle",
  year_model: "Année", mileage_km: "Kilométrage",
  fuel: "Énergie", gearbox: "Boîte", phone: "Téléphone",
  color: "Couleur", location: "Localisation",
};

export { FIELD_LABELS_FR };

/**
 * Rendu du filtre L1 : barre de completude + champs manquants.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {fields_present, fields_total, missing_critical, missing_secondary}
 * @returns {string} HTML du body L1
 */
export function buildL1Body(f, d) {
  const present = d.fields_present || 0;
  const total = d.fields_total || 10;
  const pct = total > 0 ? Math.round((present / total) * 100) : 0;
  const color = statusColor(f.status);

  const barHTML = `
    <div class="okazcar-l1-bar">
      <div class="okazcar-l1-bar-track">
        <div class="okazcar-l1-bar-fill" style="width:${pct}%;background:${color}"></div>
      </div>
      <span class="okazcar-l1-bar-label">${present}/${total} champs renseignés</span>
    </div>
  `;

  let statusMsg = "";
  if (f.status === "pass") {
    statusMsg = '<div class="okazcar-l1-status okazcar-l1-ok">Données complètes — analyse fiable</div>';
  } else {
    statusMsg = '<div class="okazcar-l1-status okazcar-l1-warn">Données incomplètes — l\'analyse qui suit peut être moins fiable</div>';
  }

  let missingHTML = "";
  const criticals = d.missing_critical || [];
  const secondaries = d.missing_secondary || [];

  if (criticals.length > 0) {
    const items = criticals.map((f) => `<li class="okazcar-l1-missing-critical">${escapeHTML(FIELD_LABELS_FR[f] || f)}</li>`).join("");
    missingHTML += `<div class="okazcar-l1-missing"><span class="okazcar-l1-missing-title">Critiques :</span><ul>${items}</ul></div>`;
  }
  if (secondaries.length > 0) {
    const items = secondaries.map((f) => `<li class="okazcar-l1-missing-secondary">${escapeHTML(FIELD_LABELS_FR[f] || f)}</li>`).join("");
    missingHTML += `<div class="okazcar-l1-missing"><span class="okazcar-l1-missing-title">Secondaires :</span><ul>${items}</ul></div>`;
  }

  return `<div class="okazcar-l1-body">${barHTML}${statusMsg}${missingHTML}</div>`;
}
