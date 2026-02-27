/**
 * Co-Pilot Background Service Worker
 *
 * Gere l'injection on-demand du content script,
 * les appels API LBC en contexte MAIN world,
 * et le proxy des appels backend (HTTP localhost depuis HTTPS).
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // ── Proxy backend API (content script → background → localhost) ─
  // Chrome MV3 : un content script sur une page HTTPS ne peut pas
  // fetch vers HTTP localhost (mixed-content). Le service worker
  // n'a pas cette restriction.
  if (message.action === "backend_fetch") {
    // Securite : seul le backend local est autorise via le proxy
    const url = String(message.url || "");
    if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(url)) {
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
        let el = document.getElementById("__copilot_next_data__");
        if (!el) {
          el = document.createElement("div");
          el.id = "__copilot_next_data__";
          el.style.display = "none";
          document.documentElement.appendChild(el);
        }
        el.textContent = JSON.stringify(window.__NEXT_DATA__ || null);
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
