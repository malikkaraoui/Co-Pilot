/**
 * OKazCar Content Script
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
import { getWinterTireSignals } from './utils/winter-tires.js';
import { SIMULATED_FILTERS } from './ui/filters/index.js';
import { normalizeAnalyzeApiUrl } from './utils/api-url.js';
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
// __API_URL__ est injecte par esbuild au build (cf. build.js).
// En dev sans build, fallback sur localhost.
const API_URL = normalizeAnalyzeApiUrl(
  (typeof __API_URL__ !== 'undefined' ? __API_URL__ : null),
  "http://localhost:5001/api/analyze",
);

// Garde l'ID du dernier scan pour le lien "voir le rapport" dans la popup
let lastScanId = null;

// Messages d'erreur "theme auto" — on en pioche un au hasard
// pour rendre les erreurs serveur un peu moins penibles
const ERROR_MESSAGES = [
  "Oh mince, on a crevé ! Réessayez dans un instant.",
  "Le moteur a calé... Notre serveur fait une pause, retentez !",
  "Panne sèche ! Impossible de joindre le serveur.",
  "Embrayage patiné... L'analyse n'a pas pu démarrer.",
  "Vidange en cours ! Le serveur revient dans un instant.",
];

/**
 * Pioche un message d'erreur aleatoire dans la liste.
 * Rend les erreurs backend plus humaines et moins repetitives.
 *
 * @returns {string} Message d'erreur en francais, theme automobile
 */
function getRandomErrorMessage() {
  return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
}

// ── Generic runAnalysis ──────────────────────────────────────

/**
 * Pipeline principal d'analyse d'une annonce.
 *
 * Execute en 3 phases sequentielles :
 * 1. Extraction — lit les donnees de l'annonce via l'extracteur du site
 * 2. Collecte prix marche — cherche des annonces similaires pour comparer
 * 3. Analyse backend — envoie tout au serveur qui applique les filtres
 *
 * Chaque phase met a jour la barre de progression en temps reel.
 * En fin de pipeline, on affiche le score et le bouton "voir les details".
 *
 * @param {Object} [injectedExtractor] - Extracteur force (pour les tests).
 *   En usage normal, on le detecte automatiquement via l'URL.
 */
async function runAnalysis(injectedExtractor) {
  const extractor = injectedExtractor || getExtractor(window.location.href);
  if (!extractor) { showPopup(buildErrorPopup("Site non supporté.")); return; }

  const progress = showProgress();

  // Phase 1 : Extraction des donnees depuis la page (DOM / __NEXT_DATA__ / etc.)
  progress.update("extract", "running");
  const payload = await extractor.extract();
  if (!payload) {
    console.warn("[OKazCar] extract() → null");
    progress.update("extract", "error", "Impossible de lire les données");
    showPopup(buildErrorPopup("Impossible de lire les données de cette page."));
    return;
  }
  const adId = payload.next_data?.props?.pageProps?.ad?.list_id || "";
  progress.update("extract", "done", adId ? "ID annonce : " + adId : "Données extraites");

  // Afficher le resume du vehicule dans la barre de progression
  // (marque + modele + annee — pour que l'utilisateur sache qu'on a bien identifie son annonce)
  const summary = extractor.getVehicleSummary();
  const vehicleLabel = document.getElementById("okazcar-progress-vehicle");
  if (vehicleLabel && summary?.make) {
    vehicleLabel.textContent = [summary.make, summary.model, summary.year].filter(Boolean).join(" ");
  }

  // Recuperation du telephone du vendeur (LBC uniquement).
  // Necessite d'etre connecte sur LBC — sinon on affiche un hint.
  if (extractor.hasPhone()) {
    if (extractor.isLoggedIn()) {
      progress.update("phone", "running");
      const phone = await extractor.revealPhone();
      if (phone) {
        // Format: +33 X XX XX XX XX (indicatif +33 puis 1 chiffre + 4 groupes de 2)
        // ou 0X XX XX XX XX pour les numeros locaux
        const formatted = phone.replace(/^\+33(\d)(\d{2})(\d{2})(\d{2})(\d{2})$/, "+33 $1 $2 $3 $4 $5")
          .replace(/^(0\d)(\d{2})(\d{2})(\d{2})(\d{2})$/, "$1 $2 $3 $4 $5")
          .replace(/(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/, "$1 $2 $3 $4 $5"); // fallback
        progress.update("phone", "done", formatted);
      }
      else { progress.update("phone", "warning", "Numéro non récupéré"); }
    } else { progress.update("phone", "skip", "Connectez-vous sur LeBonCoin pour analyser le numéro du vendeur"); }
  } else { progress.update("phone", "skip", "Pas de téléphone"); }

  // Phase 2 : Collecte de prix marche (annonces similaires sur LBC).
  // On cherche des annonces comparables pour alimenter le filtre L4 (prix vs marche).
  let collectInfo = { submitted: false };
  try {
    collectInfo = await extractor.collectMarketPrices(progress);
  } catch (err) {
    console.error("[OKazCar] collectMarketPrices erreur:", err);
    progress.update("job", "error", "Erreur collecte");
  }
  if (!collectInfo.submitted) {
    const jobEl = document.getElementById("okazcar-step-job");
    if (jobEl && jobEl.getAttribute("data-status") === "pending") {
      progress.update("job", "skip", "Collecte non disponible");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }
  }

  // Phase 3 : Envoi au backend pour analyse par le moteur de filtres.
  // Deux formats de payload selon l'extracteur :
  //   - "raw" = on envoie le blob __NEXT_DATA__ brut (LBC)
  //   - sinon = donnees deja structurees par l'extracteur (AS24, LC)
  progress.update("analyze", "running");
  const apiBody = payload.type === 'raw'
    ? { url: window.location.href, next_data: payload.next_data }
    : { url: window.location.href, ad_data: payload.ad_data, source: payload.source };

  /**
   * Appel unique au backend d'analyse. Extrait en fonction separee
   * pour pouvoir retenter si L4 etait en "skip" (prix pas encore dispo).
   *
   * @returns {Promise<Object|null>} Resultat de l'analyse, ou null si erreur
   */
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

    // Si on vient de soumettre des prix marche pour CE vehicule,
    // le backend n'a peut-etre pas encore eu le temps de les indexer.
    // On retente une fois apres 2s pour que L4 puisse calculer.
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

    // Verdict final : score global + message synthetique
    const score = result.data.score;
    const verdict = score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise";
    progress.showScore(score, verdict);

    // Detection rapport AutoViza gratuit (certaines annonces LBC en ont un)
    progress.update("autoviza", "running");
    const freeReportUrl = await extractor.detectFreeReport();
    progress.update("autoviza", freeReportUrl ? "done" : "skip", freeReportUrl ? "Rapport gratuit trouvé" : "Aucun rapport disponible");

    // Signaux bonus : infos contextuelles (Loi Montagne / pneus hiver, etc.)
    // qui ne sont pas des filtres mais meritent d'etre affiches
    const bonusSignals = extractor.getBonusSignals();
    const tireSignals = getWinterTireSignals(extractor.getLocation());
    bonusSignals.push(...tireSignals);

    // Bouton "Voir les details" : ouvre la popup complete avec tous les filtres
    const detailsBtn = document.getElementById("okazcar-progress-details-btn");
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

/**
 * Detection multi-site : verifie si l'URL courante est une page d'annonce.
 * Delegue au registre d'extracteurs (LBC, AS24, LC).
 * Utilise par les tests — a l'execution, init() appelle extractor.isAdPage() directement.
 *
 * @returns {boolean} true si on est sur une page d'annonce reconnue
 */
function isAdPage() {
  const extractor = getExtractor(window.location.href);
  return extractor ? extractor.isAdPage(window.location.href) : false;
}

/**
 * Point d'entree du content script.
 *
 * 1. Detecte le site et verifie qu'on est sur une page d'annonce
 * 2. Nettoie toute popup precedente (re-injection)
 * 3. Initialise les dependances (fetch proxy, DOM, extracteur)
 * 4. Lance l'analyse complete
 *
 * Le flag __okazcarRunning empeche les executions en parallele
 * (le popup peut re-injecter le script si l'utilisateur re-clique).
 */
function init() {
  const extractor = getExtractor(window.location.href);
  if (!extractor || !extractor.isAdPage(window.location.href)) return;
  removePopup();
  if (window.__okazcarRunning) return;
  window.__okazcarRunning = true;
  initLbcDeps({ backendFetch, sleep, apiUrl: API_URL });
  initDom({ runAnalysis, apiUrl: API_URL, getLastScanId: () => lastScanId });
  extractor.initDeps({ fetch: backendFetch, apiUrl: API_URL });
  runAnalysis(extractor).finally(() => { window.__okazcarRunning = false; });
}

init();

// ── Test exports (Vitest / ESM) ────────────────────────────────────
// Re-export de tout ce dont les tests ont besoin.
// Les fonctions viennent de utils/, ui/ et extractors/leboncoin/.
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
