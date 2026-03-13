/**
 * L6 — Analyse du numero de telephone du vendeur.
 * Classe le numero par type (mobile, fixe, virtuel, etranger, demarchage ARCEP)
 * et affiche un badge colore en consequence.
 */

"use strict";

import { escapeHTML } from '../../utils/format.js';

/**
 * Rendu du filtre L6 : badge du type de telephone + message contextuel.
 * Gere aussi le cas "connectez-vous pour voir le numero" sur LBC.
 * @param {Object} f - Filtre {status, message}
 * @param {Object} d - Details {type, is_foreign, prefix, no_phone_pro, phone_login_hint, ...}
 * @returns {string} HTML du body L6
 */
export function buildL6Body(f, d) {
  if (f.status === "neutral") {
    return `<div class="okazcar-l6-body"><span class="okazcar-l6-na">T\u00E9l\u00E9phone non disponible</span></div>`;
  }

  if (f.status === "skip" && d.phone_login_hint) {
    const hintText = typeof d.phone_login_hint === "string"
      ? d.phone_login_hint
      : "Connectez-vous sur LeBonCoin pour acc\u00E9der au num\u00E9ro";
    return `<div class="okazcar-l6-body">
      <div class="okazcar-phone-login-hint">
        <span class="okazcar-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="okazcar-phone-login-link">Se connecter</a>
      </div>
    </div>`;
  }

  // Classification du numero par type — chaque type a son badge et sa couleur
  const phoneType = d.type || "";
  let badgeText = "";
  let badgeClass = "okazcar-l6-badge-default";

  if (phoneType.startsWith("mobile")) {
    badgeText = "Mobile";
    badgeClass = "okazcar-l6-badge-mobile";
  } else if (phoneType.startsWith("landline")) {
    badgeText = "Fixe";
    badgeClass = "okazcar-l6-badge-landline";
  } else if (phoneType === "telemarketing_arcep") {
    badgeText = "D\u00E9marchage";
    badgeClass = "okazcar-l6-badge-danger";
  } else if (phoneType === "virtual_onoff") {
    badgeText = "Virtuel";
    badgeClass = "okazcar-l6-badge-danger";
  } else if (d.is_foreign) {
    const prefix = d.prefix || "";
    const flag = d.prefix_country_flag || "";
    const countryName = d.prefix_country_name || "";
    const suffix = [prefix, flag, countryName].filter(Boolean).join(" ");
    badgeText = `\u00C9tranger${suffix ? " (" + suffix + ")" : ""}`;
    badgeClass = "okazcar-l6-badge-foreign";
  } else if (phoneType.startsWith("local") || phoneType === "present_unverified") {
    badgeText = "Pr\u00E9sent";
    badgeClass = "okazcar-l6-badge-ok";
  }

  if (d.no_phone_pro) {
    badgeText = "Pro sans t\u00E9l\u00E9phone";
    badgeClass = "okazcar-l6-badge-danger";
  }

  let html = `<div class="okazcar-l6-body">`;
  if (badgeText) {
    html += `<span class="okazcar-l6-badge ${badgeClass}">${escapeHTML(badgeText)}</span>`;
  }
  if (f.message && f.status !== "pass") {
    html += `<span class="okazcar-l6-msg">${escapeHTML(f.message)}</span>`;
  }
  html += `</div>`;
  return html;
}
