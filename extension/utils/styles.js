/**
 * Mapping visuel des scores et statuts de filtres.
 *
 * Fonctions pures sans side-effects — elles traduisent les statuts
 * backend (pass/warning/fail/skip) en couleurs et icones pour l'UI.
 * Les couleurs suivent la palette Tailwind (green-500, amber-500, red-500).
 */

"use strict";

/**
 * Retourne la couleur associee au score global (0-100).
 * Vert >= 70, Orange >= 40, Rouge en dessous.
 *
 * @param {number} score - Score global de l'analyse (0-100)
 * @returns {string} Code couleur hex
 */
export function scoreColor(score) {
  if (score >= 70) return "#22c55e";
  if (score >= 40) return "#f59e0b";
  return "#ef4444";
}

/**
 * Retourne la couleur associee a un statut de filtre individuel.
 *
 * @param {string} status - Statut du filtre (pass|warning|fail|skip|neutral)
 * @returns {string} Code couleur hex
 */
export function statusColor(status) {
  switch (status) {
    case "pass": return "#22c55e";
    case "warning": return "#f59e0b";
    case "fail": return "#ef4444";
    case "skip": return "#9ca3af";
    case "neutral": return "#94a3b8";
    default: return "#6b7280";
  }
}

/**
 * Retourne l'icone unicode associee a un statut de filtre.
 *
 * @param {string} status - Statut du filtre
 * @returns {string} Caractere unicode (check, warning, cross, etc.)
 */
export function statusIcon(status) {
  switch (status) {
    case "pass": return "\u2713";
    case "warning": return "\u26A0";
    case "fail": return "\u2717";
    case "skip": return "\u2014";
    case "neutral": return "\u25CB";
    default: return "?";
  }
}

/**
 * Retourne le libelle humain d'un filtre a partir de son ID.
 * Certains libelles varient selon le statut (ex: L2 passe = "Modele reconnu",
 * L2 fail = "Identification du modele").
 *
 * @param {string} filterId - Identifiant du filtre (L1, L2, ..., L11)
 * @param {string} status - Statut du filtre (pour adapter le libelle)
 * @returns {string} Libelle en francais
 */
export function filterLabel(filterId, status) {
  const labels = {
    L1: "Complétude des données",
    L2: status === "pass" ? "Modèle reconnu" : "Identification du modèle",
    L3: "Cohérence km / année",
    L4: "Prix vs marché",
    L5: "Indice de confiance",
    L6: "Téléphone",
    L7: "SIRET vendeur",
    L8: "Détection import",
    L9: "Résultat de scan",
    L10: "Ancienneté annonce",
    L11: "Rappel constructeur",
  };
  return labels[filterId] || filterId;
}
