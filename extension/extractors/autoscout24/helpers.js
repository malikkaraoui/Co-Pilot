"use strict";

/**
 * Fonctions utilitaires pour AutoScout24.
 *
 * Conversions de donnees specifiques a AS24 : canton suisse depuis le code postal,
 * normalisation carburant/boite, conversion CV→kW pour les filtres de recherche, etc.
 */

import { getHpRange } from '../../shared/ranges.js';
import {
  SWISS_ZIP_TO_CANTON, FUEL_MAP, TRANSMISSION_MAP,
  AS24_GEAR_MAP, AS24_FUEL_CODE_MAP, CANTON_CENTER_ZIP,
} from './constants.js';

/**
 * Determine le canton suisse a partir du code postal.
 * Les 2 premiers chiffres du NPA suffisent.
 *
 * @param {string} zipcode - Code postal suisse (ex: "1003")
 * @returns {string|null} Nom du canton ou null
 */
export function getCantonFromZip(zipcode) {
  const zip = String(zipcode || '').trim();
  if (zip.length < 4) return null;
  const prefix = zip.slice(0, 2);
  return SWISS_ZIP_TO_CANTON[prefix] || null;
}

/**
 * Normalise un label carburant multilingue vers un nom francais standard.
 * Gere les cas complexes : hybrides mixtes, labels concatenes, multi-langues.
 *
 * @param {string} fuelType - Label brut (ex: "gasoline", "Diesel", "phev-gasoline")
 * @returns {string|null} Label normalise ou le brut tronque si inconnu
 */
export function mapFuelType(fuelType) {
  const raw = typeof fuelType === 'string' ? fuelType : String(fuelType || '');
  if (!raw.trim()) return null;
  const key = raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim();

  // Detection des composantes pour les labels hybrides/mixtes
  const hasElectric = key.includes('electri') || key.includes('elektrycz');
  const hasGasoline = key.includes('gasoline')
    || key.includes('benzin')
    || key.includes('benzine')
    || key.includes('benzyn')
    || key.includes('essence')
    || key.includes('petrol')
    || key.includes('gasolina');
  const hasDiesel = key.includes('diesel') || key.includes('gazole') || (key.includes('olej') && key.includes('naped'));

  // Lookup direct d'abord
  if (FUEL_MAP[key]) return FUEL_MAP[key];

  // Les labels mixtes electrique + thermique doivent rester en hybride
  if (hasElectric && (hasGasoline || hasDiesel)) return 'Hybride Rechargeable';

  // L'hybride doit etre teste avant gasoline/diesel pour eviter les faux positifs
  if (key.includes('plug') && key.includes('hybrid')) return 'Hybride Rechargeable';
  if (key.includes('phev')) return 'Hybride Rechargeable';

  if (hasDiesel) return 'Diesel';
  if (hasGasoline) return 'Essence';

  if (key.includes('hybrid') || key.includes('hybride') || key.includes('hybryd')) return 'Hybride';
  if (key.includes('electri') || key.includes('elektrycz')) return 'Electrique';
  if (key.includes('cng') || key.includes('gnv')) return 'GNV';
  if (key.includes('lpg') || key.includes('gpl')) return 'GPL';

  // Si vraiment inconnu, retourner le brut (tronque si trop long)
  return raw.length > 50 ? raw.slice(0, 50) : raw;
}

/**
 * Normalise le type de transmission vers un label francais.
 * @param {string} transmission
 * @returns {string}
 */
export function mapTransmission(transmission) {
  const key = (transmission || '').toLowerCase();
  return TRANSMISSION_MAP[key] || transmission;
}

/**
 * Convertit un label de boite de vitesses en code AS24 (A/M).
 * @param {string} gearbox
 * @returns {string|null} 'A' ou 'M' ou null
 */
export function getAs24GearCode(gearbox) {
  const raw = typeof gearbox === 'string' ? gearbox : String(gearbox || '');
  if (!raw.trim()) return null;
  const key = raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim();

  if (AS24_GEAR_MAP[key]) return AS24_GEAR_MAP[key];
  if (key.includes('manual') || key.includes('manuelle') || key.includes('manuelle')) return 'M';
  if (key.includes('auto')) return 'A';
  return null;
}

/**
 * Convertit un label carburant en code de filtre AS24 (B, D, E, 2, 3...).
 * Gere les cas ou fuel peut etre un objet complexe (pas juste une string).
 *
 * @param {string|object} fuel - Label ou objet carburant
 * @returns {string|null} Code AS24 ou null
 */
export function getAs24FuelCode(fuel) {
  // Extraire une string depuis un objet si necessaire
  const raw = typeof fuel === 'string'
    ? fuel
    : (fuel && typeof fuel === 'object'
      ? (fuel.label || fuel.name || fuel.value || fuel.type || fuel.fuelType || fuel.fuel || fuel.raw || '')
      : String(fuel || ''));
  if (!raw.trim()) return null;
  const key = raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim();

  const compact = key.replace(/\s+/g, '');
  const hasElectric = /electri|elektrycz/.test(key);
  const hasGasoline = /gasoline|benzin|benzine|benzyn|essence|petrol|gasolina/.test(key);
  const hasDiesel = /diesel|gazole/.test(key) || (key.includes('olej') && key.includes('naped'));

  // Si c'est deja un code AS24 (peut arriver dans certains payloads)
  if (/^[bdeclh]$/.test(key)) return key.toUpperCase();
  if (key === '2' || key === '3') return key;

  if (AS24_FUEL_CODE_MAP[key]) return AS24_FUEL_CODE_MAP[key];
  if (AS24_FUEL_CODE_MAP[compact]) return AS24_FUEL_CODE_MAP[compact];

  // Labels mixtes de l'UI AS24 (ex: "Electrique/Essence")
  if (hasElectric && hasGasoline) return '2';
  if (hasElectric && hasDiesel) return '3';

  if (key.includes('diesel') || key.includes('gazole')) return 'D';
  if (key.includes('essence') || key.includes('gasoline') || key.includes('petrol') || key.includes('benzin')) return 'B';
  if (key.includes('electri')) return 'E';
  if (key.includes('plug') && key.includes('hybrid')) return '2';
  if (key.includes('phev')) return '2';
  if (key.includes('hybrid') || key.includes('hybride')) return '3';
  if (key.includes('gnv') || key.includes('cng')) return 'C';
  if (key.includes('gpl') || key.includes('lpg')) return 'L';
  if (key.includes('hydrogen') || key.includes('hydrogene')) return 'H';
  return null;
}

/**
 * Calcule les parametres de puissance (kW) pour le filtre AS24.
 * AS24 filtre en kW alors qu'on a la puissance en CV →  conversion ±5 CV.
 *
 * @param {number} hp - Puissance en chevaux DIN
 * @returns {{powerfrom?: number, powerto?: number}}
 */
export function getAs24PowerParams(hp) {
  if (!hp || hp <= 0) return {};
  const hpToKw = (v) => Math.round(v * 0.7355);
  const low = Math.max(0, hp - 5);
  const high = hp + 5;
  return { powerfrom: hpToKw(low), powerto: hpToKw(high) };
}

/**
 * Calcule les parametres de kilometrage pour le filtre AS24.
 * On utilise des fourchettes larges pour avoir assez de resultats.
 *
 * @param {number} km - Kilometrage du vehicule
 * @returns {{kmfrom?: number, kmto?: number}}
 */
export function getAs24KmParams(km) {
  if (!km || km <= 0) return {};
  if (km <= 10000) return { kmto: 20000 };
  if (km <= 30000) return { kmto: 50000 };
  if (km <= 60000) return { kmfrom: 20000, kmto: 80000 };
  if (km <= 120000) return { kmfrom: 50000, kmto: 150000 };
  return { kmfrom: 100000 };
}

/** Re-export de la fonction partagee pour retrocompatibilite */
export const getHpRangeString = getHpRange;

/**
 * Parse une chaine hp_range (ex: "100-150") en parametres kW pour AS24.
 * @param {string} hpRange
 * @returns {{powerfrom?: number, powerto?: number}}
 */
export function parseHpRange(hpRange) {
  if (!hpRange) return {};
  const parts = hpRange.split('-');
  if (parts.length !== 2) return {};
  const hpToKw = (v) => Math.round(v * 0.7355);
  const result = {};
  if (parts[0] !== 'min') {
    const hpMin = parseInt(parts[0], 10);
    if (Number.isFinite(hpMin)) result.powerfrom = hpToKw(hpMin);
  }
  if (parts[1] !== 'max') {
    const hpMax = parseInt(parts[1], 10);
    if (Number.isFinite(hpMax)) result.powerto = hpToKw(hpMax);
  }
  return result;
}

/**
 * Retourne le code postal du chef-lieu d'un canton suisse.
 * Utilise pour centrer les recherches geolocalisees sur AS24.ch.
 *
 * @param {string} canton - Nom du canton (ex: "Geneve")
 * @returns {string|null}
 */
export function getCantonCenterZip(canton) {
  return CANTON_CENTER_ZIP[canton] || null;
}
