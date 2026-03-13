"use strict";

/**
 * Construction de ranges pour les filtres de recherche LBC.
 *
 * Quand on cherche des annonces similaires pour comparer les prix,
 * on ne veut pas un match exact mais une fourchette raisonnable.
 * Ces fonctions calculent les bornes selon le vehicule analyse.
 */

/**
 * Calcule le range de puissance (CV/ch) pour la recherche.
 * On prend +-5 ch — assez large pour avoir des resultats,
 * assez serre pour rester pertinent.
 *
 * @param {number} hp - Puissance en chevaux
 * @returns {string|null} Range au format "min-max", ou null si invalide
 */
export function getHpRange(hp) {
  if (!hp || hp <= 0) return null;
  const low = Math.max(0, hp - 5);
  const high = hp + 5;
  return `${low}-${high}`;
}

/**
 * Calcule le range de kilometrage pour la recherche.
 * Les tranches sont larges et asymetriques parce que le marche
 * se segmente naturellement par paliers (< 20k, < 50k, etc.).
 * Plus le km est eleve, plus la fourchette est large.
 *
 * @param {number} km - Kilometrage du vehicule
 * @returns {string|null} Range au format "min-max", ou null si invalide
 */
export function getMileageRange(km) {
  if (!km || km <= 0) return null;
  if (km <= 10000) return "min-20000";
  if (km <= 30000) return "min-50000";
  if (km <= 60000) return "20000-80000";
  if (km <= 120000) return "50000-150000";
  return "100000-max";
}

/**
 * Parse un range string en objet {from, to}.
 * Les bornes speciales "min" et "max" sont omises du resultat
 * pour signifier "pas de borne".
 *
 * @param {string} rangeStr - Ex: "170-260", "min-90", "340-max"
 * @returns {{from?: number, to?: number}} Bornes parsees
 */
export function parseRange(rangeStr) {
  if (!rangeStr) return {};
  const parts = rangeStr.split('-');
  if (parts.length !== 2) return {};
  const result = {};
  if (parts[0] !== 'min') result.from = parseInt(parts[0], 10);
  if (parts[1] !== 'max') result.to = parseInt(parts[1], 10);
  return result;
}
