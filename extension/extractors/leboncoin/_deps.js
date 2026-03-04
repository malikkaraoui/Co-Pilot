"use strict";

/**
 * Dependency injection container for LeBonCoin extractor modules.
 *
 * backendFetch, sleep and apiUrl live in content.js — they are injected
 * at startup via initLbcDeps() and consumed by collect, search and dom modules.
 */
export const lbcDeps = {
  backendFetch: null,
  sleep: null,
  apiUrl: null,
};

export function initLbcDeps(deps) {
  lbcDeps.backendFetch = deps.backendFetch;
  lbcDeps.sleep = deps.sleep;
  lbcDeps.apiUrl = deps.apiUrl;
}
