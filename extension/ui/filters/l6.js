"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL6Body(f, d) {
  if (f.status === "neutral") {
    return `<div class="copilot-l6-body"><span class="copilot-l6-na">T\u00E9l\u00E9phone non disponible</span></div>`;
  }

  if (f.status === "skip" && d.phone_login_hint) {
    const hintText = typeof d.phone_login_hint === "string"
      ? d.phone_login_hint
      : "Connectez-vous sur LeBonCoin pour acc\u00E9der au num\u00E9ro";
    return `<div class="copilot-l6-body">
      <div class="copilot-phone-login-hint">
        <span class="copilot-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="copilot-phone-login-link">Se connecter</a>
      </div>
    </div>`;
  }

  const phoneType = d.type || "";
  let badgeText = "";
  let badgeClass = "copilot-l6-badge-default";

  if (phoneType.startsWith("mobile")) {
    badgeText = "Mobile";
    badgeClass = "copilot-l6-badge-mobile";
  } else if (phoneType.startsWith("landline")) {
    badgeText = "Fixe";
    badgeClass = "copilot-l6-badge-landline";
  } else if (phoneType === "telemarketing_arcep") {
    badgeText = "D\u00E9marchage";
    badgeClass = "copilot-l6-badge-danger";
  } else if (phoneType === "virtual_onoff") {
    badgeText = "Virtuel";
    badgeClass = "copilot-l6-badge-danger";
  } else if (d.is_foreign) {
    const prefix = d.prefix || "";
    const flag = d.prefix_country_flag || "";
    const countryName = d.prefix_country_name || "";
    const suffix = [prefix, flag, countryName].filter(Boolean).join(" ");
    badgeText = `\u00C9tranger${suffix ? " (" + suffix + ")" : ""}`;
    badgeClass = "copilot-l6-badge-foreign";
  } else if (phoneType.startsWith("local") || phoneType === "present_unverified") {
    badgeText = "Pr\u00E9sent";
    badgeClass = "copilot-l6-badge-ok";
  }

  if (d.no_phone_pro) {
    badgeText = "Pro sans t\u00E9l\u00E9phone";
    badgeClass = "copilot-l6-badge-danger";
  }

  let html = `<div class="copilot-l6-body">`;
  if (badgeText) {
    html += `<span class="copilot-l6-badge ${badgeClass}">${escapeHTML(badgeText)}</span>`;
  }
  if (f.message && f.status !== "pass") {
    html += `<span class="copilot-l6-msg">${escapeHTML(f.message)}</span>`;
  }
  html += `</div>`;
  return html;
}
