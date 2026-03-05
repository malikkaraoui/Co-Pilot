"use strict";

import { getHpRange } from '../../shared/ranges.js';
import {
  SWISS_ZIP_TO_CANTON, FUEL_MAP, TRANSMISSION_MAP,
  AS24_GEAR_MAP, AS24_FUEL_CODE_MAP, CANTON_CENTER_ZIP,
} from './constants.js';

export function getCantonFromZip(zipcode) {
  const zip = String(zipcode || '').trim();
  if (zip.length < 4) return null;
  const prefix = zip.slice(0, 2);
  return SWISS_ZIP_TO_CANTON[prefix] || null;
}

export function mapFuelType(fuelType) {
  const raw = typeof fuelType === 'string' ? fuelType : String(fuelType || '');
  if (!raw.trim()) return null;
  const key = raw
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .trim();

  const hasElectric = key.includes('electri') || key.includes('elektrycz');
  const hasGasoline = key.includes('gasoline')
    || key.includes('benzin')
    || key.includes('benzine')
    || key.includes('benzyn')
    || key.includes('essence')
    || key.includes('petrol')
    || key.includes('gasolina');
  const hasDiesel = key.includes('diesel') || key.includes('gazole') || (key.includes('olej') && key.includes('naped'));

  if (FUEL_MAP[key]) return FUEL_MAP[key];

  // Mixed electric + thermal labels should stay in hybrid family.
  if (hasElectric && (hasGasoline || hasDiesel)) return 'Hybride Rechargeable';

  // Hybrid must be checked before gasoline/diesel keyword matching.
  if (key.includes('plug') && key.includes('hybrid')) return 'Hybride Rechargeable';
  if (key.includes('phev')) return 'Hybride Rechargeable';

  if (hasDiesel) return 'Diesel';

  if (hasGasoline) return 'Essence';

  if (key.includes('hybrid') || key.includes('hybride') || key.includes('hybryd')) return 'Hybride';
  if (key.includes('electri') || key.includes('elektrycz')) return 'Electrique';
  if (key.includes('cng') || key.includes('gnv')) return 'GNV';
  if (key.includes('lpg') || key.includes('gpl')) return 'GPL';

  return raw.length > 50 ? raw.slice(0, 50) : raw;
}

export function mapTransmission(transmission) {
  const key = (transmission || '').toLowerCase();
  return TRANSMISSION_MAP[key] || transmission;
}

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

export function getAs24FuelCode(fuel) {
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

  // Already an AS24 fuel code (can happen in some payload variants).
  if (/^[bdeclh]$/.test(key)) return key.toUpperCase();
  if (key === '2' || key === '3') return key;

  if (AS24_FUEL_CODE_MAP[key]) return AS24_FUEL_CODE_MAP[key];
  if (AS24_FUEL_CODE_MAP[compact]) return AS24_FUEL_CODE_MAP[compact];

  // Common mixed labels used by AS24 UI, e.g. "Electrique/Essence" or "Electrique/Diesel".
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

export function getAs24PowerParams(hp) {
  if (!hp || hp <= 0) return {};
  if (hp < 80)  return { powerto: 90 };
  if (hp < 110) return { powerfrom: 70, powerto: 120 };
  if (hp < 140) return { powerfrom: 100, powerto: 150 };
  if (hp < 180) return { powerfrom: 130, powerto: 190 };
  if (hp < 250) return { powerfrom: 170, powerto: 260 };
  if (hp < 350) return { powerfrom: 240, powerto: 360 };
  return { powerfrom: 340 };
}

export function getAs24KmParams(km) {
  if (!km || km <= 0) return {};
  if (km <= 10000) return { kmto: 20000 };
  if (km <= 30000) return { kmto: 50000 };
  if (km <= 60000) return { kmfrom: 20000, kmto: 80000 };
  if (km <= 120000) return { kmfrom: 50000, kmto: 150000 };
  return { kmfrom: 100000 };
}

/** @see shared/ranges.js — re-export for backward compatibility. */
export const getHpRangeString = getHpRange;

export function parseHpRange(hpRange) {
  if (!hpRange) return {};
  const parts = hpRange.split('-');
  if (parts.length !== 2) return {};
  const result = {};
  if (parts[0] !== 'min') result.powerfrom = parseInt(parts[0], 10);
  if (parts[1] !== 'max') result.powerto = parseInt(parts[1], 10);
  return result;
}

export function getCantonCenterZip(canton) {
  return CANTON_CENTER_ZIP[canton] || null;
}
