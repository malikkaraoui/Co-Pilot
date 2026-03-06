/**
 * DOM manipulation for popup overlay injection.
 *
 * SECURITY NOTE: All HTML passed to showPopup() is pre-escaped via
 * escapeHTML() or consists of hardcoded template strings. No raw user
 * input is ever injected. This is the same safe pattern used in the
 * original content.js before this refactoring.
 */

"use strict";

import { backendFetch } from '../utils/fetch.js';

let _runAnalysis = null;
let _apiUrl = null;
let _lastScanIdGetter = null;

export function initDom({ runAnalysis, apiUrl, getLastScanId }) {
  _runAnalysis = runAnalysis;
  _apiUrl = apiUrl;
  _lastScanIdGetter = getLastScanId;
}

export function removePopup() {
  const existing = document.getElementById("okazcar-popup");
  if (existing) existing.remove();
  const overlay = document.getElementById("okazcar-overlay");
  if (overlay) overlay.remove();
}

export function showPopup(safeHTML) {
  removePopup();
  const overlay = document.createElement("div");
  overlay.id = "okazcar-overlay";
  overlay.className = "okazcar-overlay";
  overlay.addEventListener("click", (e) => { if (e.target === overlay) removePopup(); });

  // safeHTML is pre-escaped; parse it into DOM nodes
  const template = document.createElement("template");
  template.innerHTML = safeHTML;
  const popupNode = template.content.firstElementChild;
  overlay.appendChild(popupNode);
  document.body.appendChild(overlay);

  const closeBtn = document.getElementById("okazcar-close");
  if (closeBtn) closeBtn.addEventListener("click", removePopup);
  const retryBtn = document.getElementById("okazcar-retry");
  if (retryBtn) retryBtn.addEventListener("click", () => { removePopup(); if (_runAnalysis) _runAnalysis(); });
  const premiumBtn = document.getElementById("okazcar-premium-btn");
  if (premiumBtn) {
    premiumBtn.addEventListener("click", () => { premiumBtn.textContent = "Bientôt disponible !"; premiumBtn.disabled = true; });
  }

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
        else { errorDiv.textContent = data.error || "Erreur de génération"; errorDiv.style.display = "block"; emailBtn.style.display = "block"; }
      } catch (err) { errorDiv.textContent = "Service indisponible"; errorDiv.style.display = "block"; emailBtn.style.display = "block"; }
      loading.style.display = "none";
    });
  }

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
