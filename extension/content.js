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
import { backendFetch, sleep } from './utils/fetch.js';
import { formatPrecisionStars, PRECISION_LABELS } from './utils/format.js';
import { scoreColor, statusColor, statusIcon, filterLabel } from './utils/styles.js';
import { initDom, removePopup, showPopup } from './ui/dom.js';
import { buildResultsPopup, buildErrorPopup, buildNotAVehiclePopup, buildNotSupportedPopup } from './ui/popups.js';
import { showProgress } from './ui/progress.js';
import { SIMULATED_FILTERS } from './ui/filters/index.js';
import {
  initLbcDeps,
  extractVehicleFromNextData, extractRegionFromNextData, extractLocationFromNextData,
  buildLocationParam, DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices, fetchSearchPricesViaApi, fetchSearchPricesViaHtml,
  buildApiFilters, parseRange, filterAndMapSearchAds, extractMileageFromNextData,
  isUserLoggedIn, revealPhoneNumber, isStaleData, isAdPageLBC,
  maybeCollectMarketPrices, LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  getMileageRange, getHorsePowerRange, COLLECT_COOLDOWN_MS,
  toLbcBrandToken, LBC_BRAND_ALIASES, brandMatches, getAdDetails, executeBonusJobs, reportJobDone,
  GENERIC_MODELS, EXCLUDED_CATEGORIES,
} from './extractors/leboncoin/index.js';

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

function getRandomErrorMessage() {
  return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
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
  initDom({ runAnalysis, apiUrl: API_URL, getLastScanId: () => lastScanId });
  extractor.initDeps({ fetch: backendFetch, apiUrl: API_URL });
  runAnalysis(extractor).finally(() => { window.__copilotRunning = false; });
}

init();

// ── Test exports (Vitest / ESM) ────────────────────────────────────
// Re-export everything tests need. Functions from utils/ and ui/ are
// imported above; functions from leboncoin.js are already imported.
export {
  // From utils/
  scoreColor, statusColor, statusIcon, filterLabel,
  formatPrecisionStars, PRECISION_LABELS,
  // From ui/
  SIMULATED_FILTERS,
  // Defined here
  API_URL, isAdPage,
  // Re-exports from leboncoin.js
  extractVehicleFromNextData, extractRegionFromNextData, extractLocationFromNextData,
  buildLocationParam, DEFAULT_SEARCH_RADIUS, MIN_PRICES_FOR_ARGUS,
  fetchSearchPrices, fetchSearchPricesViaApi, fetchSearchPricesViaHtml,
  buildApiFilters, parseRange, filterAndMapSearchAds, extractMileageFromNextData,
  isUserLoggedIn, revealPhoneNumber, isStaleData,
  maybeCollectMarketPrices, LBC_REGIONS, LBC_FUEL_CODES, LBC_GEARBOX_CODES,
  getMileageRange, getHorsePowerRange, COLLECT_COOLDOWN_MS,
  toLbcBrandToken, LBC_BRAND_ALIASES, brandMatches,
  getAdDetails, executeBonusJobs, reportJobDone,
};
