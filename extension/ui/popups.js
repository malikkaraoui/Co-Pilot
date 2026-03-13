/**
 * Construction des popups HTML (resultats, erreur, non-vehicule, non-supporte).
 * Chaque fonction retourne un string HTML complet pret a etre injecte par dom.js.
 * Aucune logique DOM ici — juste du template building.
 */

"use strict";

import { escapeHTML } from '../utils/format.js';
import { scoreColor } from '../utils/styles.js';
import { buildRadarSVG } from './components.js';
import { buildFiltersList, SIMULATED_FILTERS } from './filters/index.js';
import { buildAutovizaBanner, buildYouTubeBanner, buildEmailBanner } from './banners.js';
import { buildTiresPanel } from './tires.js';

// Path SVG d'une etoile pour la note fiabilite moteur
const RELIABILITY_STAR_PATH = 'M12 1.6l3.22 6.53 7.2 1.05-5.21 5.08 1.23 7.17L12 18.14 5.56 21.43l1.23-7.17L1.58 9.18l7.2-1.05L12 1.6z';

/**
 * Genere des etoiles SVG a remplissage partiel (ex: 3.7 = 3 pleines + 1 a 70%).
 * Utilise clipPath pour le remplissage fractionnel — plus precis que des demi-etoiles.
 * @param {number} score - Note sur 5
 * @param {string} color - Couleur de remplissage
 * @returns {string} HTML des etoiles ou chaine vide
 */
function buildReliabilityStars(score, color) {
  const numericScore = Number(score);
  if (!Number.isFinite(numericScore)) {
    return "";
  }

  const normalizedScore = Math.max(0, Math.min(5, numericScore));
  const label = normalizedScore.toFixed(1).replace('.', ',');
  const emptyColor = '#cbd5e1';
  let starsMarkup = '';

  for (let index = 0; index < 5; index += 1) {
    const fillRatio = Math.max(0, Math.min(1, normalizedScore - index));
    const fillPercent = Math.round(fillRatio * 100);
    const fillType = fillPercent === 100 ? 'full' : fillPercent >= 50 ? 'half' : 'empty';
    const clipId = `okazcar-star-clip-${index}-${fillPercent}`;

    starsMarkup += `
      <svg
        data-star-fill="${fillType}"
        viewBox="0 0 24 24"
        width="16"
        height="16"
        aria-hidden="true"
        style="display:block;flex:none;"
      >
        <defs>
          <clipPath id="${clipId}">
            <rect x="0" y="0" width="${24 * fillRatio}" height="24"></rect>
          </clipPath>
        </defs>
        <path d="${RELIABILITY_STAR_PATH}" fill="${emptyColor}"></path>
        <path d="${RELIABILITY_STAR_PATH}" fill="${color}" clip-path="url(#${clipId})"></path>
      </svg>`;
  }

  return `
    <span
      aria-label="Note fiabilité ${label} sur 5"
      title="${label}/5"
      style="display:inline-flex;align-items:center;gap:2px;vertical-align:middle;"
    >${starsMarkup}
    </span>`;
}

/**
 * Panneau fiabilite moteur base sur les donnees de seed_engine_reliability.
 * Si le moteur n'est pas matche, on affiche un message "en cours d'evaluation".
 * @param {Object|null} engineReliability - Donnees fiabilite du backend
 * @returns {string} HTML du panneau ou chaine vide
 */
function buildEngineReliabilityPanel(engineReliability) {
  if (!engineReliability) return "";
  if (!engineReliability.matched) {
    return `
      <div style="margin:10px 0;padding:10px 12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
        <div style="font-weight:600;font-size:12px;color:#64748b;margin-bottom:4px;">&#x1F527; Fiabilit&eacute; moteur</div>
        <div style="font-size:12px;color:#94a3b8;font-style:italic;">Les experts &eacute;valuent actuellement la fiabilit&eacute; de ce moteur.</div>
      </div>`;
  }
  const relScore = engineReliability.score || 0;
  const starColor = relScore >= 4.5 ? "#16a34a" : relScore >= 4.0 ? "#65a30d" : relScore >= 3.0 ? "#d97706" : "#dc2626";
  const label = escapeHTML(engineReliability.engine_code || "");
  // Fallback sur le texte brut si les SVG ne sont pas disponibles
  const starsHTML = buildReliabilityStars(relScore, starColor)
    || `<span style="font-size:15px;font-weight:700;color:${starColor};">${escapeHTML(engineReliability.stars || "")}</span>`;
  const noteHTML = engineReliability.note
    ? `<div style="font-size:11px;color:#64748b;margin-top:4px;">${escapeHTML(engineReliability.note)}</div>`
    : "";
  return `
    <div style="margin:10px 0;padding:10px 12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;">
      <div style="font-weight:600;font-size:12px;color:#64748b;margin-bottom:6px;">&#x1F527; Fiabilit&eacute; moteur</div>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:12px;color:#334155;font-weight:500;">${label}</span>
        <span style="font-size:15px;font-weight:700;color:${starColor};">${starsHTML}</span>
      </div>
      ${noteHTML}
    </div>`;
}

/**
 * Construit la popup principale avec les resultats d'analyse.
 * C'est la popup "complete" : radar, filtres, bannieres, fiabilite moteur, etc.
 * @param {Object} data - Reponse du backend {score, filters, vehicle, ...}
 * @param {Object} options - Options supplementaires {autovizaUrl, bonusSignals}
 * @returns {string} HTML complet de la popup
 */
export function buildResultsPopup(data, options = {}) {
  const { score, is_partial, filters, vehicle, featured_video, tire_sizes, engine_reliability } = data;
  const { autovizaUrl, bonusSignals } = options;
  const color = scoreColor(score);

  const vehicleInfo = vehicle
    ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim()
    : "Véhicule";

  // Badge conversion devise pour les annonces hors zone euro (ex: CHF, GBP)
  let currencyBadge = "";
  if (vehicle && vehicle.price_original && vehicle.currency) {
    const fmtOrig = vehicle.price_original.toLocaleString("fr-FR");
    const fmtEur = vehicle.price.toLocaleString("fr-FR");
    currencyBadge = `<span class="okazcar-currency-badge">${escapeHTML(fmtOrig)} ${escapeHTML(vehicle.currency)} <span style="opacity:0.6">\u2248 ${escapeHTML(fmtEur)} \u20AC</span></span>`;
  }

  const partialBadge = is_partial ? `<span class="okazcar-badge-partial">Analyse partielle</span>` : "";

  // On pioche le nombre de jours en ligne depuis L9 pour l'afficher dans le header
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

  // Signaux bonus = donnees supplementaires collectees multi-region
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
        ${buildTiresPanel(tire_sizes)}
        ${buildEngineReliabilityPanel(engine_reliability)}
      </div>
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

/**
 * Popup d'erreur avec bouton "Reessayer".
 * @param {string} message - Message d'erreur a afficher
 * @returns {string} HTML de la popup erreur
 */
export function buildErrorPopup(message) {
  return `<div class="okazcar-popup okazcar-popup-error" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-error-body"><div class="okazcar-error-icon">&#x1F527;</div><p class="okazcar-error-message">${escapeHTML(message)}</p><button class="okazcar-btn okazcar-btn-retry" id="okazcar-retry">Réessayer</button></div></div>`;
}

/**
 * Popup "pas un vehicule" — quand l'annonce est un meuble, un telephone, etc.
 * @param {string} message - Message explicatif
 * @param {string} category - Categorie detectee par le scraper
 * @returns {string} HTML de la popup
 */
export function buildNotAVehiclePopup(message, category) {
  return `<div class="okazcar-popup" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-not-vehicle-body"><div class="okazcar-not-vehicle-icon">&#x1F6AB;</div><h3 class="okazcar-not-vehicle-title">${escapeHTML(message)}</h3><p class="okazcar-not-vehicle-category">Cat&eacute;gorie d&eacute;tect&eacute;e : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="okazcar-not-vehicle-hint">OKazCar analyse uniquement les annonces de v&eacute;hicules.</p></div></div>`;
}

/**
 * Popup "type non supporte" — pour les motos, bateaux, camping-cars, etc.
 * @param {string} message - Message explicatif
 * @param {string} category - Categorie detectee
 * @returns {string} HTML de la popup
 */
export function buildNotSupportedPopup(message, category) {
  return `<div class="okazcar-popup" id="okazcar-popup"><div class="okazcar-popup-header"><div class="okazcar-popup-title-row"><span class="okazcar-popup-title">OKazCar</span><button class="okazcar-popup-close" id="okazcar-close">&times;</button></div></div><div class="okazcar-not-vehicle-body"><div class="okazcar-not-vehicle-icon">&#x1F3CD;</div><h3 class="okazcar-not-vehicle-title">${escapeHTML(message)}</h3><p class="okazcar-not-vehicle-category">Cat&eacute;gorie : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="okazcar-not-vehicle-hint">On bosse dessus, promis. Restez branch&eacute; !</p></div></div>`;
}
