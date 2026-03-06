/**
 * Text formatting and detail rendering utilities.
 *
 * Pure functions for escaping, formatting values,
 * and building the detail/debug HTML table.
 */

"use strict";

export function escapeHTML(str) {
  if (typeof str !== "string") return String(str ?? "");
  const el = document.createElement("span");
  el.textContent = str;
  return el.innerHTML;
}

export const DETAIL_LABELS = {
  fields_present: "Champs renseignés", fields_total: "Champs totaux",
  missing_critical: "Champs critiques manquants", missing_secondary: "Champs secondaires manquants",
  matched_model: "Modèle reconnu", confidence: "Confiance",
  km_per_year: "Km / an", expected_range: "Fourchette attendue",
  actual_km: "Kilométrage réel", expected_km: "Kilométrage attendu",
  price: "Prix annonce", argus_price: "Prix Argus",
  price_diff: "Écart de prix", price_diff_pct: "Écart (%)",
  mean_price: "Prix moyen", std_dev: "Écart-type", z_score: "Z-score",
  phone_valid: "Téléphone valide", phone: "Téléphone",
  siret: "SIRET", siret_valid: "SIRET valide", company_name: "Raison sociale",
  is_import: "Véhicule importé", import_indicators: "Indicateurs import",
  color: "Couleur", phone_login_hint: "Téléphone",
  days_online: "Première publication (jours)", republished: "Annonce republiée",
  stale_below_market: "Prix bas + annonce ancienne",
  delta_eur: "Écart (€)", delta_pct: "Écart (%)",
  price_annonce: "Prix annonce", price_reference: "Prix référence",
  sample_count: "Nb annonces comparées", source: "Source prix",
  price_argus_mid: "Argus (médian)", price_argus_low: "Argus (bas)", price_argus_high: "Argus (haut)",
  precision: "Précision",
  lookup_make: "Lookup marque", lookup_model: "Lookup modèle", lookup_year: "Lookup année",
  lookup_region_key: "Lookup région (clé)", lookup_fuel_input: "Lookup énergie (brute)",
  lookup_fuel_key: "Lookup énergie (clé)", lookup_min_samples: "Seuil min annonces",
};

export const PRECISION_LABELS = { 5: "Tres precis", 4: "Precis", 3: "Correct", 2: "Approximatif", 1: "Estimatif" };

export function formatPrecisionStars(n) {
  const filled = "\u2605".repeat(n);
  const empty = "\u2606".repeat(5 - n);
  const label = PRECISION_LABELS[n] || "";
  return `${filled}${empty} ${n}/5 – ${label}`;
}

export function formatDetailValue(value) {
  if (Array.isArray(value)) {
    if (value.length === 0) return "Aucun";
    return value.map((v) => escapeHTML(v)).join(", ");
  }
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if (typeof value === "number") {
    if (Number.isInteger(value)) return value.toLocaleString("fr-FR");
    return value.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value)
      .map(([k, v]) => `${escapeHTML(DETAIL_LABELS[k] || k)}: ${formatDetailValue(v)}`)
      .join(", ");
  }
  return escapeHTML(value);
}

export function buildDetailsHTML(details) {
  let phoneHintHTML = "";
  if (details.phone_login_hint) {
    const hintText = typeof details.phone_login_hint === "string"
      ? details.phone_login_hint
      : "Connectez-vous sur LeBonCoin pour acc\u00e9der au num\u00e9ro";
    phoneHintHTML = `
      <div class="okazcar-phone-login-hint">
        <span class="okazcar-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="okazcar-phone-login-link">Se connecter</a>
      </div>
    `;
  }

  const entries = Object.entries(details)
    .filter(([k, v]) => v !== null && v !== undefined && k !== "phone_login_hint")
    .map(([k, v]) => {
      const label = DETAIL_LABELS[k] || k;
      const val = k === "precision" && typeof v === "number"
        ? formatPrecisionStars(v)
        : formatDetailValue(v);
      return `<div class="okazcar-detail-row"><span class="okazcar-detail-key">${escapeHTML(label)}</span><span class="okazcar-detail-value">${val}</span></div>`;
    })
    .join("");

  if (!entries && !phoneHintHTML) return "";
  const detailsBlock = entries
    ? `<details class="okazcar-filter-details"><summary>Voir les détails</summary><div class="okazcar-details-content">${entries}</div></details>`
    : "";
  return phoneHintHTML + detailsBlock;
}
