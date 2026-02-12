/**
 * Co-Pilot Background Service Worker
 *
 * Gere l'injection on-demand du content script.
 * Rien ne s'execute tant que l'utilisateur ne le demande pas.
 */

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action !== "inject_and_analyze") return false;

  const tabId = message.tabId;

  // Injecter le CSS puis le JS sur l'onglet actif
  chrome.scripting
    .insertCSS({ target: { tabId }, files: ["content.css"] })
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
