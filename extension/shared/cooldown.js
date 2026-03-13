"use strict";

/**
 * Gestion du cooldown de collecte de prix marche.
 *
 * On limite la collecte a une fois par 24h pour ne pas spammer
 * le backend et l'API LBC. Le timestamp est persiste dans
 * localStorage pour survivre aux rechargements de page.
 */

// 24h entre chaque collecte — suffisant pour avoir des prix a jour
// sans surcharger les APIs
export const COLLECT_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24h
const STORAGE_KEY = "okazcar_last_collect";

/**
 * Verifie si la derniere collecte est trop recente pour en relancer une.
 *
 * @returns {boolean} true si on doit skip (cooldown pas encore ecoule)
 */
export function shouldSkipCollection() {
  const lastCollect = parseInt(localStorage.getItem(STORAGE_KEY) || "0", 10);
  return Date.now() - lastCollect < COLLECT_COOLDOWN_MS;
}

/**
 * Enregistre le timestamp actuel comme derniere collecte.
 * A appeler apres une collecte reussie.
 */
export function markCollected() {
  localStorage.setItem(STORAGE_KEY, String(Date.now()));
}
