/**
 * Utilitaires fetch pour le contexte extension Chrome.
 *
 * Probleme central : un content script sur une page HTTPS ne peut pas
 * fetch vers HTTP localhost (mixed-content bloque par le navigateur).
 * La solution : proxyer les requetes via chrome.runtime.sendMessage
 * vers le service worker (background.js) qui, lui, n'a pas cette restriction.
 *
 * Si le runtime Chrome n'est pas dispo (tests, contexte invalide),
 * on fallback sur un fetch direct.
 */

"use strict";

/**
 * Verifie si le runtime Chrome est disponible et fonctionnel.
 * Peut renvoyer false si l'extension a ete rechargee/desinstallee
 * pendant que la page etait ouverte (context invalidated).
 *
 * @returns {boolean}
 */
export function isChromeRuntimeAvailable() {
  try {
    return (
      typeof chrome !== "undefined"
      && !!chrome.runtime
      && typeof chrome.runtime.sendMessage === "function"
    );
  } catch {
    return false;
  }
}

/**
 * Detecte si l'URL pointe vers un backend local (localhost / 127.0.0.1).
 * Utilise pour savoir si on est en dev et adapter le comportement d'erreur.
 *
 * @param {string} url
 * @returns {boolean}
 */
export function isLocalBackendUrl(url) {
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
}

/**
 * Detecte les erreurs "benignes" liees au cycle de vie de l'extension.
 * Ces erreurs arrivent quand l'extension est rechargee en dev ou
 * quand le service worker est detruit — pas grave, on ignore.
 *
 * @param {Error|string} err
 * @returns {boolean}
 */
export function isBenignRuntimeTeardownError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return msg.includes("extension context invalidated")
    || msg.includes("runtime_unavailable_for_local_backend")
    || msg.includes("receiving end does not exist");
}

/**
 * Promise-based sleep. Utilise pour les retries avec delai.
 *
 * @param {number} ms - Duree en millisecondes
 * @returns {Promise<void>}
 */
export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Decode une payload base64 en Uint8Array de maniere compatible navigateur/tests.
 *
 * @param {string} base64
 * @returns {Uint8Array}
 */
function decodeBase64ToBytes(base64) {
  if (typeof atob === "function") {
    const binary = atob(base64);
    return Uint8Array.from(binary, (char) => char.charCodeAt(0));
  }

  if (typeof Buffer !== "undefined") {
    return Uint8Array.from(Buffer.from(base64, "base64"));
  }

  throw new Error("Base64 decode unavailable");
}

/**
 * Fetch vers le backend, en passant par le service worker si necessaire.
 *
 * Strategie en 3 niveaux :
 * 1. Si pas de runtime Chrome -> fetch direct (mode test / hors extension)
 * 2. Si runtime dispo -> proxy via sendMessage("backend_fetch")
 * 3. Si le proxy echoue -> fallback fetch direct (dernier recours)
 *
 * Retourne un objet compatible avec l'API Response (ok, status, json(), text())
 * mais simplifie — c'est pas une vraie Response, juste ce dont on a besoin.
 *
 * @param {string} url - URL du backend
 * @param {RequestInit} options - Options fetch standard (method, headers, body)
 * @returns {Promise<{ok: boolean, status: number, json: Function, text: Function}>}
 */
export async function backendFetch(url, options = {}) {
  const isLocalBackend = isLocalBackendUrl(url);

  // Pas de runtime Chrome -> fetch direct (mode test ou page standalone)
  if (!isChromeRuntimeAvailable()) {
    try {
      return await fetch(url, options);
    } catch (err) {
      if (isLocalBackend) {
        throw new Error("runtime_unavailable_for_local_backend");
      }
      throw err;
    }
  }

  // Proxy via le service worker
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendMessage(
        {
          action: "backend_fetch",
          url,
          method: options.method || "GET",
          headers: options.headers || null,
          body: options.body || null,
        },
        (resp) => {
          // Verifier si le runtime a plante pendant l'appel
          let runtimeErrorMsg = null;
          try {
            runtimeErrorMsg = chrome.runtime?.lastError?.message || null;
          } catch (e) {
            runtimeErrorMsg = e?.message || "extension context invalidated";
          }

          // Si le proxy a echoue, on tente un fetch direct en fallback
          if (runtimeErrorMsg || !resp || resp.error) {
            fetch(url, options)
              .then(resolve)
              .catch((fallbackErr) => {
                if (isLocalBackend) {
                  reject(new Error(runtimeErrorMsg || resp?.error || fallbackErr?.message || "runtime_unavailable_for_local_backend"));
                  return;
                }
                reject(fallbackErr);
              });
            return;
          }

          // Construire un objet Response-like a partir de la reponse du proxy
          const textBody = typeof resp.body === "string" ? resp.body : "";
          const hasBinaryBody = typeof resp.bodyBase64 === "string" && resp.bodyBase64.length > 0;
          const binaryBytes = hasBinaryBody ? decodeBase64ToBytes(resp.bodyBase64) : null;

          let parsed;
          try { parsed = JSON.parse(textBody); } catch { parsed = null; }

          resolve({
            ok: resp.ok,
            status: resp.status,
            json: async () => {
              if (parsed !== null) return parsed;
              throw new SyntaxError("Invalid JSON");
            },
            text: async () => {
              if (hasBinaryBody) {
                return new TextDecoder().decode(binaryBytes);
              }
              return textBody;
            },
            blob: async () => new Blob(
              [hasBinaryBody ? binaryBytes : textBody],
              { type: resp.contentType || "application/octet-stream" },
            ),
            arrayBuffer: async () => {
              if (hasBinaryBody) {
                return binaryBytes.buffer.slice(
                  binaryBytes.byteOffset,
                  binaryBytes.byteOffset + binaryBytes.byteLength,
                );
              }
              return new TextEncoder().encode(textBody).buffer;
            },
          });
        },
      );
    } catch (err) {
      // Derniere chance : si sendMessage plante, fetch direct
      if (isLocalBackend) {
        reject(err);
        return;
      }
      fetch(url, options).then(resolve).catch(reject);
    }
  });
}
