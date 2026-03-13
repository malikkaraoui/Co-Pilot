/**
 * Score/status visual mapping utilities.
 *
 * Pure functions — no DOM, no side-effects.
 */

"use strict";

export function scoreColor(score) {
  if (score >= 70) return "#22c55e";
  if (score >= 40) return "#f59e0b";
  return "#ef4444";
}

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
