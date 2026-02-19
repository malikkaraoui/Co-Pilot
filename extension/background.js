/**
 * Co-Pilot Background Service Worker
 *
 * Gere l'injection on-demand du content script
 * et les appels API LBC en contexte MAIN world.
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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
        files: ["content.js"],
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
