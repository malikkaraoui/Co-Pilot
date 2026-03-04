"use strict";

import { escapeHTML } from '../../utils/format.js';

export function buildL3Body(f, d) {
  const kmYear = d.km_per_year;
  const expectedKm = d.expected_km;
  const mileage = d.mileage_km;
  const age = d.age;
  const isPro = d.is_pro;
  const warnings = d.warnings || [];
  const avgExpected = d.avg_km_per_year;
  const kmRatio = d.km_ratio;

  if (kmYear == null || expectedKm == null) {
    return `<p class="copilot-filter-message">${escapeHTML(f.message)}</p>`;
  }

  const fmtKm = (n) => Math.round(n).toLocaleString("fr-FR");

  const statHTML = `
    <div class="copilot-l3-stat">
      <span class="copilot-l3-km-year">~${fmtKm(kmYear)} km/an</span>
      <span class="copilot-l3-expected">Attendu : ~${fmtKm(avgExpected || 15000)} km/an pour un véhicule de ${age} an${age > 1 ? "s" : ""}</span>
    </div>
  `;

  const maxKm = Math.max(mileage, expectedKm) * 1.3;
  const realPct = Math.min((mileage / maxKm) * 100, 100);
  const expectedPct = Math.min((expectedKm / maxKm) * 100, 100);
  const barColor = kmRatio < 0.5 ? "#3b82f6" : kmRatio <= 1.5 ? "#22c55e" : kmRatio <= 2.0 ? "#f59e0b" : "#ef4444";

  const barHTML = `
    <div class="copilot-l3-comparison">
      <div class="copilot-l3-bar-row">
        <span class="copilot-l3-bar-label">Réel</span>
        <div class="copilot-l3-bar-track"><div class="copilot-l3-bar-fill" style="width:${realPct}%;background:${barColor}"></div></div>
        <span class="copilot-l3-bar-value">${fmtKm(mileage)} km</span>
      </div>
      <div class="copilot-l3-bar-row">
        <span class="copilot-l3-bar-label">Attendu</span>
        <div class="copilot-l3-bar-track"><div class="copilot-l3-bar-fill" style="width:${expectedPct}%;background:#9ca3af"></div></div>
        <span class="copilot-l3-bar-value">${fmtKm(expectedKm)} km</span>
      </div>
    </div>
  `;

  const isRecentLowKm = d.is_recent_low_km;
  let verdictHTML = "";
  if (f.status === "pass") {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-ok">Kilométrage cohérent avec l\'âge du véhicule</div>';
  } else if (isRecentLowKm && isPro) {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-warn">Véhicule quasi-neuf — probable immatriculation constructeur</div>';
  } else if (isRecentLowKm) {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-warn">Véhicule quasi-neuf — n\'a pas trouvé preneur</div>';
  } else if (kmRatio < 0.5) {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-alert">Kilométrage très bas — compteur remis à zéro ?</div>';
  } else if (kmRatio > 2.0) {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-alert">Kilométrage très élevé — usure accélérée</div>';
  } else {
    verdictHTML = '<div class="copilot-l3-verdict copilot-l3-warn">Kilométrage à surveiller</div>';
  }

  let proHTML = "";
  if (isPro) {
    proHTML = '<span class="copilot-l3-pro-badge">Véhicule pro</span>';
  }

  let warningsHTML = "";
  if (warnings.length > 0) {
    const items = warnings.map((w) => `<li>${escapeHTML(w)}</li>`).join("");
    warningsHTML = `<ul class="copilot-l3-warnings">${items}</ul>`;
  }

  return `<div class="copilot-l3-body">${statHTML}${barHTML}${verdictHTML}${proHTML}${warningsHTML}</div>`;
}
