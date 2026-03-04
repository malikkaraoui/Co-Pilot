/**
 * Backend fetch utilities for Chrome extension context.
 *
 * Handles mixed-content (HTTP backend on HTTPS page) by proxying
 * through chrome.runtime.sendMessage when available.
 */

"use strict";

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

export function isLocalBackendUrl(url) {
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(String(url || ""));
}

export function isBenignRuntimeTeardownError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return msg.includes("extension context invalidated")
    || msg.includes("runtime_unavailable_for_local_backend")
    || msg.includes("receiving end does not exist");
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function backendFetch(url, options = {}) {
  const isLocalBackend = isLocalBackendUrl(url);

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
          let runtimeErrorMsg = null;
          try {
            runtimeErrorMsg = chrome.runtime?.lastError?.message || null;
          } catch (e) {
            runtimeErrorMsg = e?.message || "extension context invalidated";
          }

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
          let parsed;
          try { parsed = JSON.parse(resp.body); } catch { parsed = null; }
          resolve({
            ok: resp.ok,
            status: resp.status,
            json: async () => {
              if (parsed !== null) return parsed;
              throw new SyntaxError("Invalid JSON");
            },
            text: async () => resp.body,
          });
        },
      );
    } catch (err) {
      if (isLocalBackend) {
        reject(err);
        return;
      }
      fetch(url, options).then(resolve).catch(reject);
    }
  });
}
