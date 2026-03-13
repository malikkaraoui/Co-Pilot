/**
 * Manipulation DOM pour l'injection de la popup overlay.
 *
 * C'est le "chef d'orchestre" de l'UI : il injecte le HTML dans la page,
 * branche tous les event listeners (close, retry, email, premium),
 * et gere la generation email.
 *
 * NOTE SECURITE : tout le HTML passe a showPopup() est pre-escape via
 * escapeHTML() ou compose de template strings statiques. Aucune donnee
 * utilisateur brute n'est injectee.
 */

"use strict";

import { backendFetch } from '../utils/fetch.js';

// Etat module : references vers le flow principal (injectees par content.js au boot)
let _runAnalysis = null;
let _apiUrl = null;
let _lastScanIdGetter = null;

/**
 * Initialise les references necessaires pour les actions CTA.
 * Appele une seule fois au demarrage par content.js.
 * @param {Object} config
 * @param {Function} config.runAnalysis - Relance l'analyse complete
 * @param {string} config.apiUrl - URL de base de l'API backend
 * @param {Function} config.getLastScanId - Getter pour le scan_id courant
 */
export function initDom({ runAnalysis, apiUrl, getLastScanId }) {
  _runAnalysis = runAnalysis;
  _apiUrl = apiUrl;
  _lastScanIdGetter = getLastScanId;
}

/** Supprime la popup et l'overlay s'ils existent. */
export function removePopup() {
  const existing = document.getElementById("okazcar-popup");
  if (existing) existing.remove();
  const overlay = document.getElementById("okazcar-overlay");
  if (overlay) overlay.remove();
}

/**
 * Injecte une popup dans le DOM et branche tous les listeners interactifs.
 * C'est LA fonction centrale de l'UI — toutes les popups passent par ici.
 * @param {string} safeHTML - HTML pre-escape a injecter
 */
export function showPopup(safeHTML) {
  removePopup();
  const overlay = document.createElement("div");
  overlay.id = "okazcar-overlay";
  overlay.className = "okazcar-overlay";
  // Clic sur l'overlay (en dehors de la popup) = fermeture
  overlay.addEventListener("click", (e) => { if (e.target === overlay) removePopup(); });

  // On parse le HTML via <template> pour eviter l'insertion directe dans le DOM
  const template = document.createElement("template");
  template.innerHTML = safeHTML;
  const popupNode = template.content.firstElementChild;
  overlay.appendChild(popupNode);
  document.body.appendChild(overlay);

  // Accordeon : clic sur un filtre = expand/collapse de son contenu
  popupNode.querySelectorAll('.okazcar-filter-header').forEach(header => {
    header.addEventListener('click', () => {
      header.closest('.okazcar-filter-item').classList.toggle('expanded');
    });
  });

  const closeBtn = document.getElementById("okazcar-close");
  if (closeBtn) closeBtn.addEventListener("click", removePopup);
  const retryBtn = document.getElementById("okazcar-retry");
  if (retryBtn) retryBtn.addEventListener("click", () => { removePopup(); if (_runAnalysis) _runAnalysis(); });
  const premiumBtn = document.getElementById("okazcar-premium-btn");
  if (premiumBtn) {
    premiumBtn.addEventListener("click", () => { premiumBtn.textContent = "Bientôt disponible !"; premiumBtn.disabled = true; });
  }

  // --- Generation email via Gemini ---
  // Flow : clic -> masque bouton -> spinner -> appel API -> affiche textarea OU erreur
  const emailBtn = document.getElementById("okazcar-email-btn");
  if (emailBtn) {
    emailBtn.addEventListener("click", async () => {
      const loading = document.getElementById("okazcar-email-loading");
      const result = document.getElementById("okazcar-email-result");
      const errorDiv = document.getElementById("okazcar-email-error");
      const textArea = document.getElementById("okazcar-email-text");
      emailBtn.style.display = "none";
      loading.style.display = "flex";
      errorDiv.style.display = "none";
      try {
        const emailUrl = _apiUrl.replace("/analyze", "/email-draft");
        const scanId = _lastScanIdGetter ? _lastScanIdGetter() : null;
        const resp = await backendFetch(emailUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scan_id: scanId }) });
        const data = await resp.json();
        if (data.success) { textArea.value = data.data.generated_text; result.style.display = "block"; }
        else {
          let msg = data.error || "Erreur de génération";
          // On masque les erreurs techniques brutes (stack traces Google, etc.)
          if (msg.length > 120 || msg.includes("googleapis") || msg.includes("INVALID_ARGUMENT")) {
            msg = "Service de rédaction temporairement indisponible.";
          }
          errorDiv.textContent = msg; errorDiv.style.display = "block"; emailBtn.style.display = "block";
        }
      } catch (err) { errorDiv.textContent = "Service indisponible"; errorDiv.style.display = "block"; emailBtn.style.display = "block"; }
      loading.style.display = "none";
    });
  }

  // --- Bouton "Copier" pour l'email genere ---
  const copyBtn = document.getElementById("okazcar-email-copy");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const textArea = document.getElementById("okazcar-email-text");
      navigator.clipboard.writeText(textArea.value).then(() => {
        const copied = document.getElementById("okazcar-email-copied");
        copied.style.display = "inline";
        setTimeout(() => { copied.style.display = "none"; }, 2000);
      });
    });
  }
}
