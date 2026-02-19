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

  /** Pause utilitaire. */
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
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
          ? '<span class="copilot-badge-simulated">Données simulées</span>'
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
    phone_login_hint: "Téléphone",
    days_online: "Première publication (jours)",
    republished: "Annonce republiée",
    stale_below_market: "Prix bas + annonce ancienne",
    delta_eur: "Écart (€)",
    delta_pct: "Écart (%)",
    price_annonce: "Prix annonce",
    price_reference: "Prix référence",
    sample_count: "Nb annonces comparées",
    source: "Source prix",
    price_argus_mid: "Argus (médian)",
    price_argus_low: "Argus (bas)",
    price_argus_high: "Argus (haut)",
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
    // phone_login_hint : bandeau invite a se connecter sur LBC
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
        const val = formatDetailValue(v);
        return `<div class="copilot-detail-row"><span class="copilot-detail-key">${escapeHTML(label)}</span><span class="copilot-detail-value">${val}</span></div>`;
      })
      .join("");

    if (!entries && !phoneHintHTML) return "";

    const detailsBlock = entries
      ? `<details class="copilot-filter-details">
          <summary>Voir les détails</summary>
          <div class="copilot-details-content">${entries}</div>
        </details>`
      : "";

    return phoneHintHTML + detailsBlock;
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

  /** Construit la banniere YouTube (video de presentation du vehicule). */
  function buildYouTubeBanner(featuredVideo) {
    if (!featuredVideo || !featuredVideo.url) return "";
    const title = featuredVideo.title || "Découvrir ce modèle en vidéo";
    const channel = featuredVideo.channel || "";
    return `
      <div class="copilot-youtube-banner">
        <a href="${escapeHTML(featuredVideo.url)}" target="_blank" rel="noopener noreferrer"
           class="copilot-youtube-link">
          <span class="copilot-youtube-icon">&#x25B6;&#xFE0F;</span>
          <span class="copilot-youtube-text">
            <strong>Découvrir ce modèle en vidéo</strong>
            <small>${escapeHTML(channel)}${channel ? " · " : ""}${escapeHTML(title).substring(0, 50)}</small>
          </span>
          <span class="copilot-youtube-arrow">&rsaquo;</span>
        </a>
      </div>
    `;
  }

  /** Construit la banniere Autoviza (rapport gratuit offert par LBC). */
  function buildAutovizaBanner(autovizaUrl) {
    if (!autovizaUrl) return "";
    return `
      <div class="copilot-autoviza-banner">
        <a href="${escapeHTML(autovizaUrl)}" target="_blank" rel="noopener noreferrer"
           class="copilot-autoviza-link">
          <span class="copilot-autoviza-icon">&#x1F4CB;</span>
          <span class="copilot-autoviza-text">
            <strong>Rapport d'historique gratuit</strong>
            <small>Offert par LeBonCoin via Autoviza (valeur 25 €)</small>
          </span>
          <span class="copilot-autoviza-arrow">&rsaquo;</span>
        </a>
      </div>`;
  }

  /** Construit la popup complete des resultats. */
  function buildResultsPopup(data, options = {}) {
    const { score, is_partial, filters, vehicle, featured_video } = data;
    const { autovizaUrl } = options;
    const color = scoreColor(score);

    const vehicleInfo = vehicle
      ? `${vehicle.make || ""} ${vehicle.model || ""} ${vehicle.year || ""}`.trim()
      : "Véhicule";

    const partialBadge = is_partial
      ? `<span class="copilot-badge-partial">Analyse partielle</span>`
      : "";

    // Badge "En vente depuis X jours" (extrait des details L9)
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

    return `
      <div class="copilot-popup" id="copilot-popup">
        <div class="copilot-popup-header">
          <div class="copilot-popup-title-row">
            <span class="copilot-popup-title">Co-Pilot</span>
            <button class="copilot-popup-close" id="copilot-close">&times;</button>
          </div>
          <p class="copilot-popup-vehicle">${escapeHTML(vehicleInfo)} ${daysOnlineBadge}</p>
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

  function buildNotAVehiclePopup(message, category) {
    return `
      <div class="copilot-popup" id="copilot-popup">
        <div class="copilot-popup-header">
          <div class="copilot-popup-title-row">
            <span class="copilot-popup-title">Co-Pilot</span>
            <button class="copilot-popup-close" id="copilot-close">&times;</button>
          </div>
        </div>
        <div class="copilot-not-vehicle-body">
          <div class="copilot-not-vehicle-icon">&#x1F6AB;</div>
          <h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3>
          <p class="copilot-not-vehicle-category">
            Cat&eacute;gorie d&eacute;tect&eacute;e : <strong>${escapeHTML(category || "inconnue")}</strong>
          </p>
          <p class="copilot-not-vehicle-hint">
            Co-Pilot analyse uniquement les annonces de v&eacute;hicules.
          </p>
        </div>
      </div>
    `;
  }

  function buildNotSupportedPopup(message, category) {
    return `
      <div class="copilot-popup" id="copilot-popup">
        <div class="copilot-popup-header">
          <div class="copilot-popup-title-row">
            <span class="copilot-popup-title">Co-Pilot</span>
            <button class="copilot-popup-close" id="copilot-close">&times;</button>
          </div>
        </div>
        <div class="copilot-not-vehicle-body">
          <div class="copilot-not-vehicle-icon">&#x1F3CD;</div>
          <h3 class="copilot-not-vehicle-title">${escapeHTML(message)}</h3>
          <p class="copilot-not-vehicle-category">
            Cat&eacute;gorie : <strong>${escapeHTML(category || "inconnue")}</strong>
          </p>
          <p class="copilot-not-vehicle-hint">
            On bosse dessus, promis. Restez branch&eacute; !
          </p>
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

    const make = attrs["brand"] || attrs["Marque"] || "";
    let model = attrs["model"] || attrs["Modèle"] || attrs["modele"] || "";

    // Si LBC renvoie un modele generique ("Autres"), tenter d'extraire le vrai
    // nom depuis le titre : "Renault Symbioz Esprit Alpine 2025" → "Symbioz"
    if (GENERIC_MODELS.includes(model.toLowerCase()) && make) {
      const title = ad.subject || ad.title || "";
      const extracted = extractModelFromTitle(title, make);
      if (extracted) model = extracted;
    }

    return {
      make,
      model,
      year: attrs["regdate"] || attrs["Année modèle"] || attrs["Année"] || attrs["year"] || "",
      fuel: attrs["fuel"] || attrs["Énergie"] || attrs["energie"] || "",
      gearbox: attrs["gearbox"] || attrs["Boîte de vitesse"] || attrs["Boite de vitesse"] || attrs["Transmission"] || "",
      horse_power: attrs["horse_power_din"] || attrs["Puissance DIN"] || "",
    };
  }

  /**
   * Extrait le nom du modele depuis le titre quand LBC met "Autres".
   * "Renault Symbioz Esprit Alpine 2025" → "Symbioz"
   */
  function extractModelFromTitle(title, make) {
    if (!title || !make) return null;
    let cleaned = title.trim();
    // Retirer la marque du debut
    if (cleaned.toLowerCase().startsWith(make.toLowerCase())) {
      cleaned = cleaned.slice(make.length).trim();
    }
    // Retirer l'annee (4 chiffres)
    cleaned = cleaned.replace(/\b(19|20)\d{2}\b/g, "").trim();
    // Premier mot significatif
    const noise = new Set([
      "neuf", "neuve", "occasion", "tbe", "garantie",
      "full", "options", "option", "pack", "premium", "edition",
      "limited", "sport", "line", "style", "business", "confort",
      "first", "life", "zen", "intens", "intense", "initiale",
      "paris", "riviera", "alpine", "esprit", "techno", "evolution",
      "iconic", "rs", "gt", "gtline", "gt-line",
    ]);
    for (const word of cleaned.split(/[\s,\-./()]+/)) {
      const w = word.trim();
      if (!w || noise.has(w.toLowerCase()) || /^\d+$/.test(w)) continue;
      return w;
    }
    return null;
  }

  /** Modeles generiques a ne pas inclure dans la recherche texte. */
  const GENERIC_MODELS = ["autres", "autre", "other", "divers"];

  /** Categories LBC exclues de la collecte de prix (pas des voitures). */
  const EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme", "utilitaires"];

  /**
   * Extrait l'annee depuis les attributs d'une annonce de recherche LBC.
   * Les ads de recherche ont un format d'attributs different.
   */
  function getAdYear(ad) {
    const attrs = ad.attributes || [];
    for (const a of attrs) {
      const key = (a.key || a.key_label || "").toLowerCase();
      if (key === "regdate" || key === "année modèle" || key === "année") {
        const val = String(a.value || a.value_label || "");
        const y = parseInt(val, 10);
        if (y >= 1990 && y <= 2030) return y;
      }
    }
    return null;
  }

  /**
   * Detecte si l'utilisateur est connecte sur LeBonCoin.
   * LBC affiche "Se connecter" dans le header si non connecte.
   */
  function isUserLoggedIn() {
    const header = document.querySelector("header");
    if (!header) return false;
    const text = header.textContent.toLowerCase();
    return !text.includes("se connecter") && !text.includes("s'identifier");
  }

  /**
   * Detecte un lien vers un rapport Autoviza sur la page LBC.
   * Certaines annonces offrent un rapport d'historique gratuit (valeur 25 EUR).
   * Le lien peut etre lazy-loaded par React, donc on retente plusieurs fois.
   * On cherche aussi dans __NEXT_DATA__ en fallback.
   * Retourne l'URL du rapport ou null si absent.
   */
  async function detectAutovizaUrl(nextData) {
    // 1. Chercher dans le DOM (plusieurs tentatives car lazy-load React)
    for (let attempt = 0; attempt < 4; attempt++) {
      // Lien direct vers autoviza.fr
      const directLink = document.querySelector('a[href*="autoviza.fr"]');
      if (directLink) return directLink.href;

      // Lien via redirect LBC (href contient autoviza en param)
      const redirectLink = document.querySelector('a[href*="autoviza"]');
      if (redirectLink) {
        const href = redirectLink.href;
        // Extraire l'URL autoviza d'un eventuel redirect
        const match = href.match(/(https?:\/\/[^\s&"]*autoviza\.fr[^\s&"]*)/);
        if (match) return match[1];
        return href;
      }

      // Bouton/lien avec texte "rapport d'historique" ou "rapport historique"
      const allLinks = document.querySelectorAll('a[href], button[data-href]');
      for (const el of allLinks) {
        const text = (el.textContent || "").toLowerCase();
        if ((text.includes("rapport") && text.includes("historique")) ||
            text.includes("autoviza")) {
          const href = el.href || el.dataset.href || "";
          if (href && href.includes("autoviza")) return href;
        }
      }

      if (attempt < 3) await sleep(800);
    }

    // 2. Fallback : chercher une URL autoviza dans __NEXT_DATA__
    if (nextData) {
      const json = JSON.stringify(nextData);
      const match = json.match(/(https?:\/\/[^\s"]*autoviza\.fr[^\s"]*)/);
      if (match) return match[1];
    }

    return null;
  }

  /**
   * Recupere le numero de telephone sur la page LBC.
   * 1. Verifie si un lien tel: existe deja (numero deja revele)
   * 2. Sinon clique "Voir le numero" (utilisateur connecte uniquement)
   * Retourne le numero (string) ou null si indisponible.
   */
  async function revealPhoneNumber() {
    // 1. Le numero est peut-etre deja visible (revele lors d'un precedent scan)
    const existingTelLinks = document.querySelectorAll('a[href^="tel:"]');
    for (const link of existingTelLinks) {
      const phone = link.href.replace("tel:", "").trim();
      if (phone && phone.length >= 10) return phone;
    }

    // 2. Sinon chercher le bouton "Voir le numero" et cliquer
    const candidates = document.querySelectorAll('button, a, [role="button"]');
    let phoneBtn = null;

    for (const el of candidates) {
      const text = (el.textContent || "").toLowerCase().trim();
      if (text.includes("voir le numéro") || text.includes("voir le numero")
          || text.includes("afficher le numéro") || text.includes("afficher le numero")) {
        phoneBtn = el;
        break;
      }
    }

    if (!phoneBtn) return null;

    phoneBtn.click();

    // 3. Attendre que le DOM se mette a jour
    for (let attempt = 0; attempt < 5; attempt++) {
      await sleep(500);

      const telLinks = document.querySelectorAll('a[href^="tel:"]');
      for (const link of telLinks) {
        const phone = link.href.replace("tel:", "").trim();
        if (phone && phone.length >= 10) return phone;
      }

      const container = phoneBtn.closest("div") || phoneBtn.parentElement;
      if (container) {
        const match = container.textContent.match(/(?:\+33|0)\s*[1-9](?:[\s.-]*\d{2}){4}/);
        if (match) return match[0].replace(/[\s.-]/g, "");
      }
    }

    return null;
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

    // Reveler le telephone SI l'utilisateur est connecte (sinon hint login dans L6/L9)
    const ad = nextData?.props?.pageProps?.ad;
    if (ad?.has_phone && isUserLoggedIn()) {
      const phone = await revealPhoneNumber();
      if (phone) {
        if (!ad.owner) ad.owner = {};
        ad.owner.phone = phone;
      }
    }

    // Collecte des prix AVANT l'analyse (silencieuse, ~1-2s)
    // Permet a L4/L5 d'avoir des donnees fraiches pour ce vehicule
    let collectInfo = { submitted: false };
    const vehicle = extractVehicleFromNextData(nextData);
    if (vehicle.make && vehicle.model && vehicle.year) {
      collectInfo = await maybeCollectMarketPrices(vehicle, nextData).catch(() => ({ submitted: false }));
    }

    async function fetchAnalysisOnce() {
      const response = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: window.location.href, next_data: nextData }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        if (errorData?.error === "NOT_A_VEHICLE") {
          showPopup(buildNotAVehiclePopup(errorData.message, errorData.data?.category));
          return null;
        }
        if (errorData?.error === "NOT_SUPPORTED") {
          showPopup(buildNotSupportedPopup(errorData.message, errorData.data?.category));
          return null;
        }
        const msg = errorData?.message || getRandomErrorMessage();
        showPopup(buildErrorPopup(msg));
        return null;
      }

      const result = await response.json();

      if (!result.success) {
        showPopup(buildErrorPopup(result.message || getRandomErrorMessage()));
        return null;
      }
      return result;
    }

    try {
      let result = await fetchAnalysisOnce();
      if (!result) return;

      // Si une collecte vient d'etre soumise pour le vehicule COURANT
      // et que L4 n'a pas de reference (skip pour n'importe quelle raison),
      // relancer apres un delai pour laisser le temps au commit en base.
      if (collectInfo.submitted && collectInfo.isCurrentVehicle) {
        const l4 = (result?.data?.filters || []).find((f) => f.filter_id === "L4");
        if (l4 && l4.status === "skip") {
          await sleep(2000);
          const retried = await fetchAnalysisOnce();
          if (retried) result = retried;
        }
      }

      // Detecter un eventuel rapport Autoviza gratuit sur la page
      // (async : retente plusieurs fois car le lien peut etre lazy-loaded)
      const autovizaUrl = await detectAutovizaUrl(nextData);

      showPopup(buildResultsPopup(result.data, { autovizaUrl }));
    } catch (err) {
      // Erreur silencieuse -- affichee dans la popup
      showPopup(buildErrorPopup(getRandomErrorMessage()));
    }
  }

  // ── Collecte crowdsourcee des prix du marche ────────────────────

  /** Mapping des regions LeBonCoin → codes rn_ (region + voisines).
   *  Les codes rn_ utilisent l'ancienne nomenclature regionale LBC (pre-2016).
   *  Avantage: rayon elargi = plus d'annonces comparables pour l'argus.
   *  Les cles correspondent aux region_name retournees par l'API LBC (avec accents). */
  const LBC_REGIONS = {
    "Île-de-France": "rn_12",
    "Auvergne-Rhône-Alpes": "rn_22",   // Rhone-Alpes + voisines
    "Provence-Alpes-Côte d'Azur": "rn_21",
    "Occitanie": "rn_16",              // Midi-Pyrenees + voisines
    "Nouvelle-Aquitaine": "rn_20",     // Poitou-Charentes + voisines
    "Hauts-de-France": "rn_17",        // Nord-Pas-de-Calais + voisines
    "Grand Est": "rn_8",               // Champagne-Ardenne + voisines
    "Bretagne": "rn_6",
    "Pays de la Loire": "rn_18",
    "Normandie": "rn_4",               // Basse-Normandie + voisines
    "Bourgogne-Franche-Comté": "rn_5", // Bourgogne + voisines
    "Centre-Val de Loire": "rn_7",
    "Corse": "rn_9",
  };

  /** Mapping fuel LBC : texte → code URL.
   *  Valeurs extraites de l'interface LBC (février 2026). */
  const LBC_FUEL_CODES = {
    "essence": 1,
    "diesel": 2,
    "electrique": 4,
    "électrique": 4,
    "hybride": 6,
  };

  /** Mapping gearbox LBC : texte → code URL.
   *  Valeurs extraites de l'interface LBC (février 2026). */
  const LBC_GEARBOX_CODES = {
    "manuelle": 1,
    "automatique": 2,
  };

  /** Calcule le range de puissance DIN pour la recherche LBC.
   *  Arrondi a la dizaine inferieure : 136ch → "130-max", 75ch → "70-max".
   *  Pas de max pour inclure les versions plus puissantes du meme modele. */
  function getHorsePowerRange(hp) {
    if (!hp || hp <= 0) return null;
    const minHp = Math.floor(hp / 10) * 10;
    return `${minHp}-max`;
  }

  /** Calcule le range de kilometrage pour la recherche LBC.
   *  Tranches serrees pour des comparables pertinents (meme profil d'usure). */
  function getMileageRange(km) {
    if (!km || km <= 0) return null;
    if (km <= 10000) return "min-20000";
    if (km <= 30000) return "min-50000";
    if (km <= 60000) return "20000-80000";
    if (km <= 120000) return "50000-150000";
    return "100000-max";
  }

  /** Cooldown entre deux collectes (anti-ban). */
  const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h

  /** Extrait la region depuis les donnees __NEXT_DATA__ (passees en parametre pour eviter les stale DOM). */
  function extractRegionFromNextData(nextData) {
    if (!nextData) return "";
    const loc = nextData?.props?.pageProps?.ad?.location;
    return loc?.region_name || loc?.region || "";
  }

  /** Extrait les donnees de localisation completes depuis __NEXT_DATA__.
   *  Retourne { city, zipcode, lat, lng, region } ou null si absent. */
  function extractLocationFromNextData(nextData) {
    const loc = nextData?.props?.pageProps?.ad?.location;
    if (!loc) return null;
    return {
      city: loc.city || "",
      zipcode: loc.zipcode || "",
      lat: loc.lat || null,
      lng: loc.lng || null,
      region: loc.region_name || loc.region || "",
    };
  }

  /** Rayon de recherche par defaut en metres (30 km). */
  const DEFAULT_SEARCH_RADIUS = 30000;

  /** Nombre minimum de prix valides pour constituer un argus. */
  const MIN_PRICES_FOR_ARGUS = 3;

  /** Fetch une page de recherche LBC et extrait les prix valides.
   *  Retourne un tableau de prix (entiers > 500) filtrés par annee. */
  async function fetchSearchPrices(searchUrl, targetYear, yearSpread) {
    const resp = await fetch(searchUrl, {
      credentials: "same-origin",
      headers: { "Accept": "text/html" },
    });
    const html = await resp.text();

    const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (!match) return [];

    const data = JSON.parse(match[1]);
    const ads = data?.props?.pageProps?.searchData?.ads
              || data?.props?.pageProps?.initialProps?.searchData?.ads
              || [];

    return ads
      .filter((ad) => {
        if (!ad.price || ad.price[0] <= 500) return false;
        if (targetYear >= 1990) {
          const adYear = getAdYear(ad);
          if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
        }
        return true;
      })
      .map((ad) => ad.price[0]);
  }

  /** Construit le parametre `locations=` pour une recherche LBC.
   *  Priorite : geolocalisation (ville + rayon) > region (rn_XX).
   *  Format geo LBC : City_PostalCode__Lat_Lng_5000_RadiusMeters */
  function buildLocationParam(location, radiusMeters) {
    if (!location) return "";
    const radius = radiusMeters || DEFAULT_SEARCH_RADIUS;
    // Geo-location : ville + rayon (plus precis, plus de resultats pertinents)
    if (location.lat && location.lng && location.city && location.zipcode) {
      return `${location.city}_${location.zipcode}__${location.lat}_${location.lng}_5000_${radius}`;
    }
    // Fallback : code region (rn_XX)
    return LBC_REGIONS[location.region] || "";
  }

  /** Extrait le kilometrage (en km) depuis les donnees __NEXT_DATA__. Retourne 0 si absent. */
  function extractMileageFromNextData(nextData) {
    const ad = nextData?.props?.pageProps?.ad;
    if (!ad) return 0;
    const attrs = (ad.attributes || []).reduce((acc, a) => {
      const key = a.key || a.key_label || a.label || a.name;
      const val = a.value || a.value_label || a.text || a.value_text;
      if (key) acc[key] = val;
      return acc;
    }, {});
    const raw = attrs["mileage"] || attrs["Kilométrage"] || attrs["kilometrage"] || "0";
    return parseInt(String(raw).replace(/\s/g, ""), 10) || 0;
  }

  /**
   * Collecte intelligente : demande au serveur quel vehicule a besoin de
   * mise a jour, puis collecte les prix sur LeBonCoin.
   *
   * Chaque user travaille pour la communaute :
   * - Le serveur assigne le vehicule le plus prioritaire a collecter
   * - Le vehicule courant est TOUJOURS collecte si le serveur le demande
   *   (la fraicheur 7j cote serveur protege des abus)
   * - Cooldown 24h (localStorage) uniquement pour les collectes d'AUTRES
   *   vehicules (anti-ban LBC)
   *
   * Appelee AVANT l'analyse pour que L4/L5 aient des donnees fraiches.
   */
  async function maybeCollectMarketPrices(vehicle, nextData) {
    const { make, model, year, fuel, gearbox, horse_power } = vehicle;
    if (!make || !model || !year) return { submitted: false };

    // Ne pas collecter de prix pour les categories non-voiture (motos, etc.)
    const urlMatch = window.location.href.match(/\/ad\/([a-z_]+)\//);
    const urlCategory = urlMatch ? urlMatch[1] : null;
    if (urlCategory && EXCLUDED_CATEGORIES.includes(urlCategory)) return { submitted: false };

    // Extraire le kilometrage depuis le nextData pour le range de recherche
    const mileageKm = extractMileageFromNextData(nextData);

    // 1. Extraire la localisation depuis le nextData (pas le DOM qui peut etre stale)
    const location = extractLocationFromNextData(nextData);
    const region = location?.region || "";
    if (!region) return { submitted: false };

    // 2. Demander au serveur quel vehicule collecter
    const jobUrl = API_URL.replace("/analyze", "/market-prices/next-job")
      + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`;

    let jobResp;
    try {
      jobResp = await fetch(jobUrl).then((r) => r.json());
    } catch {
      return { submitted: false }; // serveur injoignable -- silencieux
    }
    if (!jobResp?.data?.collect) return { submitted: false };

    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;

    // 3. Cooldown 24h -- uniquement pour les collectes d'AUTRES vehicules
    //    Le vehicule courant est toujours collecte (le serveur gere la fraicheur)
    const isCurrentVehicle =
      target.make.toLowerCase() === make.toLowerCase() &&
      target.model.toLowerCase() === model.toLowerCase();

    if (!isCurrentVehicle) {
      const lastCollect = parseInt(localStorage.getItem("copilot_last_collect") || "0", 10);
      if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) return { submitted: false };
    }

    // 4. Construire l'URL de recherche LeBonCoin (filtres structures)
    const targetYear = parseInt(target.year, 10) || 0;
    const modelIsGeneric = GENERIC_MODELS.includes((target.model || "").toLowerCase());

    // URL de base : marque/modele + filtres vehicule (invariants entre strategies)
    const brandUpper = target.make.toUpperCase();
    let baseUrl = "https://www.leboncoin.fr/recherche?category=2";
    if (modelIsGeneric) {
      baseUrl += `&text=${encodeURIComponent(target.make)}`;
    } else {
      const modelUpper = `${brandUpper}_${target.model.toUpperCase()}`;
      baseUrl += `&u_car_brand=${encodeURIComponent(brandUpper)}`;
      baseUrl += `&u_car_model=${encodeURIComponent(modelUpper)}`;
    }

    // Filtres vehicule (fuel, km, gearbox, puissance) -- invariants
    const targetFuel = (fuel || "").toLowerCase();
    const fuelCode = LBC_FUEL_CODES[targetFuel];
    if (fuelCode) baseUrl += `&fuel=${fuelCode}`;
    if (mileageKm > 0) {
      const mileageRange = getMileageRange(mileageKm);
      if (mileageRange) baseUrl += `&mileage=${mileageRange}`;
    }
    const gearboxCode = LBC_GEARBOX_CODES[(gearbox || "").toLowerCase()];
    if (gearboxCode) baseUrl += `&gearbox=${gearboxCode}`;
    const hp = parseInt(horse_power, 10) || 0;
    const hpRange = getHorsePowerRange(hp);
    if (hpRange) baseUrl += `&horse_power_din=${hpRange}`;

    // 5. Escalade progressive : precision d'abord, puis on elargit
    //    Strategie 1 : geo-location (ville + 30 km) + annee ±1
    //    Strategie 2 : region + voisines (rn_XX) + annee ±1
    //    Strategie 3 : region + voisines (rn_XX) + annee ±2
    const hasGeo = location?.lat && location?.lng && location?.city && location?.zipcode;
    const geoParam = hasGeo ? buildLocationParam(location, DEFAULT_SEARCH_RADIUS) : "";
    const regionParam = LBC_REGIONS[region] || "";

    const strategies = [];
    if (geoParam) strategies.push({ loc: geoParam, yearSpread: 1 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 1 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 2 });

    let submitted = false;
    let prices = [];
    try {
      for (const strategy of strategies) {
        let searchUrl = baseUrl;
        if (strategy.loc) searchUrl += `&locations=${strategy.loc}`;
        if (targetYear >= 1990) {
          searchUrl += `&regdate=${targetYear - strategy.yearSpread}-${targetYear + strategy.yearSpread}`;
        }

        prices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread);
        if (prices.length >= MIN_PRICES_FOR_ARGUS) break;
      }

      if (prices.length >= MIN_PRICES_FOR_ARGUS) {
        const marketUrl = API_URL.replace("/analyze", "/market-prices");
        const marketResp = await fetch(marketUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            make: target.make,
            model: target.model,
            year: parseInt(target.year, 10),
            region: targetRegion,
            prices: prices,
            category: urlCategory,
            fuel: fuelCode ? targetFuel : null,
          }),
        });
        submitted = marketResp.ok;
      }
    } catch {
      // Silencieux -- ne pas perturber l'experience utilisateur
    }

    // 5. Sauvegarder le timestamp (meme si pas assez de prix)
    localStorage.setItem("copilot_last_collect", String(Date.now()));
    return { submitted, isCurrentVehicle };
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

  // ── Test exports (Node.js / Vitest uniquement) ──────────────────
  // En browser, typeof module === 'undefined' → ce bloc est inerte.
  // En Node/jsdom, init() sort immediatement (URL != leboncoin).
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      extractVehicleFromNextData,
      extractRegionFromNextData,
      extractLocationFromNextData,
      buildLocationParam,
      DEFAULT_SEARCH_RADIUS,
      MIN_PRICES_FOR_ARGUS,
      fetchSearchPrices,
      extractMileageFromNextData,
      isUserLoggedIn,
      revealPhoneNumber,
      isStaleData,
      isAdPage,
      scoreColor,
      statusColor,
      statusIcon,
      filterLabel,
      maybeCollectMarketPrices,
      LBC_REGIONS,
      LBC_FUEL_CODES,
      LBC_GEARBOX_CODES,
      getMileageRange,
      getHorsePowerRange,
      COLLECT_COOLDOWN_MS,
      SIMULATED_FILTERS,
      API_URL,
    };
  }
})();
