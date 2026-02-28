/**
 * Co-Pilot Content Script
 *
 * Injecte on-demand (via le popup de l'extension) et affiche
 * les résultats d'analyse dans une popup contextuelle.
 * Aucune action automatique -- zero bruit sur la page.
 */

"use strict";

// ── Imports (resolved by esbuild bundling) ────────────────────────
import { getExtractor } from './extractors/index.js';
import {
  initLbcDeps,
  extractVehicleFromNextData, extractRegionFromNextData, extractLocationFromNextData,
  buildLocationParam, DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices, fetchSearchPricesViaApi, fetchSearchPricesViaHtml,
  buildApiFilters, parseRange, filterAndMapSearchAds, extractMileageFromNextData,
  isUserLoggedIn, revealPhoneNumber, isStaleData, isAdPageLBC,
  maybeCollectMarketPrices, LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  getMileageRange, getHorsePowerRange, COLLECT_COOLDOWN_MS,
  toLbcBrandToken, LBC_BRAND_ALIASES, getAdDetails, executeBonusJobs, reportJobDone,
  GENERIC_MODELS, EXCLUDED_CATEGORIES,
} from './extractors/leboncoin.js';

// ── Configuration ──────────────────────────────────────────────
const API_URL = typeof __API_URL__ !== 'undefined' ? __API_URL__ : "http://localhost:5001/api/analyze";
let lastScanId = null;
const ERROR_MESSAGES = [
  "Oh mince, on a crevé ! Réessayez dans un instant.",
  "Le moteur a calé... Notre serveur fait une pause, retentez !",
  "Panne sèche ! Impossible de joindre le serveur.",
  "Embrayage patiné... L'analyse n'a pas pu démarrer.",
  "Vidange en cours ! Le serveur revient dans un instant.",
];

function isChromeRuntimeAvailable() {
  try {
    return (
      typeof chrome !== "undefined"
      && !!chrome.runtime
      && typeof chrome.runtime.sendMessage === "function"
    );
  } catch {
    return false;
  }
}

function isLocalBackendUrl(url) {
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
}

function isBenignRuntimeTeardownError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return msg.includes("extension context invalidated")
    || msg.includes("runtime_unavailable_for_local_backend")
    || msg.includes("receiving end does not exist");
}

// ── Proxy backend (mixed-content fix) ─────────────────────────

async function backendFetch(url, options = {}) {
  const isLocalBackend = isLocalBackendUrl(url);

  if (!isChromeRuntimeAvailable()) {
    try {
      return await fetch(url, options);
    } catch (err) {
      if (isLocalBackend) {
        throw new Error("runtime_unavailable_for_local_backend");
      }
      throw err;
    }
  }

  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(
        {
          action: "backend_fetch",
          url,
          method: options.method || "GET",
          headers: options.headers || null,
          body: options.body || null,
        },
        (resp) => {
          let runtimeErrorMsg = null;
          try {
            runtimeErrorMsg = chrome.runtime?.lastError?.message || null;
          } catch (e) {
            runtimeErrorMsg = e?.message || "extension context invalidated";
          }

          if (runtimeErrorMsg || !resp || resp.error) {
            fetch(url, options)
              .then(resolve)
              .catch((fallbackErr) => {
                if (isLocalBackend) {
                  reject(new Error(runtimeErrorMsg || resp?.error || fallbackErr?.message || "runtime_unavailable_for_local_backend"));
                  return;
                }
                reject(fallbackErr);
              });
            return;
          }
          let parsed;
          try { parsed = JSON.parse(resp.body); } catch { parsed = null; }
          resolve({
            ok: resp.ok,
            status: resp.status,
            json: async () => {
              if (parsed !== null) return parsed;
              throw new SyntaxError("Invalid JSON");
            },
            text: async () => resp.body,
          });
        },
      );
    } catch (err) {
      if (isLocalBackend) {
        reject(err);
        return;
      }
      fetch(url, options).then(resolve).catch(reject);
    }
  });
}

// ── Utilitaires ────────────────────────────────────────────────

function escapeHTML(str) {
  if (typeof str !== "string") return String(str ?? "");
  const el = document.createElement("span");
  el.textContent = str;
  return el.innerHTML;
}

function getRandomErrorMessage() {
  return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function scoreColor(score) {
  if (score >= 70) return "#22c55e";
  if (score >= 40) return "#f59e0b";
  return "#ef4444";
}

function statusColor(status) {
  switch (status) {
    case "pass": return "#22c55e";
    case "warning": return "#f59e0b";
    case "fail": return "#ef4444";
    case "skip": return "#9ca3af";
    default: return "#6b7280";
  }
}

function statusIcon(status) {
  switch (status) {
    case "pass": return "\u2713";
    case "warning": return "\u26A0";
    case "fail": return "\u2717";
    case "skip": return "\u2014";
    default: return "?";
  }
}

function filterLabel(filterId) {
  const labels = {
    L1: "Complétude des données",
    L2: "Modèle reconnu",
    L3: "Cohérence km / année",
    L4: "Prix vs Argus",
    L5: "Analyse statistique",
    L6: "Téléphone",
    L7: "SIRET vendeur",
    L8: "Détection import",
    L9: "Évaluation globale",
    L10: "Ancienneté annonce",
  };
  return labels[filterId] || filterId;
}

// ── Jauge circulaire SVG ───────────────────────────────────────

function buildGaugeSVG(score) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;
  const color = scoreColor(score);

  return `
    <svg class="copilot-gauge" viewBox="0 0 120 120" width="140" height="140">
      <circle cx="60" cy="60" r="${radius}" fill="none" stroke="#e5e7eb" stroke-width="10"/>
      <circle cx="60" cy="60" r="${radius}" fill="none" stroke="${color}" stroke-width="10"
        stroke-dasharray="${progress} ${circumference}"
        stroke-linecap="round"
        transform="rotate(-90 60 60)"
        class="copilot-gauge-progress"/>
      <text x="60" y="55" text-anchor="middle" class="copilot-gauge-score" fill="${color}">${score}</text>
      <text x="60" y="72" text-anchor="middle" class="copilot-gauge-label">/ 100</text>
    </svg>
  `;
}

// ── Radar chart SVG ───────────────────────────────────────────

const RADAR_SHORT_LABELS = {
  L1: "Donn\u00E9es", L2: "Mod\u00E8le", L3: "Km", L4: "Prix",
  L5: "Stats", L6: "T\u00E9l\u00E9phone", L7: "SIRET", L8: "Import",
  L9: "\u00C9val", L10: "Anciennet\u00E9",
};

function buildRadarSVG(filters, overallScore) {
  if (!filters || !filters.length) return "";

  const cx = 160, cy = 145, R = 100;
  const n = filters.length;
  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2;

  const mainColor = overallScore >= 70 ? "#22c55e"
    : overallScore >= 45 ? "#f59e0b" : "#ef4444";

  function pt(i, r) {
    const angle = startAngle + i * angleStep;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  }

  let gridSVG = "";
  for (const pct of [0.2, 0.4, 0.6, 0.8, 1.0]) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const p = pt(i, R * pct);
      pts.push(`${p.x},${p.y}`);
    }
    const cls = pct === 1.0 ? "copilot-radar-grid-outer" : "copilot-radar-grid";
    gridSVG += `<polygon points="${pts.join(" ")}" class="${cls}"/>`;
  }

  let axesSVG = "";
  for (let i = 0; i < n; i++) {
    const p = pt(i, R);
    axesSVG += `<line x1="${cx}" y1="${cy}" x2="${p.x}" y2="${p.y}" class="copilot-radar-axis-line"/>`;
  }

  const dataPts = [];
  for (let i = 0; i < n; i++) {
    const p = pt(i, R * filters[i].score);
    dataPts.push(`${p.x},${p.y}`);
  }
  const dataStr = dataPts.join(" ");

  let dotsSVG = "";
  let labelsSVG = "";
  const labelPad = 18;
  for (let i = 0; i < n; i++) {
    const f = filters[i];
    const score = f.score;
    const dp = pt(i, R * score);

    let dotColor = "#22c55e";
    if (f.status === "fail") dotColor = "#ef4444";
    else if (f.status === "warning") dotColor = "#f59e0b";
    else if (f.status === "skip") dotColor = "#9ca3af";
    dotsSVG += `<circle cx="${dp.x}" cy="${dp.y}" r="4" fill="${dotColor}" class="copilot-radar-dot"/>`;

    const lp = pt(i, R + labelPad);
    let anchor = "middle";
    if (lp.x < cx - 10) anchor = "end";
    else if (lp.x > cx + 10) anchor = "start";

    const statusCls = f.status === "fail" ? "fail"
      : f.status === "warning" ? "warning" : "pass";
    const shortLabel = escapeHTML(RADAR_SHORT_LABELS[f.filter_id] || f.filter_id);
    const pctLabel = Math.round(score * 100) + "%";

    labelsSVG += `<text x="${lp.x}" y="${lp.y}" text-anchor="${anchor}" dominant-baseline="central" class="copilot-radar-axis-label ${statusCls}">`;
    labelsSVG += `<tspan>${shortLabel}</tspan>`;
    labelsSVG += `<tspan x="${lp.x}" dy="12" font-size="9" font-weight="700">${pctLabel}</tspan>`;
    labelsSVG += `</text>`;
  }

  return `
    <svg class="copilot-radar-svg" width="320" height="310" viewBox="0 0 320 310">
      ${gridSVG}
      ${axesSVG}
      <polygon points="${dataStr}" fill="${mainColor}" opacity="0.15"/>
      <polygon points="${dataStr}" fill="none" stroke="${mainColor}" stroke-width="2" stroke-linejoin="round"/>
      ${dotsSVG}
      ${labelsSVG}
      <text x="${cx}" y="${cy - 6}" text-anchor="middle" class="copilot-radar-score" fill="${mainColor}">${overallScore}</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="copilot-radar-score-label">/100</text>
    </svg>
  `;
}

// ── Construction de la popup ───────────────────────────────────

const SIMULATED_FILTERS = ["L4", "L5"];

function buildFiltersList(filters) {
  if (!filters || !filters.length) return "";
  return filters
    .map((f) => {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id);
      const isL4 = f.filter_id === "L4";
      const priceBarHTML = isL4 && f.details ? buildPriceBarHTML(f.details) : "";
      const detailsHTML = isL4 ? "" : (f.details ? buildDetailsHTML(f.details) : "");
      const simulatedBadge = !isL4 && SIMULATED_FILTERS.includes(f.filter_id)
        ? '<span class="copilot-badge-simulated">Données simulées</span>'
        : "";
      return `
        <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
          <div class="copilot-filter-header">
            <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
            <span class="copilot-filter-label">${escapeHTML(label)}${simulatedBadge}</span>
            <span class="copilot-filter-score" style="color:${color}">${Math.round(f.score * 100)}%</span>
          </div>
          ${priceBarHTML || `<p class="copilot-filter-message">${escapeHTML(f.message)}</p>`}
          ${detailsHTML}
        </div>
      `;
    })
    .join("");
}

const DETAIL_LABELS = {
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

const PRECISION_LABELS = { 5: "Tres precis", 4: "Precis", 3: "Correct", 2: "Approximatif", 1: "Estimatif" };

function formatPrecisionStars(n) {
  const filled = "\u2605".repeat(n);
  const empty = "\u2606".repeat(5 - n);
  const label = PRECISION_LABELS[n] || "";
  return `${filled}${empty} ${n}/5 – ${label}`;
}

function formatDetailValue(value) {
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

function buildPriceBarHTML(details) {
  const priceAnnonce = details.price_annonce;
  const priceRef = details.price_reference;
  if (!priceAnnonce || !priceRef) return "";

  const deltaEur = details.delta_eur || (priceAnnonce - priceRef);
  const deltaPct = details.delta_pct != null
    ? details.delta_pct
    : Math.round(((priceAnnonce - priceRef) / priceRef) * 100);
  const absDelta = Math.abs(deltaEur);
  const absPct = Math.abs(Math.round(deltaPct));

  let verdictClass, verdictEmoji, line1, line2;
  if (absPct <= 10) {
    verdictClass = deltaPct < 0 ? "verdict-below" : "verdict-fair";
    verdictEmoji = deltaPct < 0 ? "\uD83D\uDFE2" : "\u2705";
    line1 = deltaPct < 0
      ? `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\u00E9`
      : "Prix juste";
    line2 = deltaPct < 0
      ? `Bon prix \u2014 ${absPct}% moins cher que le march\u00E9`
      : `Dans la fourchette du march\u00E9 (${deltaPct > 0 ? "+" : ""}${Math.round(deltaPct)}%)`;
  } else if (absPct <= 25) {
    if (deltaPct < 0) {
      verdictClass = "verdict-below";
      verdictEmoji = "\uD83D\uDFE2";
      line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\u00E9`;
      line2 = `Bon prix \u2014 ${absPct}% moins cher que le march\u00E9`;
    } else {
      verdictClass = "verdict-above-warning";
      verdictEmoji = "\uD83D\uDFE0";
      line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC au-dessus du march\u00E9`;
      line2 = `Prix \u00E9lev\u00E9 \u2014 ${absPct}% plus cher que le march\u00E9`;
    }
  } else {
    if (deltaPct < 0) {
      verdictClass = "verdict-below";
      verdictEmoji = "\uD83D\uDFE2";
      line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC en dessous du march\u00E9`;
      line2 = `Tr\u00E8s bon prix \u2014 ${absPct}% moins cher que le march\u00E9`;
    } else {
      verdictClass = "verdict-above-fail";
      verdictEmoji = "\uD83D\uDD34";
      line1 = `${absDelta.toLocaleString("fr-FR")} \u20AC au-dessus du march\u00E9`;
      line2 = `Trop cher \u2014 ${absPct}% plus cher que le march\u00E9`;
    }
  }

  const statusColors = { "verdict-below": "#16a34a", "verdict-fair": "#16a34a", "verdict-above-warning": "#ea580c", "verdict-above-fail": "#dc2626" };
  const fillOpacities = { "verdict-below": "rgba(22,163,74,0.15)", "verdict-fair": "rgba(22,163,74,0.15)", "verdict-above-warning": "rgba(234,88,12,0.2)", "verdict-above-fail": "rgba(220,38,38,0.2)" };
  const color = statusColors[verdictClass] || "#16a34a";
  const fillBg = fillOpacities[verdictClass] || "rgba(22,163,74,0.15)";

  const minP = Math.min(priceAnnonce, priceRef);
  const maxP = Math.max(priceAnnonce, priceRef);
  const gap = (maxP - minP) || maxP * 0.1;
  const scaleMin = Math.max(0, minP - gap * 0.8);
  const scaleMax = maxP + gap * 0.8;
  const range = scaleMax - scaleMin;
  const pct = (p) => ((p - scaleMin) / range) * 100;

  const annoncePct = pct(priceAnnonce);
  const argusPct = pct(priceRef);
  const fillLeft = Math.min(annoncePct, argusPct);
  const fillWidth = Math.abs(annoncePct - argusPct);
  const fmtP = (n) => escapeHTML(n.toLocaleString("fr-FR")) + " \u20AC";

  return `
    <div class="copilot-price-bar-container">
      <div class="copilot-price-verdict ${escapeHTML(verdictClass)}">
        <span class="copilot-price-verdict-emoji">${verdictEmoji}</span>
        <div>
          <div class="copilot-price-verdict-text">${escapeHTML(line1)}</div>
          <div class="copilot-price-verdict-pct">${escapeHTML(line2)}</div>
        </div>
      </div>
      <div class="copilot-price-bar-track">
        <div class="copilot-price-bar-fill" style="left:${fillLeft}%;width:${fillWidth}%;background:${fillBg}"></div>
        <div class="copilot-price-arrow-zone" style="left:${fillLeft}%;width:${fillWidth}%;border-color:${color}"></div>
        <div class="copilot-price-market-ref" style="left:${argusPct}%">
          <div class="copilot-price-market-line"></div>
          <div class="copilot-price-market-label">March\u00E9</div>
          <div class="copilot-price-market-price">${fmtP(priceRef)}</div>
        </div>
        <div class="copilot-price-car" style="left:${annoncePct}%">
          <span class="copilot-price-car-emoji">\uD83D\uDE97</span>
          <div class="copilot-price-car-price" style="color:${color}">${fmtP(priceAnnonce)}</div>
        </div>
      </div>
      <div class="copilot-price-bar-spacer"></div>
    </div>
  `;
}

function buildDetailsHTML(details) {
  let phoneHintHTML = "";
  if (details.phone_login_hint) {
    const hintText = typeof details.phone_login_hint === "string"
      ? details.phone_login_hint
      : "Connectez-vous sur LeBonCoin pour acc\u00e9der au num\u00e9ro";
    phoneHintHTML = `
      <div class="copilot-phone-login-hint">
        <span class="copilot-phone-hint-icon">&#x1F4F1;</span>
        <span>${escapeHTML(hintText)}</span>
        <a href="https://auth.leboncoin.fr/login/" target="_blank" rel="noopener noreferrer"
           class="copilot-phone-login-link">Se connecter</a>
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
      return `<div class="copilot-detail-row"><span class="copilot-detail-key">${escapeHTML(label)}</span><span class="copilot-detail-value">${val}</span></div>`;
    })
    .join("");

  if (!entries && !phoneHintHTML) return "";
  const detailsBlock = entries
    ? `<details class="copilot-filter-details"><summary>Voir les détails</summary><div class="copilot-details-content">${entries}</div></details>`
    : "";
  return phoneHintHTML + detailsBlock;
}

function buildPremiumSection() {
  return `<div class="copilot-premium-section"><div class="copilot-premium-blur"><div class="copilot-premium-fake"><p><strong>Rapport détaillé du véhicule</strong></p><p>Fiche fiabilité complète avec problèmes connus, coûts d'entretien prévus, historique des rappels constructeur et comparaison avec les alternatives du segment.</p><p>Estimation de la valeur réelle basée sur 12 critères régionaux.</p><p>Recommandation d'achat personnalisée avec score de confiance.</p></div></div><div class="copilot-premium-overlay"><div class="copilot-premium-glass"><p class="copilot-premium-title">Analyse complète</p><p class="copilot-premium-subtitle">Débloquez le rapport détaillé avec fiabilité, coûts et recommandations.</p><button class="copilot-premium-cta" id="copilot-premium-btn">Débloquer – 9,90 €</div></div></div>`;
}

function buildYouTubeBanner(featuredVideo) {
  if (!featuredVideo || !featuredVideo.url) return "";
  const title = featuredVideo.title || "Découvrir ce modèle en vidéo";
  const channel = featuredVideo.channel || "";
  return `<div class="copilot-youtube-banner"><a href="${escapeHTML(featuredVideo.url)}" target="_blank" rel="noopener noreferrer" class="copilot-youtube-link"><span class="copilot-youtube-icon">&#x25B6;&#xFE0F;</span><span class="copilot-youtube-text"><strong>Découvrir ce modèle en vidéo</strong><small>${escapeHTML(channel)}${channel ? " · " : ""}${escapeHTML(title).substring(0, 50)}</small></span><span class="copilot-youtube-arrow">&rsaquo;</span></a></div>`;
}

function buildAutovizaBanner(autovizaUrl) {
  if (!autovizaUrl) return "";
  return `<div class="copilot-autoviza-banner"><a href="${escapeHTML(autovizaUrl)}" target="_blank" rel="noopener noreferrer" class="copilot-autoviza-link"><span class="copilot-autoviza-icon">&#x1F4CB;</span><span class="copilot-autoviza-text"><strong>Rapport d'historique gratuit</strong><small>Offert par LeBonCoin via Autoviza (valeur 25 €)</small></span><span class="copilot-autoviza-arrow">&rsaquo;</span></a></div>`;
}

function buildEmailBanner() {
  return `<div class="copilot-email-banner" id="copilot-email-section"><button class="copilot-email-btn" id="copilot-email-btn">&#x2709; Rédiger un email au vendeur</button><div class="copilot-email-result" id="copilot-email-result" style="display:none;"><textarea class="copilot-email-textarea" id="copilot-email-text" rows="8" readonly></textarea><div class="copilot-email-actions"><button class="copilot-email-copy" id="copilot-email-copy">&#x1F4CB; Copier</button><span class="copilot-email-copied" id="copilot-email-copied" style="display:none;">Copié !</span></div></div><div class="copilot-email-loading" id="copilot-email-loading" style="display:none;"><span class="copilot-mini-spinner"></span> Génération en cours...</div><div class="copilot-email-error" id="copilot-email-error" style="display:none;"></div></div>`;
}

function buildResultsPopup(data, options = {}) {
  const { score, is_partial, filters, vehicle, featured_video } = data;
  const { autovizaUrl, bonusSignals } = options;
  const color = scoreColor(score);

  const vehicleInfo = vehicle
    ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim()
    : "Véhicule";

  // Affichage du prix original quand une conversion de devise a eu lieu
  let currencyBadge = "";
  if (vehicle && vehicle.price_original && vehicle.currency) {
    const fmtOrig = vehicle.price_original.toLocaleString("fr-FR");
    const fmtEur = vehicle.price.toLocaleString("fr-FR");
    currencyBadge = `<span class="copilot-currency-badge">${escapeHTML(fmtOrig)} ${escapeHTML(vehicle.currency)} <span style="opacity:0.6">\u2248 ${escapeHTML(fmtEur)} \u20AC</span></span>`;
  }

  const partialBadge = is_partial ? `<span class="copilot-badge-partial">Analyse partielle</span>` : "";

  const l9 = (filters || []).find((f) => f.filter_id === "L9");
  const daysOnline = l9?.details?.days_online;
  const isRepublished = l9?.details?.republished;
  let daysOnlineBadge = "";
  if (daysOnline != null) {
    const badgeColor = daysOnline <= 7 ? "#22c55e" : daysOnline <= 30 ? "#6b7280" : "#f59e0b";
    const label = isRepublished
      ? `&#x1F4C5; En vente depuis ${daysOnline}j (republié)`
      : `&#x1F4C5; ${daysOnline}j en ligne`;
    daysOnlineBadge = `<span class="copilot-days-badge" style="color:${badgeColor}">${label}</span>`;
  }

  // Bonus signals section (AutoScout24 exclusive data)
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
    <div class="copilot-popup" id="copilot-popup">
      <div class="copilot-popup-header">
        <div class="copilot-popup-title-row">
          <span class="copilot-popup-title">Co-Pilot</span>
          <button class="copilot-popup-close" id="copilot-close">&times;</button>
        </div>
        <p class="copilot-popup-vehicle">${escapeHTML(vehicleInfo)} ${daysOnlineBadge}</p>
        ${currencyBadge ? `<p class="copilot-popup-currency">${currencyBadge}</p>` : ""}
        ${partialBadge}
      </div>
      <div class="copilot-radar-section">
        ${buildRadarSVG(filters, score)}
        <p class="copilot-verdict" style="color:${color}">
          ${score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise"}
        </p>
      </div>
      <div class="copilot-popup-filters">
        <h3 class="copilot-section-title">Détails de l'analyse</h3>
        ${buildFiltersList(filters)}
      </div>
      ${bonusHTML}
      ${buildPremiumSection()}
      ${buildAutovizaBanner(autovizaUrl)}
      ${buildYouTubeBanner(featured_video)}
      <div class="copilot-carvertical-banner">
        <a href="https://www.carvertical.com/fr" target="_blank" rel="noopener noreferrer"
           class="copilot-carvertical-link" id="copilot-carvertical-btn">
          <img class="copilot-carvertical-logo" src="${typeof chrome !== 'undefined' && chrome.runtime ? chrome.runtime.getURL('carvertical_logo.png') : 'carvertical_logo.png'}" alt="carVertical"/>
          <span class="copilot-carvertical-text">
            <strong>Historique du véhicule</strong>
            <small>Vérifier sur carVertical</small>
          </span>
          <span class="copilot-carvertical-arrow">&rsaquo;</span>
        </a>
      </div>
      ${buildEmailBanner()}
      <div class="copilot-popup-footer"><p>Co-Pilot v1.0 &middot; Analyse automatisée</p></div>
    </div>
  `;
}

function buildErrorPopup(message) {
  return `<div class="copilot-popup copilot-popup-error" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-error-body"><div class="copilot-error-icon">&#x1F527;</div><p class="copilot-error-message">${escapeHTML(message)}</p><button class="copilot-btn copilot-btn-retry" id="copilot-retry">Réessayer</button></div></div>`;
}

function buildNotAVehiclePopup(message, category) {
  return `<div class="copilot-popup" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-not-vehicle-body"><div class="copilot-not-vehicle-icon">&#x1F6AB;</div><h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3><p class="copilot-not-vehicle-category">Cat&eacute;gorie d&eacute;tect&eacute;e : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="copilot-not-vehicle-hint">Co-Pilot analyse uniquement les annonces de v&eacute;hicules.</p></div></div>`;
}

function buildNotSupportedPopup(message, category) {
  return `<div class="copilot-popup" id="copilot-popup"><div class="copilot-popup-header"><div class="copilot-popup-title-row"><span class="copilot-popup-title">Co-Pilot</span><button class="copilot-popup-close" id="copilot-close">&times;</button></div></div><div class="copilot-not-vehicle-body"><div class="copilot-not-vehicle-icon">&#x1F3CD;</div><h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3><p class="copilot-not-vehicle-category">Cat&eacute;gorie : <strong>${escapeHTML(category || "inconnue")}</strong></p><p class="copilot-not-vehicle-hint">On bosse dessus, promis. Restez branch&eacute; !</p></div></div>`;
}

// ── Logique principale ─────────────────────────────────────────

function removePopup() {
  const existing = document.getElementById("copilot-popup");
  if (existing) existing.remove();
  const overlay = document.getElementById("copilot-overlay");
  if (overlay) overlay.remove();
}

function showPopup(html) {
  removePopup();
  const overlay = document.createElement("div");
  overlay.id = "copilot-overlay";
  overlay.className = "copilot-overlay";
  overlay.addEventListener("click", (e) => { if (e.target === overlay) removePopup(); });
  const container = document.createElement("div");
  container.innerHTML = html;
  overlay.appendChild(container.firstElementChild);
  document.body.appendChild(overlay);

  const closeBtn = document.getElementById("copilot-close");
  if (closeBtn) closeBtn.addEventListener("click", removePopup);
  const retryBtn = document.getElementById("copilot-retry");
  if (retryBtn) retryBtn.addEventListener("click", () => { removePopup(); runAnalysis(); });
  const premiumBtn = document.getElementById("copilot-premium-btn");
  if (premiumBtn) {
    premiumBtn.addEventListener("click", () => { premiumBtn.textContent = "Bientôt disponible !"; premiumBtn.disabled = true; });
  }

  const emailBtn = document.getElementById("copilot-email-btn");
  if (emailBtn) {
    emailBtn.addEventListener("click", async () => {
      const loading = document.getElementById("copilot-email-loading");
      const result = document.getElementById("copilot-email-result");
      const errorDiv = document.getElementById("copilot-email-error");
      const textArea = document.getElementById("copilot-email-text");
      emailBtn.style.display = "none";
      loading.style.display = "flex";
      errorDiv.style.display = "none";
      try {
        const emailUrl = API_URL.replace("/analyze", "/email-draft");
        const resp = await backendFetch(emailUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: lastScanId }) });
        const data = await resp.json();
        if (data.success) { textArea.value = data.data.generated_text; result.style.display = "block"; }
        else { errorDiv.textContent = data.error || "Erreur de génération"; errorDiv.style.display = "block"; emailBtn.style.display = "block"; }
      } catch (err) { errorDiv.textContent = "Service indisponible"; errorDiv.style.display = "block"; emailBtn.style.display = "block"; }
      loading.style.display = "none";
    });
  }

  const copyBtn = document.getElementById("copilot-email-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const textArea = document.getElementById("copilot-email-text");
      navigator.clipboard.writeText(textArea.value).then(() => {
        const copied = document.getElementById("copilot-email-copied");
        copied.style.display = "inline";
        setTimeout(() => { copied.style.display = "none"; }, 2000);
      });
    });
  }
}

function showLoading() {
  removePopup();
  showPopup(`<div class="copilot-popup copilot-popup-loading" id="copilot-popup"><div class="copilot-loading-body"><div class="copilot-spinner"></div><p>Analyse en cours...</p></div></div>`);
}

// ── Progress Tracker ──────────────────────────────────────────

function createProgressTracker() {
  function stepIconHTML(status) {
    switch (status) {
      case "running": return '<div class="copilot-mini-spinner"></div>';
      case "done":    return "\u2713";
      case "warning": return "\u26A0";
      case "error":   return "\u2717";
      case "skip":    return "\u2014";
      default:        return "\u25CB";
    }
  }

  function update(stepId, status, detail) {
    const el = document.getElementById("copilot-step-" + stepId);
    if (!el) return;
    el.setAttribute("data-status", status);
    const iconEl = el.querySelector(".copilot-step-icon");
    if (iconEl) {
      iconEl.className = "copilot-step-icon " + status;
      if (status === "running") { iconEl.innerHTML = '<div class="copilot-mini-spinner"></div>'; }
      else { iconEl.textContent = stepIconHTML(status); }
    }
    if (detail !== undefined) {
      let detailEl = el.querySelector(".copilot-step-detail");
      if (!detailEl) { detailEl = document.createElement("div"); detailEl.className = "copilot-step-detail"; el.querySelector(".copilot-step-text").appendChild(detailEl); }
      detailEl.textContent = detail;
    }
    el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function addSubStep(parentId, text, status, detail) {
    const parentEl = document.getElementById("copilot-step-" + parentId);
    if (!parentEl) return;
    let container = parentEl.querySelector(".copilot-substeps");
    if (!container) { container = document.createElement("div"); container.className = "copilot-substeps"; parentEl.appendChild(container); }
    const subEl = document.createElement("div");
    subEl.className = "copilot-substep";
    const iconSpan = document.createElement("span");
    iconSpan.className = "copilot-substep-icon";
    iconSpan.textContent = stepIconHTML(status);
    subEl.appendChild(iconSpan);
    const textSpan = document.createElement("span");
    let fullText = text;
    if (detail) fullText += " \u2014 " + detail;
    textSpan.textContent = fullText;
    subEl.appendChild(textSpan);
    container.appendChild(subEl);
    subEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showFilters(filters) {
    const container = document.getElementById("copilot-progress-filters");
    if (!container || !filters) return;
    filters.forEach(function (f) {
      const color = statusColor(f.status);
      const icon = statusIcon(f.status);
      const label = filterLabel(f.filter_id);
      const scoreText = f.status === "skip" ? "skip" : Math.round(f.score * 100) + "%";
      const filterDiv = document.createElement("div"); filterDiv.className = "copilot-progress-filter";
      const iconSpan = document.createElement("span"); iconSpan.className = "copilot-progress-filter-icon"; iconSpan.style.color = color; iconSpan.textContent = icon; filterDiv.appendChild(iconSpan);
      const idSpan = document.createElement("span"); idSpan.className = "copilot-progress-filter-id"; idSpan.textContent = f.filter_id; filterDiv.appendChild(idSpan);
      const labelSpan = document.createElement("span"); labelSpan.className = "copilot-progress-filter-label"; labelSpan.textContent = label; filterDiv.appendChild(labelSpan);
      const scoreSpan = document.createElement("span"); scoreSpan.className = "copilot-progress-filter-score"; scoreSpan.style.color = color; scoreSpan.textContent = scoreText; filterDiv.appendChild(scoreSpan);
      container.appendChild(filterDiv);
      const msgDiv = document.createElement("div"); msgDiv.className = "copilot-progress-filter-msg"; msgDiv.textContent = f.message; container.appendChild(msgDiv);
      if (f.filter_id === "L4" && f.details) { appendCascadeDetails(container, f.details); }
    });
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function appendCascadeDetails(container, details) {
    var lines = [];
    if (details.source === "marche_leboncoin") { lines.push("Source : march\u00e9 LBC (" + (details.sample_count || "?") + " annonces" + (details.precision ? ", pr\u00e9cision " + details.precision : "") + ")"); }
    else if (details.source === "argus_seed") { lines.push("Source : Argus (donn\u00e9es seed)"); }
    if (details.cascade_tried) {
      details.cascade_tried.forEach(function (tier) {
        var result = details["cascade_" + tier + "_result"] || "non essay\u00e9";
        var tierLabel = tier === "market_price" ? "March\u00e9 LBC" : "Argus Seed";
        var tierIcon = result === "found" ? "\u2713" : result === "insufficient" ? "\u26A0" : "\u2014";
        lines.push(tierIcon + " " + tierLabel + " : " + result);
      });
    }
    lines.forEach(function (line) { var div = document.createElement("div"); div.className = "copilot-cascade-detail"; div.textContent = line; container.appendChild(div); });
  }

  function showScore(score, verdict) {
    const container = document.getElementById("copilot-progress-score");
    if (!container) return;
    const color = scoreColor(score);
    const labelDiv = document.createElement("div"); labelDiv.className = "copilot-progress-score-label"; labelDiv.textContent = "Score global"; container.appendChild(labelDiv);
    const valueDiv = document.createElement("div"); valueDiv.className = "copilot-progress-score-value"; valueDiv.style.color = color; valueDiv.textContent = String(score); container.appendChild(valueDiv);
    const verdictDiv = document.createElement("div"); verdictDiv.className = "copilot-progress-score-verdict"; verdictDiv.style.color = color; verdictDiv.textContent = verdict; container.appendChild(verdictDiv);
    container.style.display = "block";
    container.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  return { update, addSubStep, showFilters, showScore };
}

function showProgress() {
  removePopup();
  const html = [
    '<div class="copilot-popup" id="copilot-popup">',
    '  <div class="copilot-popup-header">',
    '    <div class="copilot-popup-title-row">',
    '      <span class="copilot-popup-title">Co-Pilot</span>',
    '      <button class="copilot-popup-close" id="copilot-close">&times;</button>',
    '    </div>',
    '    <p class="copilot-popup-vehicle" id="copilot-progress-vehicle">Analyse en cours...</p>',
    '  </div>',
    '  <div class="copilot-progress-body">',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">1. Extraction</div>',
    '      <div class="copilot-step" id="copilot-step-extract" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Extraction des donn\u00e9es de l\'annonce</div></div>',
    '      <div class="copilot-step" id="copilot-step-phone" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">R\u00e9v\u00e9lation du num\u00e9ro de t\u00e9l\u00e9phone</div></div>',
    '    </div>',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">2. Collecte prix march\u00e9</div>',
    '      <div class="copilot-step" id="copilot-step-job" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Demande au serveur : quel v\u00e9hicule collecter ?</div></div>',
    '      <div class="copilot-step" id="copilot-step-collect" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte des prix (cascade LeBonCoin)</div></div>',
    '      <div class="copilot-step" id="copilot-step-submit" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Envoi des prix au serveur</div></div>',
    '      <div class="copilot-step" id="copilot-step-bonus" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Collecte bonus multi-r\u00e9gion</div></div>',
    '    </div>',
    '    <div class="copilot-progress-phase">',
    '      <div class="copilot-progress-phase-title">3. Analyse serveur</div>',
    '      <div class="copilot-step" id="copilot-step-analyze" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">Analyse des 10 filtres (L1 \u2013 L10)</div></div>',
    '      <div id="copilot-progress-filters" class="copilot-progress-filters"></div>',
    '      <div class="copilot-step" id="copilot-step-autoviza" data-status="pending"><span class="copilot-step-icon pending">\u25CB</span><div class="copilot-step-text">D\u00e9tection rapport Autoviza</div></div>',
    '    </div>',
    '    <hr class="copilot-progress-separator">',
    '    <div id="copilot-progress-score" class="copilot-progress-score" style="display:none"></div>',
    '    <div style="text-align:center; padding: 12px 0;">',
    '      <button class="copilot-btn copilot-btn-retry" id="copilot-progress-details-btn" style="display:none">Voir l\'analyse compl\u00e8te</button>',
    '    </div>',
    '  </div>',
    '  <div class="copilot-popup-footer"><p>Co-Pilot v1.0 &middot; Analyse en temps r\u00e9el</p></div>',
    '</div>',
  ].join("\n");
  showPopup(html);
  return createProgressTracker();
}

// ── Generic runAnalysis ──────────────────────────────────────

async function runAnalysis(injectedExtractor) {
  const extractor = injectedExtractor || getExtractor(window.location.href);
  if (!extractor) { showPopup(buildErrorPopup("Site non supporté.")); return; }

  const progress = showProgress();

  // Phase 1: Extraction
  progress.update("extract", "running");
  const payload = await extractor.extract();
  if (!payload) {
    console.warn("[CoPilot] extract() → null");
    progress.update("extract", "error", "Impossible de lire les données");
    showPopup(buildErrorPopup("Impossible de lire les données de cette page."));
    return;
  }
  const adId = payload.next_data?.props?.pageProps?.ad?.list_id || "";
  progress.update("extract", "done", adId ? "ID annonce : " + adId : "Données extraites");

  // Vehicle summary
  const summary = extractor.getVehicleSummary();
  const vehicleLabel = document.getElementById("copilot-progress-vehicle");
  if (vehicleLabel && summary?.make) {
    vehicleLabel.textContent = [summary.make, summary.model, summary.year].filter(Boolean).join(" ");
  }

  // Phone
  if (extractor.hasPhone()) {
    if (extractor.isLoggedIn()) {
      progress.update("phone", "running");
      const phone = await extractor.revealPhone();
      if (phone) { progress.update("phone", "done", phone.replace(/(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/, "$1 $2 $3 $4 $5")); }
      else { progress.update("phone", "warning", "Numéro non récupéré"); }
    } else { progress.update("phone", "skip", "Non connecté"); }
  } else { progress.update("phone", "skip", "Pas de téléphone"); }

  // Phase 2: Market prices
  let collectInfo = { submitted: false };
  try {
    collectInfo = await extractor.collectMarketPrices(progress);
  } catch (err) {
    console.error("[CoPilot] collectMarketPrices erreur:", err);
    progress.update("job", "error", "Erreur collecte");
  }
  if (!collectInfo.submitted) {
    // Si la collecte n'a rien soumis (site sans collecte ou erreur), skip les etapes UI
    const jobEl = document.getElementById("copilot-step-job");
    if (jobEl && jobEl.getAttribute("data-status") === "pending") {
      progress.update("job", "skip", "Collecte non disponible");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
  }

  // Phase 3: Backend analysis
  progress.update("analyze", "running");
  const apiBody = payload.type === 'raw'
    ? { url: window.location.href, next_data: payload.next_data }
    : { url: window.location.href, ad_data: payload.ad_data, source: payload.source };

  async function fetchAnalysisOnce() {
    const response = await backendFetch(API_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(apiBody) });
    if (!response.ok) {
      const errorData = await response.json().catch(() => null);
      if (errorData?.error === "NOT_A_VEHICLE") { progress.update("analyze", "skip", "Pas une voiture"); showPopup(buildNotAVehiclePopup(errorData.message, errorData.data?.category)); return null; }
      if (errorData?.error === "NOT_SUPPORTED") { progress.update("analyze", "skip", errorData.message); showPopup(buildNotSupportedPopup(errorData.message, errorData.data?.category)); return null; }
      const msg = errorData?.message || getRandomErrorMessage();
      progress.update("analyze", "error", msg); showPopup(buildErrorPopup(msg)); return null;
    }
    const result = await response.json();
    if (!result.success) { progress.update("analyze", "error", result.message || "Erreur serveur"); showPopup(buildErrorPopup(result.message || getRandomErrorMessage())); return null; }
    return result;
  }

  try {
    let result = await fetchAnalysisOnce();
    if (!result) return;

    if (collectInfo.submitted && collectInfo.isCurrentVehicle) {
      const l4 = (result?.data?.filters || []).find((f) => f.filter_id === "L4");
      if (l4 && l4.status === "skip") {
        progress.update("analyze", "running", "Retry L4...");
        await sleep(2000);
        const retried = await fetchAnalysisOnce();
        if (retried) result = retried;
      }
    }

    lastScanId = result.data.scan_id || null;
    progress.update("analyze", "done", (result.data.filters || []).length + " filtres analysés");
    progress.showFilters(result.data.filters || []);
    const score = result.data.score;
    const verdict = score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise";
    progress.showScore(score, verdict);

    progress.update("autoviza", "running");
    const freeReportUrl = await extractor.detectFreeReport();
    progress.update("autoviza", freeReportUrl ? "done" : "skip", freeReportUrl ? "Rapport gratuit trouvé" : "Aucun rapport disponible");

    const bonusSignals = extractor.getBonusSignals();

    const detailsBtn = document.getElementById("copilot-progress-details-btn");
    if (detailsBtn) {
      detailsBtn.style.display = "inline-block";
      detailsBtn.addEventListener("click", function () { showPopup(buildResultsPopup(result.data, { autovizaUrl: freeReportUrl, bonusSignals })); });
    }
  } catch (err) {
    progress.update("analyze", "error", "Erreur inattendue");
    showPopup(buildErrorPopup(getRandomErrorMessage()));
  }
}

// ── Point d'entree ─────────────────────────────────────────────

function isAdPage() { return isAdPageLBC(); }

function init() {
  const extractor = getExtractor(window.location.href);
  if (!extractor || !extractor.isAdPage(window.location.href)) return;
  removePopup();
  if (window.__copilotRunning) return;
  window.__copilotRunning = true;
  initLbcDeps({ backendFetch, sleep, apiUrl: API_URL });
  extractor.initDeps({ fetch: backendFetch, apiUrl: API_URL });
  runAnalysis(extractor).finally(() => { window.__copilotRunning = false; });
}

init();

// ── Test exports (Vitest / ESM) ────────────────────────────────────
// Re-export everything tests need. Functions defined in this file are
// exported directly; functions from leboncoin.js are already imported above.
export {
  // From this file (content.js)
  scoreColor, statusColor, statusIcon, filterLabel,
  SIMULATED_FILTERS, API_URL,
  formatPrecisionStars, PRECISION_LABELS,
  isAdPage,
  // Re-exports from leboncoin.js
  extractVehicleFromNextData, extractRegionFromNextData, extractLocationFromNextData,
  buildLocationParam, DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices, fetchSearchPricesViaApi, fetchSearchPricesViaHtml,
  buildApiFilters, parseRange, filterAndMapSearchAds, extractMileageFromNextData,
  isUserLoggedIn, revealPhoneNumber, isStaleData,
  maybeCollectMarketPrices, LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  getMileageRange, getHorsePowerRange, COLLECT_COOLDOWN_MS,
  toLbcBrandToken, LBC_BRAND_ALIASES,
  getAdDetails, executeBonusJobs, reportJobDone,
};
