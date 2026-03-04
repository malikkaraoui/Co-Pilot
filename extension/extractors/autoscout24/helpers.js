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

  if (FUEL_MAP[key]) return FUEL_MAP[key];

  // Hybrid must be checked before gasoline/diesel keyword matching.
  if (key.includes('plug') && key.includes('hybrid')) return 'Hybride Rechargeable';
  if (key.includes('phev')) return 'Hybride Rechargeable';

  if (key.includes('diesel')) return 'Diesel';
  if (key.includes('gazole')) return 'Diesel';
  if (key.includes('olej') && key.includes('naped')) return 'Diesel';

  if (
    key.includes('gasoline')
    || key.includes('benzin')
    || key.includes('benzine')
    || key.includes('benzyn')
    || key.includes('essence')
    || key.includes('petrol')
    || key.includes('gasolina')
  ) return 'Essence';

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
  return AS24_GEAR_MAP[(gearbox || '').toLowerCase()] || null;
}

export function getAs24FuelCode(fuel) {
  return AS24_FUEL_CODE_MAP[(fuel || '').toLowerCase()] || null;
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
