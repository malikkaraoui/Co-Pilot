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
  let lastScanId = null;
  // Messages de dégradation UX (humour automobile)
  const ERROR_MESSAGES = [
    "Oh mince, on a crevé ! Réessayez dans un instant.",
    "Le moteur a calé... Notre serveur fait une pause, retentez !",
    "Panne sèche ! Impossible de joindre le serveur.",
    "Embrayage patiné... L'analyse n'a pas pu démarrer.",
    "Vidange en cours ! Le serveur revient dans un instant.",
  ];

  /** Retourne true si le runtime extension Chrome est disponible. */
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

  /** Indique si l'URL cible est le backend local (mixed-content si fetch direct). */
  function isLocalBackendUrl(url) {
    return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
  }

  /** Classe les erreurs de teardown MV3 comme "benignes" (extension reloaded/unloaded). */
  function isBenignRuntimeTeardownError(err) {
    const msg = String(err?.message || err || "").toLowerCase();
    return msg.includes("extension context invalidated")
      || msg.includes("runtime_unavailable_for_local_backend")
      || msg.includes("receiving end does not exist");
  }

  // ── Proxy backend (mixed-content fix) ─────────────────────────

  /** Fetch vers le backend Co-Pilot via le background service worker.
   *  Chrome MV3 bloque les requetes HTTP depuis une page HTTPS.
   *  Fallback sur fetch() direct si le runtime n'est pas disponible.
   *  Retourne un objet Response-like (ok, status, json(), text()). */
  async function backendFetch(url, options = {}) {
    const isLocalBackend = isLocalBackendUrl(url);

    // Fallback : pas de runtime Chrome (tests, Safari, …)
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
              // Proxy indisponible : fallback fetch direct seulement hors localhost HTTP.
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
      L10: "Ancienneté annonce",
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

  // ── Radar chart SVG (vue en araignee) ─────────────────────────

  /** Labels courts pour le radar (sans prefixe L1, L2...) */
  const RADAR_SHORT_LABELS = {
    L1: "Donn\u00E9es", L2: "Mod\u00E8le", L3: "Km", L4: "Prix",
    L5: "Stats", L6: "T\u00E9l\u00E9phone", L7: "SIRET", L8: "Import",
    L9: "\u00C9val", L10: "Anciennet\u00E9",
  };

  /**
   * Genere le SVG du radar chart (vue en araignee).
   * @param {Array} filters - Liste des filtres {filter_id, score, status}.
   * @param {number} overallScore - Score global 0-100.
   * @returns {string} Le markup SVG.
   */
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

    // Grid rings
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

    // Axis lines
    let axesSVG = "";
    for (let i = 0; i < n; i++) {
      const p = pt(i, R);
      axesSVG += `<line x1="${cx}" y1="${cy}" x2="${p.x}" y2="${p.y}" class="copilot-radar-axis-line"/>`;
    }

    // Data polygon
    const dataPts = [];
    for (let i = 0; i < n; i++) {
      const p = pt(i, R * filters[i].score);
      dataPts.push(`${p.x},${p.y}`);
    }
    const dataStr = dataPts.join(" ");

    // Dots + labels
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

      // Label
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

        // L4 : barre de prix Argus (remplace les details techniques)
        const isL4 = f.filter_id === "L4";
        const priceBarHTML = isL4 && f.details ? buildPriceBarHTML(f.details) : "";
        const detailsHTML = isL4 ? "" : (f.details ? buildDetailsHTML(f.details) : "");

        // Badges simulees (L4 n'en a plus — le verdict parle de lui-meme)
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
    precision: "Précision",
    lookup_make: "Lookup marque",
    lookup_model: "Lookup modèle",
    lookup_year: "Lookup année",
    lookup_region_key: "Lookup région (clé)",
    lookup_fuel_input: "Lookup énergie (brute)",
    lookup_fuel_key: "Lookup énergie (clé)",
    lookup_min_samples: "Seuil min annonces",
  };

  /** Labels de precision (echelle 1-5). */
  const PRECISION_LABELS = {
    5: "Tres precis",
    4: "Precis",
    3: "Correct",
    2: "Approximatif",
    1: "Estimatif",
  };

  /** Formate la precision en etoiles : ★★★★☆ 4/5 - Precis */
  function formatPrecisionStars(n) {
    const filled = "\u2605".repeat(n);        // ★
    const empty = "\u2606".repeat(5 - n);     // ☆
    const label = PRECISION_LABELS[n] || "";
    return `${filled}${empty} ${n}/5 – ${label}`;
  }

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

  /** Construit la barre de prix Argus pour le filtre L4. */
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

    // Determine verdict class + text
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

    // Scale for bar positioning
    const statusColors = {
      "verdict-below": "#16a34a",
      "verdict-fair": "#16a34a",
      "verdict-above-warning": "#ea580c",
      "verdict-above-fail": "#dc2626",
    };
    const fillOpacities = {
      "verdict-below": "rgba(22,163,74,0.15)",
      "verdict-fair": "rgba(22,163,74,0.15)",
      "verdict-above-warning": "rgba(234,88,12,0.2)",
      "verdict-above-fail": "rgba(220,38,38,0.2)",
    };
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
        // Rendu special etoiles pour la precision
        const val = k === "precision" && typeof v === "number"
          ? formatPrecisionStars(v)
          : formatDetailValue(v);
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

  /**
   * Construit le bandeau "Rediger un email" dans la popup.
   */
  function buildEmailBanner() {
    return `
      <div class="copilot-email-banner" id="copilot-email-section">
        <button class="copilot-email-btn" id="copilot-email-btn">
          &#x2709; Rédiger un email au vendeur
        </button>
        <div class="copilot-email-result" id="copilot-email-result" style="display:none;">
          <textarea class="copilot-email-textarea" id="copilot-email-text" rows="8" readonly></textarea>
          <div class="copilot-email-actions">
            <button class="copilot-email-copy" id="copilot-email-copy">
              &#x1F4CB; Copier
            </button>
            <span class="copilot-email-copied" id="copilot-email-copied" style="display:none;">
              Copié !
            </span>
          </div>
        </div>
        <div class="copilot-email-loading" id="copilot-email-loading" style="display:none;">
          <span class="copilot-mini-spinner"></span> Génération en cours...
        </div>
        <div class="copilot-email-error" id="copilot-email-error" style="display:none;"></div>
      </div>
    `;
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

    // Bouton email vendeur
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
          const resp = await backendFetch(emailUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ scan_id: lastScanId }),
          });
          const data = await resp.json();

          if (data.success) {
            textArea.value = data.data.generated_text;
            result.style.display = "block";
          } else {
            errorDiv.textContent = data.error || "Erreur de génération";
            errorDiv.style.display = "block";
            emailBtn.style.display = "block";
          }
        } catch (err) {
          errorDiv.textContent = "Service indisponible";
          errorDiv.style.display = "block";
          emailBtn.style.display = "block";
        }
        loading.style.display = "none";
      });
    }

    // Bouton copier email
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

  // ── Progress Tracker (checklist live) ────────────────────────

  /**
   * Systeme de progression en temps reel.
   * Remplace le spinner par une checklist animee.
   *
   * Toutes les valeurs inserees dans le DOM passent par escapeHTML()
   * ou textContent pour prevenir les injections XSS.
   */
  function createProgressTracker() {

    /** Icone HTML selon le statut (contenu statique, pas de donnee utilisateur) */
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

    /** Met a jour le statut et le detail d'une etape */
    function update(stepId, status, detail) {
      const el = document.getElementById("copilot-step-" + stepId);
      if (!el) return;
      el.setAttribute("data-status", status);

      const iconEl = el.querySelector(".copilot-step-icon");
      if (iconEl) {
        iconEl.className = "copilot-step-icon " + status;
        if (status === "running") {
          iconEl.innerHTML = '<div class="copilot-mini-spinner"></div>';
        } else {
          iconEl.textContent = stepIconHTML(status);
        }
      }

      if (detail !== undefined) {
        let detailEl = el.querySelector(".copilot-step-detail");
        if (!detailEl) {
          detailEl = document.createElement("div");
          detailEl.className = "copilot-step-detail";
          el.querySelector(".copilot-step-text").appendChild(detailEl);
        }
        detailEl.textContent = detail;
      }

      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    /** Ajoute une sous-etape (ligne indentee sous un step parent) */
    function addSubStep(parentId, text, status, detail) {
      const parentEl = document.getElementById("copilot-step-" + parentId);
      if (!parentEl) return;

      let container = parentEl.querySelector(".copilot-substeps");
      if (!container) {
        container = document.createElement("div");
        container.className = "copilot-substeps";
        parentEl.appendChild(container);
      }

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

    /** Affiche les resultats des 10 filtres dans la zone dediee */
    function showFilters(filters) {
      const container = document.getElementById("copilot-progress-filters");
      if (!container || !filters) return;

      filters.forEach(function (f) {
        const color = statusColor(f.status);
        const icon = statusIcon(f.status);
        const label = filterLabel(f.filter_id);
        const scoreText = f.status === "skip" ? "skip" : Math.round(f.score * 100) + "%";

        // Ligne principale du filtre
        const filterDiv = document.createElement("div");
        filterDiv.className = "copilot-progress-filter";

        const iconSpan = document.createElement("span");
        iconSpan.className = "copilot-progress-filter-icon";
        iconSpan.style.color = color;
        iconSpan.textContent = icon;
        filterDiv.appendChild(iconSpan);

        const idSpan = document.createElement("span");
        idSpan.className = "copilot-progress-filter-id";
        idSpan.textContent = f.filter_id;
        filterDiv.appendChild(idSpan);

        const labelSpan = document.createElement("span");
        labelSpan.className = "copilot-progress-filter-label";
        labelSpan.textContent = label;
        filterDiv.appendChild(labelSpan);

        const scoreSpan = document.createElement("span");
        scoreSpan.className = "copilot-progress-filter-score";
        scoreSpan.style.color = color;
        scoreSpan.textContent = scoreText;
        filterDiv.appendChild(scoreSpan);

        container.appendChild(filterDiv);

        // Message du filtre
        const msgDiv = document.createElement("div");
        msgDiv.className = "copilot-progress-filter-msg";
        msgDiv.textContent = f.message;
        container.appendChild(msgDiv);

        // Details cascade L4
        if (f.filter_id === "L4" && f.details) {
          appendCascadeDetails(container, f.details);
        }
      });

      container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    /** Ajoute les details de cascade L4 (source, tiers essayes) */
    function appendCascadeDetails(container, details) {
      var lines = [];
      if (details.source === "marche_leboncoin") {
        lines.push("Source : march\u00e9 LBC (" + (details.sample_count || "?") + " annonces" + (details.precision ? ", pr\u00e9cision " + details.precision : "") + ")");
      } else if (details.source === "argus_seed") {
        lines.push("Source : Argus (donn\u00e9es seed)");
      }
      if (details.cascade_tried) {
        details.cascade_tried.forEach(function (tier) {
          var result = details["cascade_" + tier + "_result"] || "non essay\u00e9";
          var tierLabel = tier === "market_price" ? "March\u00e9 LBC" : "Argus Seed";
          var tierIcon = result === "found" ? "\u2713" : result === "insufficient" ? "\u26A0" : "\u2014";
          lines.push(tierIcon + " " + tierLabel + " : " + result);
        });
      }
      lines.forEach(function (line) {
        var div = document.createElement("div");
        div.className = "copilot-cascade-detail";
        div.textContent = line;
        container.appendChild(div);
      });
    }

    /** Affiche le score final avec jauge */
    function showScore(score, verdict) {
      const container = document.getElementById("copilot-progress-score");
      if (!container) return;

      const color = scoreColor(score);

      const labelDiv = document.createElement("div");
      labelDiv.className = "copilot-progress-score-label";
      labelDiv.textContent = "Score global";
      container.appendChild(labelDiv);

      const valueDiv = document.createElement("div");
      valueDiv.className = "copilot-progress-score-value";
      valueDiv.style.color = color;
      valueDiv.textContent = String(score);
      container.appendChild(valueDiv);

      const verdictDiv = document.createElement("div");
      verdictDiv.className = "copilot-progress-score-verdict";
      verdictDiv.style.color = color;
      verdictDiv.textContent = verdict;
      container.appendChild(verdictDiv);

      container.style.display = "block";
      container.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    return { update: update, addSubStep: addSubStep, showFilters: showFilters, showScore: showScore };
  }

  /** Affiche la popup de progression (remplace le spinner). */
  function showProgress() {
    removePopup();
    /* Structure statique : aucune donnee utilisateur injectee ici.
       Les valeurs dynamiques sont ajoutees via textContent par le tracker. */
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
      '      <div class="copilot-step" id="copilot-step-extract" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Extraction des donn\u00e9es de l\'annonce</div>',
      '      </div>',
      '      <div class="copilot-step" id="copilot-step-phone" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">R\u00e9v\u00e9lation du num\u00e9ro de t\u00e9l\u00e9phone</div>',
      '      </div>',
      '    </div>',
      '    <div class="copilot-progress-phase">',
      '      <div class="copilot-progress-phase-title">2. Collecte prix march\u00e9</div>',
      '      <div class="copilot-step" id="copilot-step-job" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Demande au serveur : quel v\u00e9hicule collecter ?</div>',
      '      </div>',
      '      <div class="copilot-step" id="copilot-step-collect" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Collecte des prix (cascade LeBonCoin)</div>',
      '      </div>',
      '      <div class="copilot-step" id="copilot-step-submit" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Envoi des prix au serveur</div>',
      '      </div>',
      '      <div class="copilot-step" id="copilot-step-bonus" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Collecte bonus multi-r\u00e9gion</div>',
      '      </div>',
      '    </div>',
      '    <div class="copilot-progress-phase">',
      '      <div class="copilot-progress-phase-title">3. Analyse serveur</div>',
      '      <div class="copilot-step" id="copilot-step-analyze" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">Analyse des 10 filtres (L1 \u2013 L10)</div>',
      '      </div>',
      '      <div id="copilot-progress-filters" class="copilot-progress-filters"></div>',
      '      <div class="copilot-step" id="copilot-step-autoviza" data-status="pending">',
      '        <span class="copilot-step-icon pending">\u25CB</span>',
      '        <div class="copilot-step-text">D\u00e9tection rapport Autoviza</div>',
      '      </div>',
      '    </div>',
      '    <hr class="copilot-progress-separator">',
      '    <div id="copilot-progress-score" class="copilot-progress-score" style="display:none"></div>',
      '    <div style="text-align:center; padding: 12px 0;">',
      '      <button class="copilot-btn copilot-btn-retry" id="copilot-progress-details-btn" style="display:none">',
      '        Voir l\'analyse compl\u00e8te',
      '      </button>',
      '    </div>',
      '  </div>',
      '  <div class="copilot-popup-footer">',
      '    <p>Co-Pilot v1.0 &middot; Analyse en temps r\u00e9el</p>',
      '  </div>',
      '</div>',
    ].join("\n");
    showPopup(html);
    return createProgressTracker();
  }

  /**
   * Extrait les infos vehicule (make, model, year) depuis __NEXT_DATA__
   * pour pouvoir lancer la collecte AVANT l'analyse.
   */
  /**
   * Extrait les tokens u_car_brand / u_car_model depuis le DOM de la page LBC.
   *
   * Chaque annonce a un lien "Voir d'autres annonces <modele>" dont le href
   * contient les tokens exacts : /c/voitures/u_car_brand:BMW+u_car_model:BMW_Série%203
   * Ces tokens sont la source de verite pour les recherches LBC (accents inclus).
   * __NEXT_DATA__ peut renvoyer "Serie 3" (sans accent) alors que LBC attend "Série 3".
   */
  function extractLbcTokensFromDom() {
    const result = { brandToken: null, modelToken: null };
    try {
      const link = document.querySelector('a[href*="u_car_model"]');
      if (!link) return result;
      const url = new URL(link.href, location.origin);
      // Le pathname est du type /c/voitures/u_car_brand:BMW+u_car_model:BMW_Série%203
      const path = decodeURIComponent(url.pathname + url.search + url.hash);
      const brandMatch = path.match(/u_car_brand:([^+&\s]+)/);
      const modelMatch = path.match(/u_car_model:([^+&\s]+)/);
      if (brandMatch) result.brandToken = brandMatch[1];
      if (modelMatch) result.modelToken = modelMatch[1];
    } catch (e) {
      console.warn("[CoPilot] extractLbcTokensFromDom error:", e);
    }
    return result;
  }

  function extractVehicleFromNextData(nextData) {
    const ad = nextData?.props?.pageProps?.ad;
    if (!ad) return {};

    const attrs = (ad.attributes || []).reduce((acc, a) => {
      const key = a.key || a.key_label || a.label || a.name;
      // Preferer value_label (texte lisible, ex: "Essence") a value (code LBC, ex: "1")
      // Coherent avec le serveur (extraction.py _normalize_attributes)
      const val = a.value_label || a.value || a.text || a.value_text;
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

    // Extraire les tokens LBC depuis le DOM (source de verite pour les URLs de recherche).
    // __NEXT_DATA__ peut avoir "Serie 3" sans accent mais LBC attend "Série 3" dans l'URL.
    const domTokens = extractLbcTokensFromDom();

    return {
      make,
      model,
      year: attrs["regdate"] || attrs["Année modèle"] || attrs["Année"] || attrs["year"] || "",
      fuel: attrs["fuel"] || attrs["Énergie"] || attrs["energie"] || "",
      gearbox: attrs["gearbox"] || attrs["Boîte de vitesse"] || attrs["Boite de vitesse"] || attrs["Transmission"] || "",
      horse_power: attrs["horse_power_din"] || attrs["Puissance DIN"] || "",
      // Tokens LBC pour les URLs de recherche (avec accents corrects)
      site_brand_token: domTokens.brandToken,
      site_model_token: domTokens.modelToken,
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
  const EXCLUDED_CATEGORIES = ["motos", "equipement_moto", "caravaning", "nautisme"];

  /** Alias marque internes -> token marque attendu par LBC dans u_car_brand. */
  const LBC_BRAND_ALIASES = {
    MERCEDES: "MERCEDES-BENZ",
  };

  /** Normalise la marque pour l'URL LBC (u_car_brand). */
  function toLbcBrandToken(make) {
    const upper = String(make || "").trim().toUpperCase();
    return LBC_BRAND_ALIASES[upper] || upper;
  }

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
    const progress = showProgress();

    // ── Phase 1 : Extraction ──────────────────────────────────
    progress.update("extract", "running");
    const nextData = await extractNextData();
    if (!nextData) {
      console.warn("[CoPilot] extractNextData() → null. Pas de __NEXT_DATA__ trouvé.");
      progress.update("extract", "error", "Impossible de lire les données");
      showPopup(buildErrorPopup("Impossible de lire les données de cette page. Vérifiez que vous êtes sur une annonce Leboncoin."));
      return;
    }
    const adId = nextData?.props?.pageProps?.ad?.list_id || "";
    progress.update("extract", "done", "ID annonce : " + adId);
    console.log("[CoPilot] nextData OK, ad id:", adId);

    // Afficher le vehicule dans le header
    const vehicle = extractVehicleFromNextData(nextData);
    const vehicleLabel = document.getElementById("copilot-progress-vehicle");
    if (vehicleLabel && vehicle.make) {
      vehicleLabel.textContent = [vehicle.make, vehicle.model, vehicle.year].filter(Boolean).join(" ");
    }

    // Telephone
    const ad = nextData?.props?.pageProps?.ad;
    if (ad?.has_phone && isUserLoggedIn()) {
      progress.update("phone", "running");
      const phone = await revealPhoneNumber();
      if (phone) {
        if (!ad.owner) ad.owner = {};
        ad.owner.phone = phone;
        progress.update("phone", "done", phone.replace(/(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/, "$1 $2 $3 $4 $5"));
      } else {
        progress.update("phone", "warning", "Numéro non récupéré");
      }
    } else if (ad?.has_phone) {
      progress.update("phone", "skip", "Non connecté sur LeBonCoin");
    } else {
      progress.update("phone", "skip", "Pas de téléphone sur cette annonce");
    }

    // ── Phase 2 : Collecte prix marche ────────────────────────
    let collectInfo = { submitted: false };
    console.log("[CoPilot] vehicle extrait:", JSON.stringify(vehicle));
    if (vehicle.make && vehicle.model && vehicle.year) {
      collectInfo = await maybeCollectMarketPrices(vehicle, nextData, progress).catch((err) => {
        console.error("[CoPilot] maybeCollectMarketPrices erreur:", err);
        progress.update("job", "error", "Erreur collecte");
        return { submitted: false };
      });
      console.log("[CoPilot] collectInfo:", JSON.stringify(collectInfo));
    } else {
      console.warn("[CoPilot] vehicle incomplet, pas de collecte:", vehicle);
      progress.update("job", "skip", "Véhicule incomplet (marque/modèle/année manquant)");
      progress.update("collect", "skip");
      progress.update("submit", "skip");
      progress.update("bonus", "skip");
    }

    // ── Phase 3 : Analyse serveur ─────────────────────────────
    progress.update("analyze", "running");

    async function fetchAnalysisOnce() {
      console.log("[CoPilot] fetchAnalysisOnce → POST", API_URL);
      const response = await backendFetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: window.location.href, next_data: nextData }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        console.warn("[CoPilot] API reponse NOT OK:", response.status, errorData);
        if (errorData?.error === "NOT_A_VEHICLE") {
          progress.update("analyze", "skip", "Pas une voiture");
          showPopup(buildNotAVehiclePopup(errorData.message, errorData.data?.category));
          return null;
        }
        if (errorData?.error === "NOT_SUPPORTED") {
          progress.update("analyze", "skip", errorData.message);
          showPopup(buildNotSupportedPopup(errorData.message, errorData.data?.category));
          return null;
        }
        const msg = errorData?.message || getRandomErrorMessage();
        progress.update("analyze", "error", msg);
        showPopup(buildErrorPopup(msg));
        return null;
      }

      const result = await response.json();

      if (!result.success) {
        console.warn("[CoPilot] API success=false:", result);
        progress.update("analyze", "error", result.message || "Erreur serveur");
        showPopup(buildErrorPopup(result.message || getRandomErrorMessage()));
        return null;
      }

      // Log L4/L5 pour diagnostiquer l'argus
      const filters = result?.data?.filters || [];
      const l4 = filters.find((f) => f.filter_id === "L4");
      const l5 = filters.find((f) => f.filter_id === "L5");
      console.log("[CoPilot] L4:", l4 ? l4.status + " | " + l4.message : "absent", l4?.details || {});
      console.log("[CoPilot] L5:", l5 ? l5.status + " | " + l5.message : "absent", l5?.details || {});

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
          console.log("[CoPilot] L4=skip + collecte soumise → retry dans 2s...");
          progress.update("analyze", "running", "Retry L4 (données fraîches en cours d'écriture)...");
          await sleep(2000);
          const retried = await fetchAnalysisOnce();
          if (retried) result = retried;
        }
      }

      // Stocker le scan_id pour la generation d'email
      lastScanId = result.data.scan_id || null;

      // Afficher les resultats des filtres dans la checklist
      progress.update("analyze", "done", (result.data.filters || []).length + " filtres analysés");
      progress.showFilters(result.data.filters || []);

      // Score final
      const score = result.data.score;
      const verdict = score >= 70 ? "Annonce fiable" : score >= 40 ? "Points d'attention" : "Vigilance requise";
      progress.showScore(score, verdict);

      // Detecter un eventuel rapport Autoviza gratuit sur la page
      progress.update("autoviza", "running");
      const autovizaUrl = await detectAutovizaUrl(nextData);
      if (autovizaUrl) {
        progress.update("autoviza", "done", "Rapport gratuit trouvé");
      } else {
        progress.update("autoviza", "skip", "Aucun rapport disponible");
      }

      // Bouton "Voir l'analyse complète" pour basculer vers la popup detaillee
      const detailsBtn = document.getElementById("copilot-progress-details-btn");
      if (detailsBtn) {
        detailsBtn.style.display = "inline-block";
        detailsBtn.addEventListener("click", function () {
          showPopup(buildResultsPopup(result.data, { autovizaUrl: autovizaUrl }));
        });
      }
    } catch (err) {
      progress.update("analyze", "error", "Erreur inattendue");
      showPopup(buildErrorPopup(getRandomErrorMessage()));
    }
  }

  // ── Collecte crowdsourcee des prix du marche ────────────────────

  /** Mapping des regions LeBonCoin → codes rn_ (region + voisines).
   *  Les codes rn_ utilisent l'ancienne nomenclature regionale LBC (pre-2016).
   *  Inclut AUSSI les anciens noms de region (LBC retourne parfois les anciens
   *  noms dans region_name, ex: "Nord-Pas-de-Calais" au lieu de "Hauts-de-France"). */
  const LBC_REGIONS = {
    // Regions post-2016
    "Île-de-France": "rn_12",
    "Auvergne-Rhône-Alpes": "rn_22",
    "Provence-Alpes-Côte d'Azur": "rn_21",
    "Occitanie": "rn_16",
    "Nouvelle-Aquitaine": "rn_20",
    "Hauts-de-France": "rn_17",
    "Grand Est": "rn_8",
    "Bretagne": "rn_6",
    "Pays de la Loire": "rn_18",
    "Normandie": "rn_4",
    "Bourgogne-Franche-Comté": "rn_5",
    "Centre-Val de Loire": "rn_7",
    "Corse": "rn_9",
    // Anciennes regions (pre-2016) -- LBC retourne parfois ces noms
    "Nord-Pas-de-Calais": "rn_17",
    "Picardie": "rn_17",
    "Rhône-Alpes": "rn_22",
    "Auvergne": "rn_22",
    "Midi-Pyrénées": "rn_16",
    "Languedoc-Roussillon": "rn_16",
    "Aquitaine": "rn_20",
    "Poitou-Charentes": "rn_20",
    "Limousin": "rn_20",
    "Alsace": "rn_8",
    "Lorraine": "rn_8",
    "Champagne-Ardenne": "rn_8",
    "Basse-Normandie": "rn_4",
    "Haute-Normandie": "rn_4",
    "Bourgogne": "rn_5",
    "Franche-Comté": "rn_5",
  };

  /** Mapping fuel LBC : texte → code URL.
   *  Valeurs extraites de l'interface LBC (février 2026). */
  const LBC_FUEL_CODES = {
    "essence": 1,
    "diesel": 2,
    "electrique": 4,
    "électrique": 4,
    "hybride": 6,
    "hybride rechargeable": 7,
    "gpl": 3,
    "électrique & essence": 6,
    "electrique & essence": 6,
    "électrique & diesel": 6,
    "electrique & diesel": 6,
  };

  /** Mapping gearbox LBC : texte → code URL.
   *  Valeurs extraites de l'interface LBC (février 2026). */
  const LBC_GEARBOX_CODES = {
    "manuelle": 1,
    "automatique": 2,
  };

  /** Calcule le range de puissance DIN pour la recherche LBC.
   *  Tranches serrees par segment pour des comparables pertinents
   *  (overlap volontaire entre segments pour maximiser les resultats). */
  function getHorsePowerRange(hp) {
    if (!hp || hp <= 0) return null;
    if (hp < 80)  return "min-90";
    if (hp < 110) return "70-120";
    if (hp < 140) return "100-150";
    if (hp < 180) return "130-190";
    if (hp < 250) return "170-260";
    if (hp < 350) return "240-360";
    return "340-max";
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

  /** Nombre minimum de prix valides pour constituer un argus fiable.
   *  En-dessous de 20, l'IQR est trop instable pour etre significatif. */
  const MIN_PRICES_FOR_ARGUS = 20;

  /** Extrait les details d'une annonce LBC (prix, annee, km, fuel).
   *  Utilise pour la transparence de l'argus. */
  function getAdDetails(ad) {
    const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
    const parsedPrice = typeof rawPrice === "number"
      ? rawPrice
      : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
    const attrs = Array.isArray(ad?.attributes) ? ad.attributes : [];
    const details = { price: Number.isFinite(parsedPrice) ? parsedPrice : 0 };
    for (const a of attrs) {
      if (!a || typeof a !== "object") continue;
      const key = (a.key || a.key_label || "").toLowerCase();
      if (key === "regdate" || key === "année modèle" || key === "année") {
        details.year = parseInt(a.value || a.value_label, 10) || null;
      } else if (key === "mileage" || key === "kilométrage" || key === "kilometrage") {
        details.km = parseInt(String(a.value || a.value_label || "0").replace(/\s/g, ""), 10) || null;
      } else if (key === "fuel" || key === "énergie" || key === "energie") {
        details.fuel = a.value_label || a.value || null;
      } else if (key === "gearbox" || key === "boîte de vitesse" || key === "boite de vitesse") {
        details.gearbox = a.value_label || a.value || null;
      } else if (key === "horse_power_din" || key === "puissance din") {
        details.horse_power = parseInt(String(a.value || a.value_label || "0"), 10) || null;
      }
    }
    return details;
  }

  /** Parse une range URL "min-max" en objet {min?, max?}.
   *  "min" et "max" sont des mots-cles indiquant pas de borne. */
  function parseRange(rangeStr) {
    if (!rangeStr) return null;
    const [minStr, maxStr] = rangeStr.split("-");
    const range = {};
    if (minStr && minStr !== "min") range.min = parseInt(minStr, 10);
    if (maxStr && maxStr !== "max") range.max = parseInt(maxStr, 10);
    return Object.keys(range).length > 0 ? range : null;
  }

  /** Convertit les params URL de recherche LBC en filtres pour l'API finder. */
  function buildApiFilters(searchUrl) {
    const url = new URL(searchUrl);
    const params = url.searchParams;

    const filters = {
      category: { id: params.get("category") || "2" },
      enums: { ad_type: ["offer"], country_id: ["FR"] },
      ranges: { price: { min: 500 } },
    };

    // Enums (brand, model, fuel, gearbox)
    for (const key of ["u_car_brand", "u_car_model", "fuel", "gearbox"]) {
      const val = params.get(key);
      if (val) filters.enums[key] = [val];
    }

    // Text search (modeles generiques)
    const text = params.get("text");
    if (text) filters.keywords = { text };

    // Ranges (regdate, mileage, horse_power_din)
    for (const key of ["regdate", "mileage", "horse_power_din"]) {
      const range = parseRange(params.get(key));
      if (range) filters.ranges[key] = range;
    }

    // Location
    const loc = params.get("locations");
    if (loc) {
      if (loc.startsWith("rn_")) {
        filters.location = { regions: [loc.replace("rn_", "")] };
      } else if (loc.includes("__")) {
        // Format geo: City_Zip__Lat_Lng_5000_Radius
        const [, geoPart] = loc.split("__");
        const geoParts = geoPart.split("_");
        filters.location = {
          area: {
            lat: parseFloat(geoParts[0]),
            lng: parseFloat(geoParts[1]),
            radius: parseInt(geoParts[3]) || 30000,
          },
        };
      }
    }

    return filters;
  }

  /** Filtre et mappe les ads bruts en tableau de {price, year, km, fuel}. */
  function filterAndMapSearchAds(ads, targetYear, yearSpread) {
    return ads
      .filter((ad) => {
        const rawPrice = Array.isArray(ad?.price) ? ad.price[0] : ad?.price;
        const priceInt = typeof rawPrice === "number"
          ? rawPrice
          : parseInt(String(rawPrice || "0").replace(/[^\d]/g, ""), 10);
        if (!Number.isFinite(priceInt) || priceInt <= 500) return false;
        if (targetYear >= 1990) {
          const adYear = getAdYear(ad);
          if (adYear && Math.abs(adYear - targetYear) > yearSpread) return false;
        }
        return true;
      })
      .map((ad) => getAdDetails(ad));
  }

  /** Fetch les prix via l'API LBC finder/search (methode principale).
   *  LBC ne pre-rend plus les resultats dans __NEXT_DATA__ (CSR depuis ~2026).
   *
   *  En production : route via background → MAIN world (meme session/cookies
   *  que le JavaScript LBC, pas de CORS ni api_key necessaire).
   *  En tests (pas de chrome.runtime) : direct fetch fallback. */
  async function fetchSearchPricesViaApi(searchUrl) {
    const filters = buildApiFilters(searchUrl);
    // LBC detecte les bots qui demandent trop d'annonces ou trient differemment
    const body = JSON.stringify({
      filters,
      limit: 35, // Identique au site web (etait 100 -> detecte comme bot)
      sort_by: "time", // Tri par date plus naturel que prix
      sort_order: "desc",
      owner_type: "all", // Ajout explicite
    });

    // 1. Via background → MAIN world (production : cookies LBC natifs)
    if (isChromeRuntimeAvailable()) {
      try {
        const result = await chrome.runtime.sendMessage({
          action: "lbc_api_search",
          body: body,
        });
        if (result?.ok) {
          const ads = result.data?.ads || result.data?.results || [];
          console.log("[CoPilot] API finder (MAIN world): %d ads bruts", ads.length);
          return ads.length > 0 ? ads : null;
        }
        console.warn("[CoPilot] API finder (MAIN): %s", result?.error || `HTTP ${result?.status}`);
      } catch (err) {
        console.debug("[CoPilot] chrome.runtime.sendMessage echoue:", err.message);
      }
    }

    // 2. Fallback : direct fetch (tests + si background indisponible)
    const resp = await fetch("https://api.leboncoin.fr/finder/search", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
      },
      body: body,
    });

    if (!resp.ok) {
      console.warn("[CoPilot] API finder (direct): HTTP %d", resp.status);
      return null;
    }

    const data = await resp.json();
    return data.ads || data.results || [];
  }

  /** Fetch les prix via HTML scraping __NEXT_DATA__ (fallback). */
  async function fetchSearchPricesViaHtml(searchUrl) {
    const resp = await fetch(searchUrl, {
      credentials: "same-origin",
      headers: { "Accept": "text/html" },
    });
    const html = await resp.text();

    const match = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (!match) return [];

    const data = JSON.parse(match[1]);
    const pp = data?.props?.pageProps || {};
    return pp?.searchData?.ads
        || pp?.initialProps?.searchData?.ads
        || pp?.ads
        || pp?.adSearch?.ads
        || [];
  }

  /** Fetch une page de recherche LBC et extrait les prix valides.
   *  Strategie : API finder d'abord (fiable), puis fallback HTML.
   *  Retourne un tableau de {price, year, km, fuel} filtre par annee. */
  async function fetchSearchPrices(searchUrl, targetYear, yearSpread) {
    let ads = null;

    // 1. API LBC finder/search (methode principale depuis que LBC est CSR)
    try {
      ads = await fetchSearchPricesViaApi(searchUrl);
      if (ads && ads.length > 0) {
        console.log("[CoPilot] fetchSearchPrices (API): %d ads bruts", ads.length);
        return filterAndMapSearchAds(ads, targetYear, yearSpread);
      }
    } catch (err) {
      console.debug("[CoPilot] API finder indisponible:", err.message);
    }

    // 2. Fallback HTML __NEXT_DATA__ (au cas ou l'API ne marche pas)
    try {
      ads = await fetchSearchPricesViaHtml(searchUrl);
      if (ads && ads.length > 0) {
        console.log("[CoPilot] fetchSearchPrices (HTML): %d ads bruts", ads.length);
        return filterAndMapSearchAds(ads, targetYear, yearSpread);
      }
      console.log("[CoPilot] fetchSearchPrices: 0 ads (API + HTML)");
    } catch (err) {
      console.debug("[CoPilot] HTML scraping failed:", err.message);
    }

    return [];
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
      // Preferer value_label (coherent avec extractVehicleFromNextData)
      const val = a.value_label || a.value || a.text || a.value_text;
      if (key) acc[key] = val;
      return acc;
    }, {});
    const raw = attrs["mileage"] || attrs["Kilométrage"] || attrs["kilometrage"] || "0";
    return parseInt(String(raw).replace(/\s/g, ""), 10) || 0;
  }

  /** Report job completion to server. */
  async function reportJobDone(jobDoneUrl, jobId, success) {
    if (!jobId) return;
    try {
      await backendFetch(jobDoneUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, success }),
      });
    } catch (e) {
      if (isBenignRuntimeTeardownError(e)) {
        console.debug("[CoPilot] job-done report skipped (extension reloaded/unloaded)");
        return;
      }
      console.warn("[CoPilot] job-done report failed:", e);
    }
  }

  /**
   * Execute bonus jobs from the CollectionJob queue.
   * Each job contains make, model, year, region, fuel, hp_range, gearbox, job_id.
   * Builds LBC URLs from job data and POSTs collected prices to server.
   */
  async function executeBonusJobs(bonusJobs, progress) {
    const MIN_BONUS_PRICES = 5;
    const marketUrl = API_URL.replace("/analyze", "/market-prices");
    const jobDoneUrl = API_URL.replace("/analyze", "/market-prices/job-done");

    if (progress) progress.update("bonus", "running", "Exécution de " + bonusJobs.length + " jobs");

    for (const job of bonusJobs) {
      try {
        await new Promise((r) => setTimeout(r, 1000 + Math.random() * 1000));

        // Build LBC URL from job data
        // Preferer les tokens serveur (auto-appris depuis le DOM) pour les accents corrects
        const brandUpper = toLbcBrandToken(job.make);
        const modelIsGeneric = GENERIC_MODELS.includes((job.model || "").toLowerCase());
        let jobCoreUrl = "https://www.leboncoin.fr/recherche?category=2";
        if (modelIsGeneric) {
          jobCoreUrl += `&text=${encodeURIComponent(job.make)}`;
        } else {
          const jobBrand = job.site_brand_token || brandUpper;
          const jobModel = job.site_model_token || `${brandUpper}_${job.model}`;
          jobCoreUrl += `&u_car_brand=${encodeURIComponent(jobBrand)}`;
          jobCoreUrl += `&u_car_model=${encodeURIComponent(jobModel)}`;
        }

        // Add filters from job data
        let filters = "";
        if (job.fuel) {
          const fc = LBC_FUEL_CODES[job.fuel.toLowerCase()];
          if (fc) filters += `&fuel=${fc}`;
        }
        if (job.gearbox) {
          const gc = LBC_GEARBOX_CODES[job.gearbox.toLowerCase()];
          if (gc) filters += `&gearbox=${gc}`;
        }
        if (job.hp_range) {
          filters += `&horse_power_din=${job.hp_range}`;
        }

        // Region
        const locParam = LBC_REGIONS[job.region];
        if (!locParam) {
          console.warn("[CoPilot] bonus job: region inconnue '%s', skip", job.region);
          await reportJobDone(jobDoneUrl, job.job_id, false);
          if (progress) progress.addSubStep("bonus", job.region, "skip", "Région inconnue");
          continue;
        }

        let searchUrl = jobCoreUrl + filters + `&locations=${locParam}`;
        const jobYear = parseInt(job.year, 10);
        if (jobYear >= 1990) searchUrl += `&regdate=${jobYear - 1}-${jobYear + 1}`;

        const bonusPrices = await fetchSearchPrices(searchUrl, jobYear, 1);
        console.log("[CoPilot] bonus job %s %s %d %s: %d prix", job.make, job.model, job.year, job.region, bonusPrices.length);

        if (progress) {
          const stepStatus = bonusPrices.length >= MIN_BONUS_PRICES ? "done" : "skip";
          progress.addSubStep("bonus", job.make + " " + job.model + " · " + job.region, stepStatus, bonusPrices.length + " annonces");
        }

        if (bonusPrices.length >= MIN_BONUS_PRICES) {
          const bDetails = bonusPrices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
          const bInts = bDetails.map((p) => p.price);
          if (bInts.length >= MIN_BONUS_PRICES) {
            const bonusPrecision = bonusPrices.length >= 20 ? 4 : 2;
            const bonusPayload = {
              make: job.make,
              model: job.model,
              year: jobYear,
              region: job.region,
              prices: bInts,
              price_details: bDetails,
              fuel: job.fuel || null,
              hp_range: job.hp_range || null,
              precision: bonusPrecision,
              search_log: [{
                step: 1, precision: bonusPrecision, location_type: "region",
                year_spread: 1,
                filters_applied: [
                  ...(filters.includes("fuel=") ? ["fuel"] : []),
                  ...(filters.includes("gearbox=") ? ["gearbox"] : []),
                  ...(filters.includes("horse_power_din=") ? ["hp"] : []),
                ],
                ads_found: bonusPrices.length, url: searchUrl,
                was_selected: true,
                reason: `bonus job queue: ${bonusPrices.length} annonces`,
              }],
            };
            const bResp = await backendFetch(marketUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(bonusPayload),
            });
            console.log("[CoPilot] bonus job POST %s: %s", job.region, bResp.ok ? "OK" : "FAIL");
            await reportJobDone(jobDoneUrl, job.job_id, bResp.ok);
          } else {
            await reportJobDone(jobDoneUrl, job.job_id, false);
          }
        } else {
          await reportJobDone(jobDoneUrl, job.job_id, false);
        }
      } catch (err) {
        if (isBenignRuntimeTeardownError(err)) {
          console.info("[CoPilot] bonus jobs interrompus: extension rechargée/déchargée");
          if (progress) {
            progress.update("bonus", "warning", "Extension rechargée, jobs bonus interrompus");
          }
          break;
        }
        console.warn("[CoPilot] bonus job %s failed:", job.region, err);
        await reportJobDone(jobDoneUrl, job.job_id, false);
      }
    }
    if (progress) progress.update("bonus", "done");
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
  async function maybeCollectMarketPrices(vehicle, nextData, progress) {
    const { make, model, year, fuel, gearbox, horse_power } = vehicle;
    if (!make || !model || !year) return { submitted: false };

    // Pre-compute hp range for next-job URL and search filters
    const hp = parseInt(horse_power, 10) || 0;
    const hpRange = getHorsePowerRange(hp);

    // Ne pas collecter de prix pour les categories non-voiture (motos, etc.)
    const urlMatch = window.location.href.match(/\/ad\/([a-z_]+)\//);
    const urlCategory = urlMatch ? urlMatch[1] : null;
    if (urlCategory && EXCLUDED_CATEGORIES.includes(urlCategory)) {
      console.log("[CoPilot] collecte ignoree: categorie exclue", urlCategory);
      if (progress) {
        progress.update("job", "skip", "Catégorie exclue : " + urlCategory);
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }

    // Extraire le kilometrage depuis le nextData pour le range de recherche
    const mileageKm = extractMileageFromNextData(nextData);

    // 1. Extraire la localisation depuis le nextData (pas le DOM qui peut etre stale)
    const location = extractLocationFromNextData(nextData);
    const region = location?.region || "";
    if (!region) {
      console.warn("[CoPilot] collecte ignoree: pas de region dans nextData");
      if (progress) {
        progress.update("job", "skip", "Région non disponible");
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false };
    }
    console.log("[CoPilot] collecte: region=%s, location=%o, km=%d", region, location, mileageKm);

    // 2. Demander au serveur quel vehicule collecter
    if (progress) progress.update("job", "running");
    const fuelForJob = (fuel || "").toLowerCase();
    const gearboxForJob = (gearbox || "").toLowerCase();
    const jobUrl = API_URL.replace("/analyze", "/market-prices/next-job")
      + `?make=${encodeURIComponent(make)}&model=${encodeURIComponent(model)}`
      + `&year=${encodeURIComponent(year)}&region=${encodeURIComponent(region)}`
      + (fuelForJob ? `&fuel=${encodeURIComponent(fuelForJob)}` : "")
      + (gearboxForJob ? `&gearbox=${encodeURIComponent(gearboxForJob)}` : "")
      + (hpRange ? `&hp_range=${encodeURIComponent(hpRange)}` : "");

    let jobResp;
    try {
      console.log("[CoPilot] next-job →", jobUrl);
      jobResp = await backendFetch(jobUrl).then((r) => r.json());
      console.log("[CoPilot] next-job ←", JSON.stringify(jobResp));
    } catch (err) {
      console.warn("[CoPilot] next-job erreur:", err);
      if (progress) {
        progress.update("job", "error", "Serveur injoignable");
        progress.update("collect", "skip");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
      return { submitted: false }; // serveur injoignable -- silencieux
    }
    if (!jobResp?.data?.collect) {
      const queuedJobs = jobResp?.data?.bonus_jobs || [];
      if (queuedJobs.length === 0) {
        console.log("[CoPilot] next-job: collect=false, aucun bonus en queue");
        if (progress) {
          progress.update("job", "done", "Données déjà à jour, pas de collecte nécessaire");
          progress.update("collect", "skip", "Non nécessaire");
          progress.update("submit", "skip");
          progress.update("bonus", "skip");
        }
        return { submitted: false };
      }
      console.log("[CoPilot] next-job: collect=false, %d bonus jobs en queue", queuedJobs.length);
      if (progress) {
        progress.update("job", "done", "Véhicule à jour — " + queuedJobs.length + " jobs en attente");
        progress.update("collect", "skip", "Véhicule déjà à jour");
        progress.update("submit", "skip");
      }
      await executeBonusJobs(queuedJobs, progress);
      localStorage.setItem("copilot_last_collect", String(Date.now()));
      return { submitted: false };
    }

    const target = jobResp.data.vehicle;
    const targetRegion = jobResp.data.region;
    const isRedirect = !!jobResp.data.redirect;
    const bonusJobs = jobResp.data.bonus_jobs || [];
    console.log("[CoPilot] next-job: %d bonus jobs", bonusJobs.length);

    // 3. Cooldown 24h -- uniquement pour les collectes d'AUTRES vehicules
    //    Le vehicule courant est toujours collecte (le serveur gere la fraicheur)
    const isCurrentVehicle =
      target.make.toLowerCase() === make.toLowerCase() &&
      target.model.toLowerCase() === model.toLowerCase();

    if (!isCurrentVehicle) {
      const lastCollect = parseInt(localStorage.getItem("copilot_last_collect") || "0", 10);
      if (Date.now() - lastCollect < COLLECT_COOLDOWN_MS) {
        console.log("[CoPilot] cooldown actif pour autre vehicule, skip collecte redirect — bonus jobs toujours executes");
        if (progress) {
          progress.update("job", "done", "Cooldown actif (autre véhicule collecté récemment)");
          progress.update("collect", "skip", "Cooldown 24h");
          progress.update("submit", "skip");
        }
        // Le cooldown bloque la collecte du redirect, mais les bonus jobs
        // sont des taches assignees par le serveur — on les execute quand meme
        if (bonusJobs.length > 0) {
          await executeBonusJobs(bonusJobs, progress);
          // PAS de localStorage.setItem ici : l'execution de bonus jobs
          // ne doit pas reset le cooldown redirect (sinon cascade infinie)
        } else if (progress) {
          progress.update("bonus", "skip");
        }
        return { submitted: false };
      }
    }
    const targetLabel = target.make + " " + target.model + " " + target.year;
    if (progress) {
      progress.update("job", "done", targetLabel + (isCurrentVehicle ? " (véhicule courant)" : " (autre véhicule du référentiel)"));
    }
    console.log("[CoPilot] collecte cible: %s %s %d (isCurrentVehicle=%s, redirect=%s)", target.make, target.model, target.year, isCurrentVehicle, isRedirect);

    // 4. Construire l'URL de recherche LeBonCoin (filtres structures)
    const targetYear = parseInt(target.year, 10) || 0;
    const modelIsGeneric = GENERIC_MODELS.includes((target.model || "").toLowerCase());

    // URL core : marque/modele uniquement (les filtres sont separes pour l'escalade)
    // Preferer les tokens DOM (extraits du lien "Voir d'autres annonces") car ils
    // contiennent les accents corrects (ex: "BMW_Série 3" vs "BMW_Serie 3").
    // __NEXT_DATA__ renvoie parfois le modele sans accent, mais LBC exige le token exact.
    const brandUpper = toLbcBrandToken(target.make);
    // Priorite : tokens DOM (vehicule courant) > tokens serveur (auto-appris) > fallback manuel
    const hasDomTokens = isCurrentVehicle && vehicle.site_brand_token && vehicle.site_model_token;
    const hasServerTokens = target.site_brand_token && target.site_model_token;
    const effectiveBrand = hasDomTokens ? vehicle.site_brand_token
      : hasServerTokens ? target.site_brand_token
      : brandUpper;
    const effectiveModel = hasDomTokens ? vehicle.site_model_token
      : hasServerTokens ? target.site_model_token
      : `${brandUpper}_${target.model}`;
    const tokenSource = hasDomTokens ? "DOM" : hasServerTokens ? "serveur" : "fallback";
    if (progress) {
      progress.addSubStep("collect", "Diagnostic LBC", "done",
        `Token marque: ${target.make} → ${effectiveBrand} (${tokenSource})`);
    }
    let coreUrl = "https://www.leboncoin.fr/recherche?category=2";
    if (modelIsGeneric) {
      coreUrl += `&text=${encodeURIComponent(target.make)}`;
    } else {
      coreUrl += `&u_car_brand=${encodeURIComponent(effectiveBrand)}`;
      coreUrl += `&u_car_model=${encodeURIComponent(effectiveModel)}`;
    }

    // GARDE-FOU : quand le serveur redirige vers un AUTRE vehicule du referentiel,
    // on ne doit PAS utiliser le fuel/gearbox/hp/km du vehicule courant
    // (un A6 diesel 218ch n'a rien a voir avec un 208 essence 75ch).
    // On cherche sans filtres vehicule specifiques → recherche plus large mais correcte.
    let fuelParam = "";
    let mileageParam = "";
    let gearboxParam = "";
    let hpParam = "";
    let targetFuel = null;
    let fuelCode = null;
    let gearboxCode = null;
    if (!isRedirect) {
      targetFuel = (fuel || "").toLowerCase();
      fuelCode = LBC_FUEL_CODES[targetFuel];
      fuelParam = fuelCode ? `&fuel=${fuelCode}` : "";

      if (mileageKm > 0) {
        const mileageRange = getMileageRange(mileageKm);
        if (mileageRange) mileageParam = `&mileage=${mileageRange}`;
      }

      gearboxCode = LBC_GEARBOX_CODES[(gearbox || "").toLowerCase()];
      gearboxParam = gearboxCode ? `&gearbox=${gearboxCode}` : "";

      hpParam = hpRange ? `&horse_power_din=${hpRange}` : "";
    }

    // Niveaux de filtrage (du plus precis au plus large)
    const fullFilters = fuelParam + mileageParam + gearboxParam + hpParam;
    const noHpFilters = fuelParam + mileageParam + gearboxParam;
    const minFilters = fuelParam + gearboxParam;

    // 5. Escalade progressive : precision d'abord, puis on elargit
    //    On a besoin de 20+ annonces pour un argus fiable (IQR stable).
    //    7 strategies, de la plus precise a la plus large :
    //    1. Geo (ville + 30 km) + annee ±1 + tous filtres
    //    2. Region + annee ±1 + tous filtres
    //    3. Region + annee ±2 + tous filtres
    //    4. National + annee ±1 + tous filtres
    //    5. National + annee ±2 + tous filtres
    //    6. National + annee ±2 + sans puissance DIN
    //    7. National + annee ±3 + sans puissance ni km
    const hasGeo = location?.lat && location?.lng && location?.city && location?.zipcode;
    const geoParam = hasGeo ? buildLocationParam(location, DEFAULT_SEARCH_RADIUS) : "";
    const regionParam = LBC_REGIONS[region] || "";

    const strategies = [];
    if (geoParam)    strategies.push({ loc: geoParam,    yearSpread: 1, filters: fullFilters, precision: 5 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 1, filters: fullFilters, precision: 4 });
    if (regionParam) strategies.push({ loc: regionParam, yearSpread: 2, filters: fullFilters, precision: 4 });
    strategies.push({ loc: "", yearSpread: 1, filters: fullFilters, precision: 3 });
    strategies.push({ loc: "", yearSpread: 2, filters: fullFilters, precision: 3 });
    strategies.push({ loc: "", yearSpread: 2, filters: noHpFilters, precision: 2 });
    strategies.push({ loc: "", yearSpread: 3, filters: minFilters,  precision: 1 });

    console.log("[CoPilot] fuel=%s → fuelCode=%s | gearbox=%s → gearboxCode=%s | hp=%d → hpRange=%s | km=%d",
      targetFuel, fuelCode, (gearbox || "").toLowerCase(), gearboxCode, hp, hpRange, mileageKm);
    console.log("[CoPilot] coreUrl:", coreUrl);
    console.log("[CoPilot] %d strategies, geoParam=%s, regionParam=%s", strategies.length, geoParam || "(vide)", regionParam || "(vide)");

    let submitted = false;
    let prices = [];
    let collectedPrecision = null;
    const searchLog = [];
    if (progress) progress.update("collect", "running");
    try {
      for (let i = 0; i < strategies.length; i++) {
        // Anti-detection LBC : delai aleatoire entre requetes (800-1500ms)
        // Simule un comportement humain. Session reelle = risque faible.
        if (i > 0) await new Promise((r) => setTimeout(r, 800 + Math.random() * 700));

        const strategy = strategies[i];
        let searchUrl = coreUrl + strategy.filters;
        if (strategy.loc) searchUrl += `&locations=${strategy.loc}`;
        if (targetYear >= 1990) {
          searchUrl += `&regdate=${targetYear - strategy.yearSpread}-${targetYear + strategy.yearSpread}`;
        }

        // Label lisible pour la sous-etape
        const locLabel = (strategy.loc === geoParam && geoParam) ? "Géo (" + (location?.city || "local") + " 30km)"
          : (strategy.loc === regionParam && regionParam) ? "Région (" + targetRegion + ")"
          : "National";
        const strategyLabel = "Stratégie " + (i + 1) + " \u00b7 " + locLabel + " \u00b1" + strategy.yearSpread + "an";

        prices = await fetchSearchPrices(searchUrl, targetYear, strategy.yearSpread);
        const enoughPrices = prices.length >= MIN_PRICES_FOR_ARGUS;
        console.log("[CoPilot] strategie %d (precision=%d): %d prix trouvés | %s",
          i + 1, strategy.precision, prices.length, searchUrl.substring(0, 150));

        // Sous-etape dans la checklist
        if (progress) {
          const stepStatus = enoughPrices ? "done" : "skip";
          const stepDetail = prices.length + " annonces" + (enoughPrices ? " \u2713 seuil atteint" : "");
          progress.addSubStep("collect", strategyLabel, stepStatus, stepDetail);
        }

        // Capturer chaque etape pour la transparence admin
        const locationType = (strategy.loc === geoParam && geoParam) ? "geo"
          : (strategy.loc === regionParam && regionParam) ? "region"
          : "national";
        searchLog.push({
          step: i + 1,
          precision: strategy.precision,
          location_type: locationType,
          year_spread: strategy.yearSpread,
          filters_applied: [
            ...(strategy.filters.includes("fuel=") ? ["fuel"] : []),
            ...(strategy.filters.includes("gearbox=") ? ["gearbox"] : []),
            ...(strategy.filters.includes("horse_power_din=") ? ["hp"] : []),
            ...(strategy.filters.includes("mileage=") ? ["km"] : []),
          ],
          ads_found: prices.length,
          url: searchUrl,
          was_selected: enoughPrices,
          reason: enoughPrices
            ? `${prices.length} annonces >= ${MIN_PRICES_FOR_ARGUS} minimum`
            : `${prices.length} annonces < ${MIN_PRICES_FOR_ARGUS} minimum`,
        });

        if (enoughPrices) {
          collectedPrecision = strategy.precision;
          console.log("[CoPilot] ✓ assez de prix (%d >= %d), precision=%d", prices.length, MIN_PRICES_FOR_ARGUS, collectedPrecision);
          break;
        }
      }

      if (prices.length >= MIN_PRICES_FOR_ARGUS) {
        if (progress) {
          progress.update("collect", "done", prices.length + " prix collectés (précision " + (collectedPrecision || "?") + ")");
          progress.update("submit", "running");
        }
        const priceDetails = prices.filter((p) => Number.isInteger(p?.price) && p.price > 500);
        const priceInts = priceDetails.map((p) => p.price);
        if (priceInts.length < MIN_PRICES_FOR_ARGUS) {
          console.warn("[CoPilot] apres filtrage >500: %d prix valides (< %d requis)", priceInts.length, MIN_PRICES_FOR_ARGUS);
          // Si on a quand meme > 5 prix, on tente l'envoi "degradé" (precision faible)
          if (priceInts.length >= 5) {
             console.log("[CoPilot] envoi degradé avec %d prix (min 5)", priceInts.length);
          } else {
             if (progress) {
               progress.update("submit", "warning", "Trop de prix invalides après filtrage");
               progress.update("bonus", "skip");
             }
             return { submitted: false, isCurrentVehicle };
          }
        }
        const marketUrl = API_URL.replace("/analyze", "/market-prices");
        const payload = {
          make: target.make,
          model: target.model,
          year: parseInt(target.year, 10),
          region: targetRegion,
          prices: priceInts,
          price_details: priceDetails,
          category: urlCategory,
          fuel: fuelCode ? targetFuel : null,
          hp_range: hpRange || null,
          precision: collectedPrecision,
          search_log: searchLog,
          // Auto-apprentissage : envoyer les tokens DOM pour que le serveur
          // les persiste sur le Vehicle (accents corrects pour futures recherches)
          site_brand_token: isCurrentVehicle ? vehicle.site_brand_token : null,
          site_model_token: isCurrentVehicle ? vehicle.site_model_token : null,
        };
        console.log("[CoPilot] POST /api/market-prices:", target.make, target.model, target.year, targetRegion, "fuel=", payload.fuel, "n=", priceInts.length);
        const marketResp = await backendFetch(marketUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        submitted = marketResp.ok;
        if (!marketResp.ok) {
          const errBody = await marketResp.json().catch(() => null);
          console.warn("[CoPilot] POST /api/market-prices FAILED:", marketResp.status, errBody);
          if (progress) progress.update("submit", "error", "Erreur serveur (" + marketResp.status + ")");
        } else {
          console.log("[CoPilot] POST /api/market-prices OK, submitted=true");
          if (progress) progress.update("submit", "done", priceInts.length + " prix envoyés (" + targetRegion + ")");

          // 5b. BONUS : executer les jobs de la queue
          if (bonusJobs.length > 0) {
            await executeBonusJobs(bonusJobs, progress);
          } else {
            if (progress) progress.update("bonus", "skip", "Aucun job en attente");
          }
        }
      } else {
        console.log(`[CoPilot] pas assez de prix apres toutes les strategies: ${prices.length} < ${MIN_PRICES_FOR_ARGUS}`);
        if (progress) {
          progress.update("collect", "warning", prices.length + " annonces trouvées (minimum " + MIN_PRICES_FOR_ARGUS + ")");
          progress.update("submit", "skip", "Pas assez de données");
          progress.update("bonus", "skip");
        }

        // Reporter la recherche echouee au serveur pour diagnostic
        // (URLs mal construites, tokens manquants, etc.)
        try {
          const failedUrl = API_URL.replace("/analyze", "/market-prices/failed-search");
          await backendFetch(failedUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              make: target.make,
              model: target.model,
              year: parseInt(target.year, 10),
              region: targetRegion,
              fuel: targetFuel || null,
              hp_range: hpRange || null,
              brand_token_used: effectiveBrand,
              model_token_used: effectiveModel,
              token_source: tokenSource,
              search_log: searchLog,
            }),
          });
          console.log("[CoPilot] failed search reported to server");
        } catch (e) {
          console.warn("[CoPilot] failed-search report error:", e);
        }
      }
    } catch (err) {
      console.error("[CoPilot] market collection failed:", err);
      if (progress) {
        progress.update("collect", "error", "Erreur pendant la collecte");
        progress.update("submit", "skip");
        progress.update("bonus", "skip");
      }
    }

    // 6. Sauvegarder le timestamp (meme si pas assez de prix)
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
      fetchSearchPricesViaApi,
      fetchSearchPricesViaHtml,
      buildApiFilters,
      parseRange,
      filterAndMapSearchAds,
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
      toLbcBrandToken,
      LBC_BRAND_ALIASES,
      formatPrecisionStars,
      PRECISION_LABELS,
      getAdDetails,
      executeBonusJobs,
      reportJobDone,
    };
  }
})();
