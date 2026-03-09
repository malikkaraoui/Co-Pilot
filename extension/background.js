/**
 * OKazCar Background Service Worker
 *
 * Gere l'injection on-demand du content script,
 * les appels API LBC en contexte MAIN world,
 * et le proxy des appels backend (HTTP localhost depuis HTTPS).
 */

// ── Icone adaptative dark/light mode ────────────────────────
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

// Au demarrage, restaurer la preference stockee
chrome.storage.local.get("isDarkMode", (result) => {
  if (result.isDarkMode != null) updateIcon(result.isDarkMode);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // ── Mise a jour icone dark/light depuis popup ou content ──
  if (message.action === "update_icon_theme") {
    updateIcon(message.isDark);
    chrome.storage.local.set({ isDarkMode: message.isDark });
    return false;
  }

  // ── Proxy backend API (content script → background → localhost) ─
  // Chrome MV3 : un content script sur une page HTTPS ne peut pas
  // fetch vers HTTP localhost (mixed-content). Le service worker
  // n'a pas cette restriction.
  if (message.action === "backend_fetch") {
    // Securite : seul le backend local est autorise via le proxy
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
    return true;
  }

  // ── Recherche API LBC (content script → MAIN world) ──────────
  // Le content script ne peut pas appeler l'API LBC directement
  // (CORS + session cookies). On injecte le fetch dans le contexte
  // MAIN de la page (meme session que le JavaScript LBC).
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

  // ── Fetch HTML La Centrale depuis le MAIN world ──────────────
  // Le fetch direct depuis le content script peut perdre le contexte
  // anti-bot / cookies de premiere partie. On execute donc la requete
  // dans le monde de la page, comme pour Leboncoin.
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

  // ── Injection content script (popup → background) ────────────
  if (message.action !== "inject_and_analyze") return false;

  const tabId = message.tabId;

  // Etape 1 : Lire window.__NEXT_DATA__ dans le contexte MAIN (contourne le CSP)
  // Etape 2 : Injecter le CSS puis le content script
  chrome.scripting
    .executeScript({
      target: { tabId },
      world: "MAIN",
      func: () => {
        const host = window.location.hostname;
        const isLBC = host.includes("leboncoin.fr");
        const isLC = host.includes("lacentrale.fr");

        // LeBonCoin: __NEXT_DATA__ (skip on other sites — can be huge)
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

        // La Centrale: CLASSIFIED_GALLERY + tc_vars (skip on other sites)
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

  // Retourner true pour indiquer une reponse asynchrone
  return true;
});
