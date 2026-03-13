"use strict";

/**
 * Utilitaires de normalisation de l'URL backend.
 *
 * Le build esbuild injecte __API_URL__ qui peut etre :
 * - l'URL complete (https://host/api/analyze)
 * - juste l'origin (https://host)
 * - ou rien du tout en dev (fallback localhost)
 *
 * Ces helpers s'assurent qu'on a toujours une URL valide
 * et permettent de construire d'autres endpoints a partir
 * de l'URL d'analyze.
 */

export const DEFAULT_ANALYZE_URL = "http://localhost:5001/api/analyze";

/**
 * Normalise une URL brute en endpoint /api/analyze.
 * Gere tous les cas : URL complete, partielle, ou vide.
 *
 * @param {unknown} input - URL brute (peut etre null/undefined/string)
 * @param {string} fallbackAnalyzeUrl - URL de fallback si input est vide
 * @returns {string} URL normalisee pointant vers /api/analyze
 *
 * @example
 * normalizeAnalyzeApiUrl("https://host")            // -> "https://host/api/analyze"
 * normalizeAnalyzeApiUrl("https://host/api")         // -> "https://host/api/analyze"
 * normalizeAnalyzeApiUrl("https://host/api/analyze") // -> inchange
 * normalizeAnalyzeApiUrl(null, "http://localhost:5001/api/analyze") // -> fallback
 */
export function normalizeAnalyzeApiUrl(input, fallbackAnalyzeUrl) {
  const raw = String(input || "").trim();
  if (!raw) return fallbackAnalyzeUrl;

  const trimmed = raw.replace(/\/+$/g, "");

  // Deja complet — on touche a rien
  if (/\/api\/analyze$/i.test(trimmed)) return trimmed;
  if (/\/analyze$/i.test(trimmed)) return trimmed;

  // Pointe vers /api mais sans /analyze
  if (/\/api$/i.test(trimmed)) return trimmed + "/analyze";

  // Juste l'origin ou un path quelconque — on ajoute tout
  return trimmed + "/api/analyze";
}

/**
 * Construit un endpoint backend a partir de l'URL d'analyze.
 * On remplace /analyze par le path souhaite.
 * Utile pour appeler d'autres routes comme /market-prices/next-job
 * sans dupliquer la logique de resolution d'URL.
 *
 * @param {string} analyzeUrl - URL d'analyze (normalisee ou non)
 * @param {string} apiPath - Chemin sous /api (ex: "/market-prices/next-job")
 * @param {string} fallbackAnalyzeUrl - Fallback si analyzeUrl est vide
 * @returns {string} URL complete de l'endpoint
 */
export function apiEndpointFromAnalyzeUrl(analyzeUrl, apiPath, fallbackAnalyzeUrl) {
  const normalized = normalizeAnalyzeApiUrl(analyzeUrl, fallbackAnalyzeUrl);
  // On retire /analyze pour obtenir la base /api
  const base = normalized.replace(/\/analyze$/i, "");
  const path = apiPath.startsWith("/") ? apiPath : "/" + apiPath;
  return base + path;
}
