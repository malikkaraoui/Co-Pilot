"use strict";

/**
 * Normalisation et comparaison de noms de marques automobiles.
 *
 * On a besoin de comparer des marques venant de sources differentes
 * (LBC, La Centrale, backend) qui ne formatent pas pareil.
 * Ex: "MERCEDES-BENZ" vs "Mercedes Benz" vs "mercedes".
 */

/**
 * Normalise un nom de marque pour comparaison.
 * On passe en minuscule, on vire les accents et les tirets
 * pour que "CITROEN" == "citroen" et "Mercedes-Benz" == "mercedes benz".
 *
 * @param {string} brand - Nom de marque brut
 * @returns {string} Nom normalise (minuscule, sans accent, sans tiret)
 */
export function normalizeBrand(brand) {
  if (!brand) return '';
  return brand.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[-_]/g, ' ')
    .trim();
}

/**
 * Verifie si la marque d'une annonce correspond a la marque cible.
 * Tolerant : si l'une des deux est vide, on considere que ca match
 * (pas assez d'info pour rejeter). Gere aussi les alias courants
 * comme VW/Volkswagen et les variantes Mercedes.
 *
 * @param {string} adBrand - Marque telle qu'affichee dans l'annonce
 * @param {string} targetMake - Marque cible (depuis le vehicule analyse)
 * @returns {boolean} true si les marques correspondent (ou si on ne peut pas comparer)
 */
export function brandsMatch(adBrand, targetMake) {
  if (!adBrand || !targetMake) return true;
  const a = normalizeBrand(adBrand);
  const t = normalizeBrand(targetMake);
  if (!a || !t) return true;
  if (a === t) return true;
  // VW est systematiquement utilise comme raccourci de Volkswagen sur LBC
  if ((a === 'vw' && t === 'volkswagen') || (a === 'volkswagen' && t === 'vw')) return true;
  // Mercedes a plein de variantes (Mercedes-Benz, Mercedes, Mercedes AMG...)
  if (a.startsWith('mercedes') && t.startsWith('mercedes')) return true;
  // Fallback : inclusion partielle (ex: "bmw" dans "bmw alpina")
  if (a.includes(t) || t.includes(a)) return true;
  return false;
}
