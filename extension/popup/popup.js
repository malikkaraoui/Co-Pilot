/**
 * OKazCar Popup Script
 *
 * Le popup de l'extension (clic sur l'icone dans la barre Chrome).
 * Son seul role : verifier qu'on est sur une annonce supportee,
 * puis demander au background d'injecter le content script.
 * Aucune analyse ici — tout le travail est dans content.js.
 */

(function () {
  "use strict";

  const analyzeBtn = document.getElementById("analyze-btn");
  const statusEl = document.getElementById("popup-status");
  const statusText = document.getElementById("popup-status-text");

  /**
   * Verifie si l'URL correspond a une page annonce supportee.
   * On supporte LeBonCoin, AutoScout24 (tous TLDs europeens) et La Centrale.
   *
   * @param {string} url - URL de l'onglet actif
   * @returns {boolean}
   */
  function isSupportedAd(url) {
    // LeBonCoin : /ad/ (nouveau format) et /voitures/ (ancien format)
    if (url.includes("leboncoin.fr/ad/") || url.includes("leboncoin.fr/voitures/")) return true;
    // AutoScout24 : regex large pour couvrir tous les TLDs (.fr, .de, .it, etc.)
    // et toutes les langues de path (d/, angebote/, offres/, etc.)
    if (/autoscout24\.\w+\/(?:(?:fr|de|it|en|nl|es|pl|sv)\/)?(?:d|angebote|offerte|ofertas|aanbod|offres|annunci|anuncios|oferta|erbjudanden)\/[a-z0-9][\w-]*?[-–](?:\d+|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|[a-z0-9]{6,})(?:[/?#]|$)/i.test(url)) return true;
    // La Centrale : format fixe avec ID numerique
    if (/lacentrale\.fr\/(?:auto|utilitaire)-occasion-annonce-\d+\.html/.test(url)) return true;
    return false;
  }

  /**
   * Met a jour le message de statut dans le popup.
   *
   * @param {string} text - Message a afficher
   * @param {boolean} isError - true pour afficher en style erreur
   */
  function setStatus(text, isError) {
    statusText.textContent = text;
    if (isError) {
      statusEl.classList.add("error");
    } else {
      statusEl.classList.remove("error");
    }
  }

  // Clic sur "Analyser cette annonce"
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

      // On ne fait pas l'analyse ici — on demande au background
      // d'injecter le content script qui fera tout le travail
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

  // Synchroniser l'icone de l'extension avec le theme OS (dark/light).
  // On le fait ici parce que le popup est le premier point de contact
  // avec l'utilisateur et matchMedia n'est pas dispo dans le service worker.
  const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  chrome.runtime.sendMessage({ action: "update_icon_theme", isDark });
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    chrome.runtime.sendMessage({ action: "update_icon_theme", isDark: e.matches });
  });

  // Au chargement du popup, desactiver le bouton si on n'est pas sur une annonce
  chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
    if (!tab || !tab.url || !isSupportedAd(tab.url)) {
      setStatus("Naviguez vers une annonce auto.", true);
      analyzeBtn.disabled = true;
    }
  });
})();
