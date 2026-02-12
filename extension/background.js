/**
 * Co-Pilot Background Service Worker
 *
 * Gere l'injection on-demand du content script.
 * Rien ne s'execute tant que l'utilisateur ne le demande pas.
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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
