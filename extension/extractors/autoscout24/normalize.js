"use strict";

import {
  TLD_TO_COUNTRY, TLD_TO_CURRENCY, TLD_TO_COUNTRY_CODE,
} from './constants.js';
import { getCantonFromZip, mapFuelType, mapTransmission } from './helpers.js';
import { extractTld } from './search.js';

function _extractFuelToken(value, depth = 0) {
  if (depth > 5 || value == null) return null;

  if (typeof value === 'string') {
    const v = value.trim();
    return v || null;
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found = _extractFuelToken(item, depth + 1);
      if (found) return found;
    }
    return null;
  }

  if (typeof value === 'object') {
    const priorityKeys = [
      'label', 'name', 'value', 'type', 'text', 'displayValue',
      'fuelType', 'fuel', 'raw', 'slug',
    ];
    for (const key of priorityKeys) {
      if (key in value) {
        const found = _extractFuelToken(value[key], depth + 1);
        if (found) return found;
      }
    }

    for (const v of Object.values(value)) {
      const found = _extractFuelToken(v, depth + 1);
      if (found) return found;
    }
  }

  return null;
}

/** Extract 4-digit year from a date string like "2021-11-01" or "2021". */
export function _yearFromDate(dateStr) {
  if (!dateStr) return null;
  const m = String(dateStr).match(/^(\d{4})/);
  return m ? m[1] : dateStr;
}

/** Compute days since a given ISO date string. */
export function _daysOnline(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return null;
  return Math.max(Math.floor((Date.now() - d.getTime()) / 86_400_000), 0);
}

/** Compute days since last refresh (index_date). */
export function _daysSinceRefresh(createdStr, modifiedStr) {
  if (!createdStr || !modifiedStr) return null;
  const modified = new Date(modifiedStr);
  if (Number.isNaN(modified.getTime())) return null;
  return Math.max(Math.floor((Date.now() - modified.getTime()) / 86_400_000), 0);
}

/** Detect republication: created and modified differ by > 1 day. */
export function _isRepublished(createdStr, modifiedStr) {
  if (!createdStr || !modifiedStr) return false;
  const created = new Date(createdStr);
  const modified = new Date(modifiedStr);
  if (Number.isNaN(created.getTime()) || Number.isNaN(modified.getTime())) return false;
  return Math.abs(modified.getTime() - created.getTime()) > 86_400_000;
}

export function normalizeToAdData(rsc, jsonLd) {
  const ld = jsonLd || {};
  const offers = ld.offers || {};
  const seller = offers.seller || offers.offeredBy || {};
  const sellerAddress = seller.address || {};
  const rawEngine = ld.vehicleEngine || {};
  const engine = Array.isArray(rawEngine) ? (rawEngine[0] || {}) : rawEngine;

  function resolveOwnerType() {
    if (rsc && rsc.sellerId) return 'pro';
    if (seller['@type'] === 'AutoDealer') return 'pro';
    return 'private';
  }

  function resolveMake() {
    if (rsc) {
      const m = typeof rsc.make === 'string' ? rsc.make : rsc.make?.name;
      if (m) return m;
    }
    return ld.brand?.name || (typeof ld.brand === 'string' ? ld.brand : null) || ld.manufacturer || null;
  }
  function resolveModel() {
    if (rsc) {
      const m = typeof rsc.model === 'string' ? rsc.model : rsc.model?.name;
      if (m) return m;
    }
    return ld.model || null;
  }

  function resolveDescription() {
    if (rsc) {
      const full = typeof rsc.description === 'string' ? rsc.description.trim() : '';
      if (full) return full;
      const short = typeof rsc.teaser === 'string' ? rsc.teaser.trim() : '';
      if (short) return short;
    }
    const ldDesc = typeof ld.description === 'string' ? ld.description.trim() : '';
    if (ldDesc) return ldDesc;
    return null;
  }

  function resolveFuel() {
    const rscCandidates = [
      rsc?.fuelType,
      rsc?.fuel,
      rsc?.fuel?.type,
      rsc?.fuel?.name,
      rsc?.fuelCategory,
      rsc?.energySource,
      rsc?.vehicleFuelType,
    ];

    for (const candidate of rscCandidates) {
      const token = _extractFuelToken(candidate);
      if (token) {
        return mapFuelType(token);
      }
    }

    const ldFuel = _extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType) || null;
    return ldFuel ? mapFuelType(ldFuel) : null;
  }

  const rating = seller.aggregateRating || {};
  const dealerRating = rating.ratingValue ?? null;
  const dealerReviewCount = rating.reviewCount ?? null;

  const zipcode = sellerAddress.postalCode || null;
  const tld = typeof window !== 'undefined' ? extractTld(window.location.href) : null;
  const countryCode = tld ? (TLD_TO_COUNTRY_CODE[tld] || null) : null;
  const derivedRegion = (tld === 'ch' && zipcode)
    ? getCantonFromZip(zipcode)
    : (tld ? (TLD_TO_COUNTRY[tld] || null) : null);

  const resolvedCurrency = offers.priceCurrency
    || (tld ? (TLD_TO_CURRENCY[tld] || null) : null)
    || null;

  if (rsc) {
    return {
      title: rsc.versionFullName || ld.name || null,
      price_eur: rsc.price ?? offers.price ?? null,
      currency: resolvedCurrency,
      make: resolveMake(),
      model: resolveModel(),
      year_model: rsc.firstRegistrationYear || ld.vehicleModelDate || _yearFromDate(ld.productionDate) || null,
      mileage_km: rsc.mileage ?? ld.mileageFromOdometer?.value ?? null,
      fuel: resolveFuel(),
      gearbox: rsc.transmissionType
        ? mapTransmission(rsc.transmissionType)
        : (ld.vehicleTransmission || null),
      doors: rsc.doors ?? ld.numberOfDoors ?? null,
      seats: rsc.seats ?? ld.vehicleSeatingCapacity ?? ld.seatingCapacity ?? null,
      first_registration: rsc.firstRegistrationDate || ld.productionDate || null,
      color: rsc.bodyColor || ld.color || null,
      power_fiscal_cv: null,
      power_din_hp: rsc.horsePower ?? (Array.isArray(engine.enginePower) ? engine.enginePower[0]?.value : engine.enginePower?.value) ?? null,
      country: countryCode,
      location: {
        city: sellerAddress.addressLocality || null,
        zipcode,
        department: null,
        region: derivedRegion,
        lat: null,
        lng: null,
      },
      phone: seller.telephone || null,
      description: resolveDescription(),
      owner_type: resolveOwnerType(),
      owner_name: seller.name || null,
      siret: null,
      dealer_rating: dealerRating,
      dealer_review_count: dealerReviewCount,
      raw_attributes: {},
      image_count: Array.isArray(rsc.images) && rsc.images.length > 0
        ? rsc.images.length
        : (Array.isArray(ld.image) ? ld.image.length : 0),
      has_phone: Boolean(seller.telephone),
      has_urgent: false,
      has_highlight: false,
      has_boost: false,
      publication_date: rsc.createdDate || null,
      days_online: _daysOnline(rsc.createdDate),
      index_date: rsc.lastModifiedDate || null,
      days_since_refresh: _daysSinceRefresh(rsc.createdDate, rsc.lastModifiedDate),
      republished: _isRepublished(rsc.createdDate, rsc.lastModifiedDate),
      lbc_estimation: null,
    };
  }

  // JSON-LD only (no RSC)
  return {
    title: ld.name || null,
    price_eur: offers.price ?? null,
    currency: resolvedCurrency,
    make: ld.brand?.name || ld.manufacturer || null,
    model: ld.model || null,
    year_model: ld.vehicleModelDate || _yearFromDate(ld.productionDate) || null,
    mileage_km: ld.mileageFromOdometer?.value ?? null,
    fuel: (_extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType))
      ? mapFuelType(_extractFuelToken(engine.fuelType) || _extractFuelToken(ld.fuelType))
      : null,
    gearbox: ld.vehicleTransmission || null,
    doors: ld.numberOfDoors ?? null,
    seats: ld.vehicleSeatingCapacity ?? ld.seatingCapacity ?? null,
    first_registration: ld.productionDate || null,
    color: ld.color || null,
    power_fiscal_cv: null,
    power_din_hp: (Array.isArray(engine.enginePower) ? engine.enginePower[0]?.value : engine.enginePower?.value) ?? null,
    country: countryCode,
    location: {
      city: sellerAddress.addressLocality || null,
      zipcode,
      department: null,
      region: derivedRegion,
      lat: null,
      lng: null,
    },
    phone: seller.telephone || null,
    description: (typeof ld.description === 'string' && ld.description.trim()) || null,
    owner_type: resolveOwnerType(),
    owner_name: seller.name || null,
    siret: null,
    dealer_rating: dealerRating,
    dealer_review_count: dealerReviewCount,
    raw_attributes: {},
    image_count: Array.isArray(ld.image) ? ld.image.length : 0,
    has_phone: Boolean(seller.telephone),
    has_urgent: false,
    has_highlight: false,
    has_boost: false,
    publication_date: null,
    days_online: null,
    index_date: null,
    days_since_refresh: null,
    republished: false,
    lbc_estimation: null,
  };
}

export function buildBonusSignals(rsc, jsonLd) {
  const signals = [];
  if (!rsc) return signals;

  if (typeof rsc.hadAccident === 'boolean') {
    signals.push({
      label: 'Accident',
      value: rsc.hadAccident ? 'Oui' : 'Non',
      status: rsc.hadAccident ? 'fail' : 'pass',
    });
  }

  if (typeof rsc.inspected === 'boolean') {
    signals.push({
      label: 'CT',
      value: rsc.inspected ? 'Passe' : 'Non communique',
      status: rsc.inspected ? 'pass' : 'warning',
    });
  }

  if (rsc.warranty && rsc.warranty.duration) {
    signals.push({
      label: 'Garantie',
      value: `${rsc.warranty.duration} mois / ${rsc.warranty.mileage || '?'} km`,
      status: 'pass',
    });
  }

  if (rsc.listPrice && rsc.price) {
    signals.push({
      label: 'Prix catalogue',
      value: `${rsc.listPrice} EUR`,
      status: 'info',
    });
    const decote = Math.round((1 - rsc.price / rsc.listPrice) * 100);
    signals.push({
      label: 'Decote',
      value: `${decote}%`,
      status: 'info',
    });
  }

  const ld = jsonLd || {};
  const seller = ld.offers?.seller || ld.offers?.offeredBy || {};
  const rating = seller.aggregateRating;
  if (rating && rating.ratingValue) {
    signals.push({
      label: 'Note Google',
      value: `${rating.ratingValue}/5 (${rating.reviewCount} avis)`,
      status: 'info',
    });
  }

  if (rsc.directImport === true) {
    signals.push({
      label: 'Import',
      value: 'Import direct',
      status: 'warning',
    });
  }

  return signals;
}
