/**
 * Co-Pilot Content Script
 *
 * Injecte on-demand (via le popup de l'extension) et affiche
 * les résultats d'analyse dans une popup contextuelle.
 * Aucune action automatique -- zero bruit sur la page.
 */

(function () {
  "use strict";

  // ── Configuration ──────────────────────────────────────────────
  const API_URL = "http://localhost:5001/api/analyze";
  // Messages de dégradation UX (humour automobile)
  const ERROR_MESSAGES = [
    "Oh mince, on a crevé ! Réessayez dans un instant.",
    "Le moteur a calé... Notre serveur fait une pause, retentez !",
    "Panne sèche ! Impossible de joindre le serveur.",
    "Embrayage patiné... L'analyse n'a pas pu démarrer.",
    "Vidange en cours ! Le serveur revient dans un instant.",
  ];

  // ── Utilitaires ────────────────────────────────────────────────

  /** Echappe les caracteres HTML pour prevenir les injections XSS. */
  function escapeHTML(str) {
    if (typeof str !== "string") return String(str ?? "");
    const el = document.createElement("span");
    el.textContent = str;
    return el.innerHTML;
  }

  /** Retourne un message d'erreur aléatoire. */
  function getRandomErrorMessage() {
    return ERROR_MESSAGES[Math.floor(Math.random() * ERROR_MESSAGES.length)];
  }

  /**
   * Detecte si les donnees __NEXT_DATA__ sont obsoletes (navigation SPA).
   * Compare l'ID de l'annonce dans les donnees avec l'ID dans l'URL courante.
   * Retourne true (= perime) si on ne peut pas confirmer la correspondance.
   */
  function isStaleData(data) {
    const urlMatch = window.location.href.match(/\/(\d+)(?:[?#]|$)/);
    if (!urlMatch) return false;
    const urlAdId = urlMatch[1];

    const ad = data?.props?.pageProps?.ad;
    if (!ad) return true; // Pas d'annonce dans les donnees → considerer perime

    const dataAdId = String(ad.list_id || ad.id || "");
    if (!dataAdId) return true; // Pas d'ID → impossible de verifier → perime

    return dataAdId !== urlAdId;
  }

  /**
   * Extrait le JSON __NEXT_DATA__ a jour.
   *
   * 1. Lit les donnees injectees par le background (world:MAIN)
   * 2. Verifie la fraicheur (compare ad ID vs URL)
   * 3. Si obsoletes (nav SPA) : re-fetch le HTML de la page pour un __NEXT_DATA__ frais
   */
  async function extractNextData() {
    // 1. Donnees injectees par le background (world:MAIN)
    const el = document.getElementById("__copilot_next_data__");
    if (el && el.textContent) {
      try {
        const data = JSON.parse(el.textContent);
        el.remove();
        if (data && !isStaleData(data)) return data;
      } catch {
        // continue
      }
    }

    // 2. Tag script DOM (premiere page seulement)
    const script = document.getElementById("__NEXT_DATA__");
    if (script) {
      try {
        const data = JSON.parse(script.textContent);
        if (data && !isStaleData(data)) return data;
      } catch {
        // continue
      }
    }

    // 3. Fallback SPA : re-fetch le HTML de la page courante
    try {
      const resp = await fetch(window.location.href, {
        credentials: "same-origin",
        headers: { "Accept": "text/html" },
      });
      const html = await resp.text();
      const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
      if (match) return JSON.parse(match[1]);
    } catch {
      // extraction impossible
    }

    return null;
  }

  /** Détermine la couleur selon le score. */
  function scoreColor(score) {
    if (score >= 70) return "#22c55e"; // vert
    if (score >= 40) return "#f59e0b"; // orange
    return "#ef4444"; // rouge
  }

  /** Détermine la couleur selon le statut du filtre. */
  function statusColor(status) {
    switch (status) {
      case "pass": return "#22c55e";
      case "warning": return "#f59e0b";
      case "fail": return "#ef4444";
      case "skip": return "#9ca3af";
      default: return "#6b7280";
    }
  }

  /** Détermine l'icône selon le statut du filtre. */
  function statusIcon(status) {
    switch (status) {
      case "pass": return "\u2713"; // checkmark
      case "warning": return "\u26A0"; // warning triangle
      case "fail": return "\u2717"; // cross
      case "skip": return "\u2014"; // dash
      default: return "?";
    }
  }

  /** Labels lisibles pour chaque filter_id. */
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
    };
    return labels[filterId] || filterId;
  }

  // ── Jauge circulaire SVG ───────────────────────────────────────

  /**
   * Génère le SVG de la jauge circulaire.
   * @param {number} score - Score de 0 a 100.
   * @returns {string} Le markup SVG.
   */
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

  // ── Construction de la popup ───────────────────────────────────

  /** Filtres dont les donnees sont simulees (seed data, pas de source reelle). */
  const SIMULATED_FILTERS = ["L4", "L5"];

  /** Construit le HTML de la liste des filtres. */
  function buildFiltersList(filters) {
    if (!filters || !filters.length) return "";

    return filters
      .map((f) => {
        const color = statusColor(f.status);
        const icon = statusIcon(f.status);
        const label = filterLabel(f.filter_id);
        const detailsHTML = f.details ? buildDetailsHTML(f.details) : "";
        const simulatedBadge = SIMULATED_FILTERS.includes(f.filter_id)
          ? '<span class="copilot-badge-simulated">Donnees simulees</span>'
          : "";

        return `
          <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
            <div class="copilot-filter-header">
              <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
              <span class="copilot-filter-label">${escapeHTML(label)}${simulatedBadge}</span>
              <span class="copilot-filter-score" style="color:${color}">${Math.round(f.score * 100)}%</span>
            </div>
            <p class="copilot-filter-message">${escapeHTML(f.message)}</p>
            ${detailsHTML}
          </div>
        `;
      })
      .join("");
  }

  /** Labels francais pour les cles de details courantes. */
  const DETAIL_LABELS = {
    fields_present: "Champs renseignés",
    fields_total: "Champs totaux",
    missing_critical: "Champs critiques manquants",
    missing_secondary: "Champs secondaires manquants",
    matched_model: "Modèle reconnu",
    confidence: "Confiance",
    km_per_year: "Km / an",
    expected_range: "Fourchette attendue",
    actual_km: "Kilométrage réel",
    expected_km: "Kilométrage attendu",
    price: "Prix annonce",
    argus_price: "Prix Argus",
    price_diff: "Écart de prix",
    price_diff_pct: "Écart (%)",
    mean_price: "Prix moyen",
    std_dev: "Écart-type",
    z_score: "Z-score",
    phone_valid: "Téléphone valide",
    phone: "Téléphone",
    siret: "SIRET",
    siret_valid: "SIRET valide",
    company_name: "Raison sociale",
    is_import: "Véhicule importé",
    import_indicators: "Indicateurs import",
    color: "Couleur",
  };

  /** Formate une valeur de detail pour l'affichage humain. */
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

  /** Construit le HTML des details d'un filtre (depliable). */
  function buildDetailsHTML(details) {
    const entries = Object.entries(details)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => {
        const label = DETAIL_LABELS[k] || k;
        const val = formatDetailValue(v);
        return `<div class="copilot-detail-row"><span class="copilot-detail-key">${escapeHTML(label)}</span><span class="copilot-detail-value">${val}</span></div>`;
      })
      .join("");

    if (!entries) return "";

    return `
      <details class="copilot-filter-details">
        <summary>Voir les détails</summary>
        <div class="copilot-details-content">${entries}</div>
      </details>
    `;
  }

  /** Construit la section premium floutée (paywall liquid glass). */
  function buildPremiumSection() {
    return `
      <div class="copilot-premium-section">
        <div class="copilot-premium-blur">
          <div class="copilot-premium-fake">
            <p><strong>Rapport détaillé du véhicule</strong></p>
            <p>Fiche fiabilité complète avec problèmes connus, coûts d'entretien prévus,
               historique des rappels constructeur et comparaison avec les alternatives du segment.</p>
            <p>Estimation de la valeur réelle basée sur 12 critères régionaux.</p>
            <p>Recommandation d'achat personnalisée avec score de confiance.</p>
          </div>
        </div>
        <div class="copilot-premium-overlay">
          <div class="copilot-premium-glass">
            <p class="copilot-premium-title">Analyse complète</p>
            <p class="copilot-premium-subtitle">Débloquez le rapport détaillé avec fiabilité, coûts et recommandations.</p>
            <button class="copilot-premium-cta" id="copilot-premium-btn">
              Débloquer – 9,90 €
          </div>
        </div>
      </div>
    `;
  }

  /** Construit la popup complete des resultats. */
  function buildResultsPopup(data) {
    const { score, is_partial, filters, vehicle } = data;
    const color = scoreColor(score);

    const vehicleInfo = vehicle
      ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim()
      : "Véhicule";

    const partialBadge = is_partial
      ? `<span class="copilot-badge-partial">Analyse partielle</span>`
      : "";

    return `
      <div class="copilot-popup" id="copilot-popup">
        <div class="copilot-popup-header">
          <div class="copilot-popup-title-row">
            <span class="copilot-popup-title">Co-Pilot</span>
            <button class="copilot-popup-close" id="copilot-close">&times;</button>
          </div>
          <p class="copilot-popup-vehicle">${escapeHTML(vehicleInfo)}</p>
          ${partialBadge}
        </div>

        <div class="copilot-popup-gauge">
          ${buildGaugeSVG(score)}
          <p class="copilot-verdict" style="color:${color}">
            ${score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise"}
          </p>
        </div>

        <div class="copilot-popup-filters">
          <h3 class="copilot-section-title">Détails de l'analyse</h3>
          ${buildFiltersList(filters)}
        </div>

        ${buildPremiumSection()}

        <div class="copilot-popup-footer">
          <p>Co-Pilot v1.0 &middot; Analyse automatisée</p>
        </div>
      </div>
    `;
  }

  /** Construit la popup d'erreur. */
  function buildErrorPopup(message) {
    return `
      <div class="copilot-popup copilot-popup-error" id="copilot-popup">
        <div class="copilot-popup-header">
          <div class="copilot-popup-title-row">
            <span class="copilot-popup-title">Co-Pilot</span>
            <button class="copilot-popup-close" id="copilot-close">&times;</button>
          </div>
        </div>
        <div class="copilot-error-body">
          <div class="copilot-error-icon">&#x1F527;</div>
          <p class="copilot-error-message">${escapeHTML(message)}</p>
          <button class="copilot-btn copilot-btn-retry" id="copilot-retry">Réessayer</button>
        </div>
      </div>
    `;
  }

  // ── Logique principale ─────────────────────────────────────────

  /** Supprime la popup existante si presente. */
  function removePopup() {
    const existing = document.getElementById("copilot-popup");
    if (existing) existing.remove();
    const overlay = document.getElementById("copilot-overlay");
    if (overlay) overlay.remove();
  }

  /** Affiche une popup dans un overlay. */
  function showPopup(html) {
    removePopup();

    const overlay = document.createElement("div");
    overlay.id = "copilot-overlay";
    overlay.className = "copilot-overlay";
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) removePopup();
    });

    const container = document.createElement("div");
    container.innerHTML = html;
    overlay.appendChild(container.firstElementChild);
    document.body.appendChild(overlay);

    // Bouton fermer
    const closeBtn = document.getElementById("copilot-close");
    if (closeBtn) closeBtn.addEventListener("click", removePopup);

    // Bouton reessayer
    const retryBtn = document.getElementById("copilot-retry");
    if (retryBtn) retryBtn.addEventListener("click", () => { removePopup(); runAnalysis(); });

    // Bouton premium (log pour le moment)
    const premiumBtn = document.getElementById("copilot-premium-btn");
    if (premiumBtn) {
      premiumBtn.addEventListener("click", () => {
        // Premium CTA -- Stripe integration Phase 2
        premiumBtn.textContent = "Bientôt disponible !";
        premiumBtn.disabled = true;
      });
    }
  }

  /** Affiche l'animation de chargement. */
  function showLoading() {
    removePopup();
    const html = `
      <div class="copilot-popup copilot-popup-loading" id="copilot-popup">
        <div class="copilot-loading-body">
          <div class="copilot-spinner"></div>
          <p>Analyse en cours...</p>
        </div>
      </div>
    `;
    showPopup(html);
  }

  /**
   * Extrait les infos vehicule (make, model, year) depuis __NEXT_DATA__
   * pour pouvoir lancer la collecte AVANT l'analyse.
   */
  function extractVehicleFromNextData(nextData) {
    const ad = nextData?.props?.pageProps?.ad;
    if (!ad) return {};

    const attrs = (ad.attributes || []).reduce((acc, a) => {
      const key = a.key || a.key_label || a.label || a.name;
      const val = a.value || a.value_label || a.text || a.value_text;
      if (key) acc[key] = val;
      return acc;
    }, {});

    return {
      make: attrs["brand"] || attrs["Marque"] || "",
      model: attrs["model"] || attrs["Modèle"] || attrs["modele"] || "",
      year: attrs["regdate"] || attrs["Année modèle"] || attrs["Année"] || attrs["year"] || "",
    };
  }

  /**
   * Lance l'analyse : extrait les donnees, collecte les prix SI besoin
   * (AVANT l'analyse pour que L4/L5 aient des donnees fraiches),
   * puis appelle l'API et affiche les resultats.
   */
  async function runAnalysis() {
    showLoading();

    const nextData = await extractNextData();
    if (!nextData) {
      showPopup(buildErrorPopup("Impossible de lire les données de cette page. Vérifiez que vous êtes sur une annonce Leboncoin."));
      return;
    }

    // Collecte des prix AVANT l'analyse (silencieuse, ~1-2s)
    // Permet a L4/L5 d'avoir des donnees fraiches pour ce vehicule
    const vehicle = extractVehicleFromNextData(nextData);
    if (vehicle.make && vehicle.model && vehicle.year) {
      await maybeCollectMarketPrices(vehicle).catch(() => {});
    }

    try {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: window.location.href, next_data: nextData }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        const msg = errorData?.message || getRandomErrorMessage();
        showPopup(buildErrorPopup(msg));
        return;
      }

      const result = await response.json();

      if (!result.success) {
        showPopup(buildErrorPopup(result.message || getRandomErrorMessage()));
        return;
      }

      showPopup(buildResultsPopup(result.data));
    } catch (err) {
      // Erreur silencieuse -- affichee dans la popup
      showPopup(buildErrorPopup(getRandomErrorMessage()));
    }
  }

  // ── Collecte crowdsourcee des prix du marche ────────────────────

  /** Mapping des regions LeBonCoin (valeurs du parametre locations). */
  const LBC_REGIONS = {
    "Ile-de-France": "r_12",
    "Auvergne-Rhone-Alpes": "r_1",
    "Provence-Alpes-Cote d'Azur": "r_21",
    "Occitanie": "r_16",
    "Nouvelle-Aquitaine": "r_54",
    "Hauts-de-France": "r_22",
    "Grand Est": "r_44",
    "Bretagne": "r_6",
    "Pays de la Loire": "r_18",
    "Normandie": "r_28",
    "Bourgogne-Franche-Comte": "r_27",
    "Centre-Val de Loire": "r_7",
    "Corse": "r_9",
  };

  /** Cooldown entre deux collectes (anti-ban). */
  const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h

  /** Extrait la region depuis les donnees __NEXT_DATA__ de l'annonce courante. */
  function extractRegionFromPage() {
    const nextEl = document.getElementById("__NEXT_DATA__");
    if (!nextEl) return "";
    try {
      const nd = JSON.parse(nextEl.textContent);
      const loc = nd?.props?.pageProps?.ad?.location;
      return loc?.region_name || loc?.region || "";
    } catch {
      return "";
    }
  }

  /**
   * Collecte intelligente : demande au serveur quel vehicule a besoin de
   * mise a jour, puis collecte les prix sur LeBonCoin.
   *
   * Chaque user travaille pour la communaute :
   * - Cooldown 24h (localStorage) pour eviter les bans
   * - Le serveur assigne le vehicule le plus prioritaire a collecter
   * - Si le vehicule courant est a jour, un autre modele est assigne
   *
   * Fire-and-forget : ne bloque pas l'affichage des resultats.
   */
  async function maybeCollectMarketPrices(vehicle) {
    const { make, model, year } = vehicle;
    if (!make || !model || !year) return;

    // 1. Cooldown 24h (localStorage)
    const lastCollect = parseInt(localStorage.getItem("copilot_last_collect") || "0", 10);
    if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) return;

    // 2. Extraire la region de l'annonce courante
    const region = extractRegionFromPage();
    if (!region) return;

    // 3. Demander au serveur quel vehicule collecter
    const jobUrl = API_URL.replace("/analyze", "/market-prices/next-job")
      + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`;

    let jobResp;
    try {
      jobResp = await fetch(jobUrl).then((r) => r.json());
    } catch {
      return; // serveur injoignable -- silencieux
    }
    if (!jobResp?.data?.collect) return;

    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;

    // 4. Chercher le vehicule cible sur LeBonCoin
    const searchText = encodeURIComponent(`${target.make} ${target.model}`);
    const regionParam = LBC_REGIONS[targetRegion] || "";
    let searchUrl = `https://www.leboncoin.fr/recherche?category=2&text=${searchText}`;
    if (regionParam) searchUrl += `&locations=${regionParam}`;

    try {
      const resp = await fetch(searchUrl, {
        credentials: "same-origin",
        headers: { "Accept": "text/html" },
      });
      const html = await resp.text();

      const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
      if (!match) return;

      const data = JSON.parse(match[1]);
      const ads = data?.props?.pageProps?.searchData?.ads
                || data?.props?.pageProps?.initialProps?.searchData?.ads
                || [];

      const prices = ads
        .filter((ad) => ad.price && ad.price[0] > 500)
        .map((ad) => ad.price[0]);

      if (prices.length >= 3) {
        const marketUrl = API_URL.replace("/analyze", "/market-prices");
        await fetch(marketUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            make: target.make,
            model: target.model,
            year: parseInt(target.year, 10),
            region: targetRegion,
            prices: prices,
          }),
        });
      }
    } catch {
      // Silencieux -- ne pas perturber l'experience utilisateur
    }

    // 5. Sauvegarder le timestamp (meme si pas assez de prix)
    localStorage.setItem("copilot_last_collect", String(Date.now()));
  }

  // ── Point d'entree ─────────────────────────────────────────────

  /** Vérifie qu'on est bien sur une page d'annonce. */
  function isAdPage() {
    const url = window.location.href;
    return url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/");
  }

  /**
   * Initialisation du content script.
   * Injecte uniquement on-demand (via le popup de l'extension).
   * Lance directement l'analyse sans attendre de clic supplementaire.
   */
  function init() {
    if (!isAdPage()) return;

    // Toujours supprimer l'ancienne popup (navigation SPA = meme DOM)
    removePopup();

    // Si une analyse est deja en cours, ne pas en lancer une autre
    if (window.__copilotRunning) return;
    window.__copilotRunning = true;

    // Lancer l'analyse directement (l'utilisateur a deja clique dans le popup)
    runAnalysis().finally(() => { window.__copilotRunning = false; });
  }

  init();
})();
