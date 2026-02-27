/**
 * AutoScout24 Extractor
 *
 * Extrait les donnees vehicule depuis les pages d'annonces AutoScout24
 * (.ch, .de, .fr, .it, .at, .be, .nl, .es).
 *
 * Deux sources de donnees:
 * 1. RSC payload (React Server Components) -- richest data
 * 2. JSON-LD structured data -- fallback
 */

import { SiteExtractor } from './base.js';

// ── URL patterns ────────────────────────────────────────────────────

export const AS24_URL_PATTERNS = [
  /autoscout24\.\w+\/(?:fr|de|it|en|nl|es)?\/?d\//,
  /autoscout24\.\w+\/angebote\//,
  /autoscout24\.\w+\/offerte\//,
  /autoscout24\.\w+\/ofertas\//,
  /autoscout24\.\w+\/aanbod\//,
];

const AD_PAGE_PATTERN = /autoscout24\.\w+\/.*\/d\/.*-\d+/;

// ── Fuel type mapping ───────────────────────────────────────────────

const FUEL_MAP = {
  gasoline: 'Essence',
  diesel: 'Diesel',
  electric: 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  cng: 'GPL',
  lpg: 'GPL',
  hydrogen: 'Hydrogene',
};

/**
 * Maps an AutoScout24 fuel type key to a French label.
 * Returns the original value if no mapping exists.
 * @param {string} fuelType
 * @returns {string}
 */
export function mapFuelType(fuelType) {
  return FUEL_MAP[fuelType] || fuelType;
}

// ── Transmission mapping ────────────────────────────────────────────

const TRANSMISSION_MAP = {
  automatic: 'Automatique',
  manual: 'Manuelle',
  'semi-automatic': 'Automatique',
};

/**
 * Maps an AutoScout24 transmission key to a French label.
 * Returns the original value if no mapping exists.
 * @param {string} transmission
 * @returns {string}
 */
export function mapTransmission(transmission) {
  return TRANSMISSION_MAP[transmission] || transmission;
}

// ── RSC payload parsing (DOM-dependent) ─────────────────────────────

/**
 * Parses the RSC (React Server Components) payload from the page.
 * Searches all script tags for JSON containing vehicle data.
 * @param {Document} doc
 * @returns {object|null}
 */
export function parseRSCPayload(doc) {
  const scripts = doc.querySelectorAll('script');
  for (const script of scripts) {
    const text = script.textContent || '';
    if (!text.includes('"vehicleCategory"') && !text.includes('"firstRegistrationDate"')) {
      continue;
    }
    // RSC payloads embed JSON objects within the script; find the vehicle object
    const matches = text.match(/\{[^{}]*"vehicleCategory"[^]*?\}/g);
    if (!matches) continue;
    for (const candidate of matches) {
      try {
        const parsed = JSON.parse(candidate);
        if (parsed.make && parsed.model) return parsed;
      } catch {
        // Not valid JSON, try next candidate
      }
    }
  }
  return null;
}

// ── JSON-LD parsing (DOM-dependent) ─────────────────────────────────

/**
 * Parses JSON-LD structured data from the page.
 * @param {Document} doc
 * @returns {object|null}
 */
export function parseJsonLd(doc) {
  const scripts = doc.querySelectorAll('script[type="application/ld+json"]');
  for (const script of scripts) {
    try {
      const data = JSON.parse(script.textContent || '');
      if (data['@type'] === 'Car') return data;
      // Some pages wrap in @graph
      if (Array.isArray(data['@graph'])) {
        const car = data['@graph'].find((item) => item['@type'] === 'Car');
        if (car) return car;
      }
    } catch {
      // Malformed JSON-LD, skip
    }
  }
  return null;
}

// ── Normalize to ad_data ────────────────────────────────────────────

/**
 * Normalizes RSC and/or JSON-LD data into the extract_ad_data() format
 * expected by the backend /api/analyze endpoint.
 *
 * @param {object|null} rsc - RSC vehicle payload
 * @param {object|null} jsonLd - JSON-LD structured data
 * @returns {object}
 */
export function normalizeToAdData(rsc, jsonLd) {
  const ld = jsonLd || {};
  const offers = ld.offers || {};
  const seller = offers.seller || {};
  const sellerAddress = seller.address || {};
  const engine = ld.vehicleEngine || {};

  // Determine owner_type: pro if sellerId exists (RSC) or seller is AutoDealer (JSON-LD)
  function resolveOwnerType() {
    if (rsc && rsc.sellerId) return 'pro';
    if (seller['@type'] === 'AutoDealer') return 'pro';
    return 'private';
  }

  // RSC-first extraction with JSON-LD fallback
  if (rsc) {
    return {
      title: rsc.versionFullName || ld.name || null,
      price_eur: rsc.price ?? offers.price ?? null,
      currency: offers.priceCurrency || null,
      make: rsc.make?.name || ld.brand?.name || null,
      model: rsc.model?.name || ld.model || null,
      year_model: rsc.firstRegistrationYear || ld.vehicleModelDate || null,
      mileage_km: rsc.mileage ?? ld.mileageFromOdometer?.value ?? null,
      fuel: rsc.fuelType ? mapFuelType(rsc.fuelType) : (engine.fuelType || null),
      gearbox: rsc.transmissionType
        ? mapTransmission(rsc.transmissionType)
        : (ld.vehicleTransmission || null),
      doors: rsc.doors ?? ld.numberOfDoors ?? null,
      seats: rsc.seats ?? ld.vehicleSeatingCapacity ?? null,
      first_registration: rsc.firstRegistrationDate || null,
      color: rsc.bodyColor || ld.color || null,
      power_fiscal_cv: null,
      power_din_hp: rsc.horsePower ?? engine.enginePower?.value ?? null,
      location: {
        city: sellerAddress.addressLocality || null,
        zipcode: sellerAddress.postalCode || null,
        department: null,
        region: null,
        lat: null,
        lng: null,
      },
      phone: seller.telephone || null,
      description: rsc.teaser || null,
      owner_type: resolveOwnerType(),
      owner_name: seller.name || null,
      siret: null,
      raw_attributes: {},
      image_count: Array.isArray(rsc.images) ? rsc.images.length : 0,
      has_phone: Boolean(seller.telephone),
      has_urgent: false,
      has_highlight: false,
      has_boost: false,
      publication_date: rsc.createdDate || null,
      days_online: null,
      index_date: rsc.lastModifiedDate || null,
      days_since_refresh: null,
      republished: false,
      lbc_estimation: null,
    };
  }

  // JSON-LD only (no RSC)
  return {
    title: ld.name || null,
    price_eur: offers.price ?? null,
    currency: offers.priceCurrency || null,
    make: ld.brand?.name || null,
    model: ld.model || null,
    year_model: ld.vehicleModelDate || null,
    mileage_km: ld.mileageFromOdometer?.value ?? null,
    fuel: engine.fuelType || null,
    gearbox: ld.vehicleTransmission || null,
    doors: ld.numberOfDoors ?? null,
    seats: ld.vehicleSeatingCapacity ?? null,
    first_registration: null,
    color: ld.color || null,
    power_fiscal_cv: null,
    power_din_hp: engine.enginePower?.value ?? null,
    location: {
      city: sellerAddress.addressLocality || null,
      zipcode: sellerAddress.postalCode || null,
      department: null,
      region: null,
      lat: null,
      lng: null,
    },
    phone: seller.telephone || null,
    description: null,
    owner_type: resolveOwnerType(),
    owner_name: seller.name || null,
    siret: null,
    raw_attributes: {},
    image_count: 0,
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

// ── Bonus signals ───────────────────────────────────────────────────

/**
 * Builds bonus signals from RSC and JSON-LD data.
 * Each signal has {label, value, status}.
 *
 * @param {object|null} rsc
 * @param {object|null} jsonLd
 * @returns {Array<{label: string, value: string, status: string}>}
 */
export function buildBonusSignals(rsc, jsonLd) {
  const signals = [];
  if (!rsc) return signals;

  // Accident
  if (typeof rsc.hadAccident === 'boolean') {
    signals.push({
      label: 'Accident',
      value: rsc.hadAccident ? 'Oui' : 'Non',
      status: rsc.hadAccident ? 'fail' : 'pass',
    });
  }

  // CT (inspected)
  if (typeof rsc.inspected === 'boolean') {
    signals.push({
      label: 'CT',
      value: rsc.inspected ? 'Passe' : 'Non communique',
      status: rsc.inspected ? 'pass' : 'warning',
    });
  }

  // Warranty
  if (rsc.warranty && rsc.warranty.duration) {
    signals.push({
      label: 'Garantie',
      value: `${rsc.warranty.duration} mois / ${rsc.warranty.mileage || '?'} km`,
      status: 'pass',
    });
  }

  // List price + decote
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

  // Google rating from seller
  const ld = jsonLd || {};
  const seller = ld.offers?.seller || {};
  const rating = seller.aggregateRating;
  if (rating && rating.ratingValue) {
    signals.push({
      label: 'Note Google',
      value: `${rating.ratingValue}/5 (${rating.reviewCount} avis)`,
      status: 'info',
    });
  }

  // Direct import
  if (rsc.directImport === true) {
    signals.push({
      label: 'Import',
      value: 'Import direct',
      status: 'warning',
    });
  }

  return signals;
}

// ── AutoScout24Extractor class ──────────────────────────────────────

export class AutoScout24Extractor extends SiteExtractor {
  static SITE_ID = 'autoscout24';
  static URL_PATTERNS = AS24_URL_PATTERNS;

  /** @type {object|null} Cached RSC data */
  _rsc = null;
  /** @type {object|null} Cached JSON-LD data */
  _jsonLd = null;
  /** @type {object|null} Cached ad_data */
  _adData = null;

  /**
   * @param {string} url
   * @returns {boolean}
   */
  isAdPage(url) {
    return AD_PAGE_PATTERN.test(url);
  }

  /**
   * Extracts vehicle data from the current page.
   * @returns {Promise<{type: string, source: string, ad_data: object}|null>}
   */
  async extract() {
    this._rsc = parseRSCPayload(document);
    this._jsonLd = parseJsonLd(document);

    if (!this._rsc && !this._jsonLd) return null;

    this._adData = normalizeToAdData(this._rsc, this._jsonLd);

    return {
      type: 'normalized',
      source: 'autoscout24',
      ad_data: this._adData,
    };
  }

  /**
   * @returns {{make: string, model: string, year: string}|null}
   */
  getVehicleSummary() {
    if (!this._adData) return null;
    return {
      make: this._adData.make || '',
      model: this._adData.model || '',
      year: String(this._adData.year_model || ''),
    };
  }

  /**
   * @returns {boolean}
   */
  isLoggedIn() {
    return false;
  }

  /**
   * @returns {Array<{label: string, value: string, status: string}>}
   */
  getBonusSignals() {
    return buildBonusSignals(this._rsc, this._jsonLd);
  }
}
