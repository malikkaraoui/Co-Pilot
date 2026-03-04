"use strict";

/** Calcule le range de puissance (CV/ch) pour la recherche. */
export function getHpRange(hp) {
  if (!hp || hp <= 0) return null;
  if (hp < 80)  return "min-90";
  if (hp < 110) return "70-120";
  if (hp < 140) return "100-150";
  if (hp < 180) return "130-190";
  if (hp < 250) return "170-260";
  if (hp < 350) return "240-360";
  return "340-max";
}

/** Calcule le range de kilometrage pour la recherche. */
export function getMileageRange(km) {
  if (!km || km <= 0) return null;
  if (km <= 10000) return "min-20000";
  if (km <= 30000) return "min-50000";
  if (km <= 60000) return "20000-80000";
  if (km <= 120000) return "50000-150000";
  return "100000-max";
}

/** Parse un range string (e.g. '170-260', 'min-90', '340-max') en {from, to}. */
export function parseRange(rangeStr) {
  if (!rangeStr) return {};
  const parts = rangeStr.split('-');
  if (parts.length !== 2) return {};
  const result = {};
  if (parts[0] !== 'min') result.from = parseInt(parts[0], 10);
  if (parts[1] !== 'max') result.to = parseInt(parts[1], 10);
  return result;
}
