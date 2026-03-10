"use strict";

export const DEFAULT_ANALYZE_URL = "http://localhost:5001/api/analyze";

/**
 * Utilities for dealing with the backend API URL in the extension.
 *
 * Historically, the extension expects an "analyze" endpoint:
 *   https://<host>/api/analyze
 *
 * But release builds can accidentally inject only the base origin:
 *   https://<host>
 *
 * These helpers normalize the input and safely build other endpoints
 * relative to the /api prefix.
 */

/**
 * Normalize a user/build-provided URL into an /api/analyze endpoint.
 * Accepts:
 * - https://host           -> https://host/api/analyze
 * - https://host/api       -> https://host/api/analyze
 * - https://host/api/analyze (unchanged)
 * - http://localhost:5001/api/analyze (unchanged)
 *
 * @param {unknown} input
 * @param {string} fallbackAnalyzeUrl
 * @returns {string}
 */
export function normalizeAnalyzeApiUrl(input, fallbackAnalyzeUrl) {
  const raw = String(input || "").trim();
  if (!raw) return fallbackAnalyzeUrl;

  const trimmed = raw.replace(/\/+$/g, "");

  // Already points to analyze
  if (/\/api\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/analyze$/i.test(trimmed)) return trimmed;

  // Points to /api
  if (/\/api$/i.test(trimmed)) return trimmed + "/analyze";

  // Base origin (or any other path): append /api/analyze
  return trimmed + "/api/analyze";
}

/**
 * Build a backend endpoint URL from the analyze URL.
 *
 * @param {string} analyzeUrl - normalized or not
 * @param {string} apiPath - path under /api, e.g. "/market-prices/next-job"
 * @param {string} fallbackAnalyzeUrl
 * @returns {string}
 */
export function apiEndpointFromAnalyzeUrl(analyzeUrl, apiPath, fallbackAnalyzeUrl) {
  const normalized = normalizeAnalyzeApiUrl(analyzeUrl, fallbackAnalyzeUrl);
  const base = normalized.replace(/\/analyze$/i, "");
  const path = apiPath.startsWith("/") ? apiPath : "/" + apiPath;
  return base + path;
}
