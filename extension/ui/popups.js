"use strict";

import { escapeHTML } from '../utils/format.js';
import { scoreColor } from '../utils/styles.js';
import { buildRadarSVG } from './components.js';
import { buildFiltersList, SIMULATED_FILTERS } from './filters/index.js';
import { buildAutovizaBanner, buildYouTubeBanner, buildEmailBanner } from './banners.js';
import { buildTiresPanel } from './tires.js';

export function buildResultsPopup(data, options = {}) {
  const { score, is_partial, filters, vehicle, featured_video, tire_sizes } = data;
  const { autovizaUrl, bonusSignals } = options;
  const color = scoreColor(score);

  const vehicleInfo = vehicle
    ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim()
    : "Véhicule";

  let currencyBadge = "";
  if (vehicle && vehicle.price_original && vehicle.currency) {
    const fmtOrig = vehicle.price_original.toLocaleString("fr-FR");
    const fmtEur = vehicle.price.toLocaleString("fr-FR");
    currencyBadge = `<span class="okazcar-currency-badge">${escapeHTML(fmtOrig)} ${escapeHTML(vehicle.currency)} <span style="opacity:0.6">\u2248 ${escapeHTML(fmtEur)} \u20AC</span></span>`;
  }

  const partialBadge = is_partial ? `<span class="okazcar-badge-partial">Analyse partielle</span>` : "";

  const l9 = (filters || []).find((f) => f.filter_id === "L9");
  const daysOnline = l9?.details?.days_online;
  const isRepublished = l9?.details?.republished;
  let daysOnlineBadge = "";
  if (daysOnline != null) {
    const badgeColor = daysOnline <= 7 ? "#22c55e" : daysOnline <= 30 ? "#6b7280" : "#f59e0b";
    const label = isRepublished
      ? `&#x1F4C5; En vente depuis ${daysOnline}j (republié)`
      : `&#x1F4C5; ${daysOnline}j en ligne`;
    daysOnlineBadge = `<span class="okazcar-days-badge" style="color:${badgeColor}">${label}</span>`;
  }

  let bonusHTML = "";
  if (bonusSignals && bonusSignals.length > 0) {
    bonusHTML = '<div style="margin:12px 0;padding:10px;background:#f0f4ff;border-radius:8px;border:1px solid #d0d8f0;">';
    bonusHTML += '<div style="font-weight:600;font-size:13px;margin-bottom:8px;color:#334155;">Signaux exclusifs</div>';
    for (const signal of bonusSignals) {
      let sIcon, sColor;
      switch (signal.status) {
        case 'pass':    sIcon = '\u2713'; sColor = '#16a34a'; break;
        case 'warning': sIcon = '\u26A0'; sColor = '#f59e0b'; break;
        case 'fail':    sIcon = '\u2717'; sColor = '#ef4444'; break;
        default:        sIcon = '\u2139'; sColor = '#6366f1'; break;
      }
      bonusHTML += '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;font-size:12px;">';
      bonusHTML += '<span style="color:#64748b;">' + escapeHTML(signal.label) + '</span>';
      bonusHTML += '<span style="font-weight:600;color:' + sColor + ';">' + sIcon + ' ' + escapeHTML(signal.value) + '</span>';
      bonusHTML += '</div>';
    }
    bonusHTML += '</div>';
  }

  return `
    <div class="okazcar-popup" id="okazcar-popup">
      <div class="okazcar-popup-header">
        <div class="okazcar-popup-title-row">
          <span class="okazcar-popup-title">OKazCar</span>
          <button class="okazcar-popup-close" id="okazcar-close">&times;</button>
        </div>
        <p class="okazcar-popup-vehicle">${escapeHTML(vehicleInfo)} ${daysOnlineBadge}</p>
        ${currencyBadge ? `<p class="okazcar-popup-currency">${currencyBadge}</p>` : ""}
        ${partialBadge}
      </div>
      <div class="okazcar-radar-section">
        ${buildRadarSVG(filters, score)}
        <p class="okazcar-verdict" style="color:${color}">
          ${score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise"}
        </p>
      </div>
      <div class="okazcar-popup-filters">
        <h3 class="okazcar-section-title">Détails de l'analyse</h3>
        ${buildFiltersList(filters, vehicle)}
      </div>
      ${buildTiresPanel(tire_sizes)}
      ${bonusHTML}
      ${buildAutovizaBanner(autovizaUrl)}
      ${buildYouTubeBanner(featured_video)}
      <div class="okazcar-carvertical-banner">
        <a href="https://www.carvertical.com/fr" target="_blank" rel="noopener noreferrer"
           class="okazcar-carvertical-link" id="okazcar-carvertical-btn">
          <img class="okazcar-carvertical-logo" src="${typeof chrome !== 'undefined' && chrome.runtime ? chrome.runtime.getURL('carvertical_logo.png') : 'carvertical_logo.png'}" alt="carVertical"/>
          <span class="okazcar-carvertical-text">
            <strong>Historique du véhicule</strong>
            <small>Vérifier sur carVertical</small>
          </span>
          <span class="okazcar-carvertical-arrow">&rsaquo;</span>
        </a>
      </div>
      ${buildEmailBanner()}
      <div class="okazcar-popup-footer"><p>OKazCar v1.0 &middot; Analyse automatisée</p></div>
    </div>
  `;
}

export function buildErrorPopup(message) {
  return `<div class="okazcar-popup okazcar-popup-error" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-error-body"><div class="okazcar-error-icon">&#x1F527;</div><p class="okazcar-error-message">${escapeHTML(message)}</p><button class="okazcar-btn okazcar-btn-retry" id="okazcar-retry">Réessayer</button></div></div>`;
}

export function buildNotAVehiclePopup(message, category) {
  return `<div class="okazcar-popup" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-not-vehicle-body"><div class="okazcar-not-vehicle-icon">&#x1F6AB;</div><h3 class="okazcar-not-vehicle-title">${escapeHTML(message)}</h3><p class="okazcar-not-vehicle-category">Cat&eacute;gorie d&eacute;tect&eacute;e : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="okazcar-not-vehicle-hint">OKazCar analyse uniquement les annonces de v&eacute;hicules.</p></div></div>`;
}

export function buildNotSupportedPopup(message, category) {
  return `<div class="okazcar-popup" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-not-vehicle-body"><div class="okazcar-not-vehicle-icon">&#x1F3CD;</div><h3 class="okazcar-not-vehicle-title">${escapeHTML(message)}</h3><p class="okazcar-not-vehicle-category">Cat&eacute;gorie : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="okazcar-not-vehicle-hint">On bosse dessus, promis. Restez branch&eacute; !</p></div></div>`;
}
