/**
 * OKazCar Background Service Worker (Chrome MV3)
 *
 * Ce fichier tourne dans le service worker de l'extension.
 * Il a 3 roles principaux :
 *
 * 1. Proxy backend : le content script (HTTPS) ne peut pas fetch vers
 *    HTTP localhost (mixed-content). Le service worker n'a pas cette
 *    restriction, donc il sert de relai.
 *
 * 2. Execution MAIN world : pour acceder aux variables JS des sites
 *    (window.__NEXT_DATA__ sur LBC, window.CLASSIFIED_GALLERY sur LC)
 *    et utiliser leurs cookies de session (API LBC), on injecte du code
 *    dans le "MAIN world" de la page via chrome.scripting.
 *
 * 3. Injection on-demand : le content script n'est pas injecte
 *    automatiquement — c'est le popup qui declenche l'injection
 *    pour eviter tout bruit sur les pages non-analysees.
 */

// ── Icone adaptative dark/light mode ────────────────────────

/**
 * Met a jour l'icone de l'extension selon le theme de l'OS.
 * On a deux jeux d'icones : classique (fond sombre) et "-light" (fond clair).
 *
 * @param {boolean} isDark - true si l'OS est en mode sombre
 */
function updateIcon(isDark) {
  const suffix = isDark ? "-light" : "";
  chrome.action.setIcon({
    path: {
      16: `icons/icon16${suffix}.png`,
      48: `icons/icon48${suffix}.png`,
      128: `icons/icon128${suffix}.png`,
    },
  });
}

// Au demarrage du service worker, restaurer le dernier theme connu
// (le service worker peut redemarrer a tout moment dans MV3)
chrome.storage.local.get("isDarkMode", (result) => {
  if (result.isDarkMode != null) updateIcon(result.isDarkMode);
});

// ── Routeur de messages ─────────────────────────────────────
// Tous les messages passent par ce listener unique.
// Le `return true` est obligatoire pour les reponses asynchrones
// dans chrome.runtime.onMessage (sinon le port se ferme).

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // ── Mise a jour icone dark/light depuis popup ou content ──
  if (message.action === "update_icon_theme") {
    updateIcon(message.isDark);
    chrome.storage.local.set({ isDarkMode: message.isDark });
    return false; // reponse synchrone, pas besoin de garder le port ouvert
  }

  // ── Proxy backend API (content script -> background -> backend) ──
  // Whitelist stricte : on accepte uniquement localhost et *.onrender.com
  // pour eviter qu'un site malveillant utilise le proxy comme open relay
  if (message.action === "backend_fetch") {
    const url = String(message.url || "");
    if (!/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(url) &&
        !/^https:\/\/[a-z0-9-]+\.onrender\.com\//i.test(url)) {
      sendResponse({ ok: false, status: 0, body: null, error: "URL not allowed" });
      return true;
    }

    const opts = { method: message.method || "GET" };
    if (message.headers) opts.headers = message.headers;
    if (message.body) opts.body = message.body;

    fetch(url, opts)
      .then(async (resp) => {
        const body = await resp.text();
        sendResponse({ ok: resp.ok, status: resp.status, body });
      })
      .catch((err) => {
        sendResponse({ ok: false, status: 0, body: null, error: err.message });
      });
    return true; // reponse async
  }

  // ── Recherche API LBC via MAIN world ──────────────────────
  // L'API LBC (api.leboncoin.fr/finder/search) exige les cookies
  // de session de l'utilisateur. Seul un fetch execute dans le
  // contexte MAIN de la page LBC peut les envoyer (credentials: "include").
  if (message.action === "lbc_api_search") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse({ ok: false, error: "no tab id" });
      return true;
    }

    chrome.scripting
      .executeScript({
        target: { tabId },
        world: "MAIN",
        func: async (bodyStr) => {
          try {
            const resp = await fetch("https://api.leboncoin.fr/finder/search", {
              method: "POST",
              credentials: "include",
              headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
              },
              body: bodyStr,
            });
            if (!resp.ok) return { ok: false, status: resp.status };
            const data = await resp.json();
            return { ok: true, data };
          } catch (e) {
            return { ok: false, error: e.message };
          }
        },
        args: [message.body],
      })
      .then((results) => {
        const result = results?.[0]?.result;
        sendResponse(result || { ok: false, error: "no result from MAIN world" });
      })
      .catch((err) => {
        sendResponse({ ok: false, error: err.message });
      });

    return true;
  }

  // ── Fetch HTML La Centrale via MAIN world ─────────────────
  // Meme principe que LBC : le fetch doit se faire dans le
  // contexte de la page pour garder les cookies anti-bot.
  if (message.action === "lc_listing_fetch") {
    const tabId = sender.tab?.id;
    if (!tabId) {
      sendResponse({ ok: false, error: "no tab id" });
      return true;
    }

    chrome.scripting
      .executeScript({
        target: { tabId },
        world: "MAIN",
        func: async (url) => {
          try {
            const resp = await fetch(url, {
              credentials: "include",
              headers: { Accept: "text/html" },
            });
            const body = await resp.text();
            return { ok: resp.ok, status: resp.status, body };
          } catch (e) {
            return { ok: false, error: e.message };
          }
        },
        args: [message.url],
      })
      .then((results) => {
        const result = results?.[0]?.result;
        sendResponse(result || { ok: false, error: "no result from MAIN world" });
      })
      .catch((err) => {
        sendResponse({ ok: false, error: err.message });
      });

    return true;
  }

  // ── Injection content script (popup -> background) ────────
  // C'est ici que tout demarre : le popup demande d'injecter
  // le content script dans l'onglet actif.
  if (message.action !== "inject_and_analyze") return false;

  const tabId = message.tabId;

  // Pipeline d'injection en 3 etapes :
  // 1. Extraire les donnees JS du site (MAIN world) et les stocker dans le DOM
  //    pour que le content script puisse les lire (il n'a pas acces au MAIN world)
  // 2. Injecter le CSS
  // 3. Injecter le bundle JS du content script
  chrome.scripting
    .executeScript({
      target: { tabId },
      world: "MAIN",
      func: () => {
        const host = window.location.hostname;
        const isLBC = host.includes("leboncoin.fr");
        const isLC = host.includes("lacentrale.fr");

        // LBC : on extrait __NEXT_DATA__ (le blob JSON de Next.js avec toutes
        // les donnees de l'annonce) et on le cache dans un div invisible
        if (isLBC) {
          let el = document.getElementById("__okazcar_next_data__");
          if (!el) {
            el = document.createElement("div");
            el.id = "__okazcar_next_data__";
            el.style.display = "none";
            document.documentElement.appendChild(el);
          }
          el.textContent = JSON.stringify(window.__NEXT_DATA__ || null);
        }

        // La Centrale : on extrait la galerie d'images et les variables
        // de tracking (tc_vars contient les specs du vehicule)
        if (isLC) {
          let lcEl = document.getElementById("__okazcar_lc_gallery__");
          if (!lcEl) {
            lcEl = document.createElement("div");
            lcEl.id = "__okazcar_lc_gallery__";
            lcEl.style.display = "none";
            document.documentElement.appendChild(lcEl);
          }
          lcEl.textContent = JSON.stringify(window.CLASSIFIED_GALLERY || null);

          let tcEl = document.getElementById("__okazcar_lc_tcvars__");
          if (!tcEl) {
            tcEl = document.createElement("div");
            tcEl.id = "__okazcar_lc_tcvars__";
            tcEl.style.display = "none";
            document.documentElement.appendChild(tcEl);
          }
          tcEl.textContent = JSON.stringify(window.tc_vars || null);
        }
      },
    })
    .then(() =>
      chrome.scripting.insertCSS({ target: { tabId }, files: ["content.css"] })
    )
    .then(() =>
      chrome.scripting.executeScript({
        target: { tabId },
        files: ["dist/content.bundle.js"],
      })
    )
    .then(() => {
      sendResponse({ ok: true });
    })
    .catch((err) => {
      sendResponse({ ok: false, error: err.message });
    });

  // return true = on va repondre de maniere asynchrone (via sendResponse)
  return true;
});
