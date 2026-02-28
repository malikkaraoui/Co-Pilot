/**
 * Co-Pilot Popup Script
 *
 * Gere le bouton "Analyser cette annonce" dans le popup de l'extension.
 * Envoie un message au background pour injecter le content script on-demand.
 */

(function () {
  "use strict";

  const analyzeBtn = document.getElementById("analyze-btn");
  const statusEl = document.getElementById("popup-status");
  const statusText = document.getElementById("popup-status-text");

  /** Verifie si l'onglet actif est une page annonce supportee. */
  function isSupportedAd(url) {
    // LeBonCoin
    if (url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/")) return true;
    // AutoScout24 (tous TLDs)
    if (/autoscout24\.\w+\/(?:fr|de|it|nl|es|en)?\/?d\//.test(url)) return true;
    return false;
  }

  /** Met a jour le statut dans le popup. */
  function setStatus(text, isError) {
    statusText.textContent = text;
    if (isError) {
      statusEl.classList.add("error");
    } else {
      statusEl.classList.remove("error");
    }
  }

  /** Gere le clic sur le bouton Analyser. */
  analyzeBtn.addEventListener("click", async () => {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = "Injection en cours...";

    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

      if (!tab || !tab.url || !isSupportedAd(tab.url)) {
        setStatus("Cette page n'est pas une annonce supportée.", true);
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Analyser cette annonce";
        return;
      }

      // Demander au background d'injecter le content script
      const response = await chrome.runtime.sendMessage({
        action: "inject_and_analyze",
        tabId: tab.id,
      });

      if (response && response.ok) {
        setStatus("Analyse lancée !", false);
        // Fermer le popup apres un court delai pour laisser le content script travailler
        setTimeout(() => window.close(), 400);
      } else {
        setStatus(response?.error || "Erreur lors de l'injection.", true);
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = "Analyser cette annonce";
      }
    } catch (err) {
      setStatus("Erreur : " + err.message, true);
      analyzeBtn.disabled = false;
      analyzeBtn.textContent = "Analyser cette annonce";
    }
  });

  // Au chargement, verifier si on est sur leboncoin
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab || !tab.url || !isSupportedAd(tab.url)) {
      setStatus("Naviguez vers une annonce auto.", true);
      analyzeBtn.disabled = true;
    }
  });
})();
