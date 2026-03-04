"use strict";

/** Normalise un nom de marque pour comparaison (minuscule, sans accent, sans tiret). */
export function normalizeBrand(brand) {
  if (!brand) return '';
  return brand.toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[-_]/g, ' ')
    .trim();
}

/** Verifie si la marque d'une annonce correspond a la marque cible. */
export function brandsMatch(adBrand, targetMake) {
  if (!adBrand || !targetMake) return true;
  const a = normalizeBrand(adBrand);
  const t = normalizeBrand(targetMake);
  if (!a || !t) return true;
  if (a === t) return true;
  if ((a === 'vw' && t === 'volkswagen') || (a === 'volkswagen' && t === 'vw')) return true;
  if (a.startsWith('mercedes') && t.startsWith('mercedes')) return true;
  if (a.includes(t) || t.includes(a)) return true;
  return false;
}
