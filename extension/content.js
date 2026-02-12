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

  /** Construit le HTML de la liste des filtres. */
  function buildFiltersList(filters) {
    if (!filters || !filters.length) return "";

    return filters
      .map((f) => {
        const color = statusColor(f.status);
        const icon = statusIcon(f.status);
        const label = filterLabel(f.filter_id);
        const detailsHTML = f.details ? buildDetailsHTML(f.details) : "";

        return `
          <div class="copilot-filter-item" data-status="${escapeHTML(f.status)}">
            <div class="copilot-filter-header">
              <span class="copilot-filter-icon" style="color:${color}">${icon}</span>
              <span class="copilot-filter-label">${escapeHTML(label)}</span>
              <span class="copilot-filter-score" style="color:${color}">${Math.round(f.score * 100)}%</span>
            </div>
            <p class="copilot-filter-message">${escapeHTML(f.message)}</p>
            ${detailsHTML}
          </div>
        `;
      })
      .join("");
  }

  /** Construit le HTML des details d'un filtre (depliable). */
  function buildDetailsHTML(details) {
    const entries = Object.entries(details)
      .filter(([, v]) => v !== null && v !== undefined)
      .map(([k, v]) => {
        const val = typeof v === "object" ? JSON.stringify(v) : v;
        return `<span class="copilot-detail-key">${escapeHTML(k)}:</span> ${escapeHTML(val)}`;
      })
      .join("<br>");

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

  /** Lance l'analyse : extrait les donnees, appelle l'API, affiche les resultats. */
  async function runAnalysis() {
    showLoading();

    const nextData = await extractNextData();
    if (!nextData) {
      showPopup(buildErrorPopup("Impossible de lire les données de cette page. Vérifiez que vous êtes sur une annonce Leboncoin."));
      return;
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
