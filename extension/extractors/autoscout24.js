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

// TLD → country mapping for region field
const TLD_TO_COUNTRY = {
  ch: 'Suisse',
  de: 'Allemagne',
  fr: 'France',
  it: 'Italie',
  at: 'Autriche',
  be: 'Belgique',
  nl: 'Pays-Bas',
  es: 'Espagne',
};

// TLD → currency
const TLD_TO_CURRENCY = {
  ch: 'CHF',
};

// CHF → EUR rate (same as backend currency_service.py)
const CHF_TO_EUR = 0.94;

// Minimum prices to submit
const MIN_PRICES = 5;

// ── Fuel type mapping ───────────────────────────────────────────────

const FUEL_MAP = {
  gasoline: 'Essence',
  diesel: 'Diesel',
  electric: 'Electrique',
  'mhev-diesel': 'Diesel',
  'mhev-gasoline': 'Essence',
  'phev-diesel': 'Hybride Rechargeable',
  'phev-gasoline': 'Hybride Rechargeable',
  cng: 'GNV',
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
  const key = (fuelType || '').toLowerCase();
  return FUEL_MAP[key] || fuelType;
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
  const key = (transmission || '').toLowerCase();
  return TRANSMISSION_MAP[key] || transmission;
}

// ── RSC payload parsing (DOM-dependent) ─────────────────────────────

/**
 * Extracts balanced JSON objects from a string starting at each '{'.
 * Uses a brace counter to handle nested objects correctly.
 * @param {string} text
 * @returns {Generator<string>}
 */
function* extractJsonObjects(text) {
  let i = 0;
  while (i < text.length) {
    if (text[i] !== '{') { i++; continue; }
    let depth = 0;
    let inString = false;
    let escape = false;
    const start = i;
    for (let j = i; j < text.length; j++) {
      const ch = text[j];
      if (escape) { escape = false; continue; }
      if (ch === '\\' && inString) { escape = true; continue; }
      if (ch === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth === 0) {
          yield text.slice(start, j + 1);
          i = j + 1;
          break;
        }
      }
      if (j === text.length - 1) i = j + 1; // unbalanced, skip
    }
    if (depth !== 0) break; // unbalanced remainder, stop
  }
}

/**
 * Parses the RSC (React Server Components) payload from the page.
 * Searches all script tags for JSON containing vehicle data.
 * Uses balanced brace extraction for robust nested JSON handling.
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
    for (const candidate of extractJsonObjects(text)) {
      if (!candidate.includes('"vehicleCategory"') && !candidate.includes('"firstRegistrationDate"')) {
        continue;
      }
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

  // Resolve make/model: RSC can return string ("AUDI") or object ({name: "AUDI"})
  function resolveMake() {
    if (rsc) {
      const m = typeof rsc.make === 'string' ? rsc.make : rsc.make?.name;
      if (m) return m;
    }
    return ld.brand?.name || (typeof ld.brand === 'string' ? ld.brand : null) || null;
  }
  function resolveModel() {
    if (rsc) {
      const m = typeof rsc.model === 'string' ? rsc.model : rsc.model?.name;
      if (m) return m;
    }
    return ld.model || null;
  }

  // RSC-first extraction with JSON-LD fallback
  if (rsc) {
    return {
      title: rsc.versionFullName || ld.name || null,
      price_eur: rsc.price ?? offers.price ?? null,
      currency: offers.priceCurrency || null,
      make: resolveMake(),
      model: resolveModel(),
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

// ── Search helpers for market price collection ──────────────────────

/**
 * Extracts the TLD from an AutoScout24 URL.
 * @param {string} url
 * @returns {string} e.g. 'ch', 'de', 'fr'
 */
export function extractTld(url) {
  const match = url.match(/autoscout24\.(\w+)/);
  return match ? match[1] : 'de';
}

/**
 * Builds an AutoScout24 search URL for similar vehicles.
 * @param {string} makeKey - Lowercase make key (e.g. 'audi')
 * @param {string} modelKey - Lowercase model key (e.g. 'q5')
 * @param {number} year - Target year
 * @param {string} tld - TLD (e.g. 'ch', 'de')
 * @param {object} [options]
 * @param {number} [options.yearSpread=1] - Year range (+/-)
 * @param {string} [options.fuel] - AS24 fuel key (e.g. 'diesel')
 * @returns {string}
 */
export function buildSearchUrl(makeKey, modelKey, year, tld, options = {}) {
  const { yearSpread = 1, fuel } = options;
  const base = `https://www.autoscout24.${tld}/lst/${makeKey}/${modelKey}`;
  const params = new URLSearchParams({
    fregfrom: String(year - yearSpread),
    fregto: String(year + yearSpread),
    sort: 'standard',
    desc: '0',
    atype: 'C',
    'ustate': 'N,U',
  });
  if (fuel) params.set('fuel', fuel);
  return `${base}?${params}`;
}

/**
 * Parses AS24 search result page to extract vehicle prices.
 * Looks for listing data in script tags (RSC/Next.js chunks).
 * @param {string} html - Raw HTML of search page
 * @returns {Array<{price: number, year: number|null, km: number|null, fuel: string|null}>}
 */
export function parseSearchPrices(html) {
  const results = [];
  // AS24 search results embed listing JSON in script tags.
  // Each listing has "price" and "mileage" keys.
  const listingPattern = /"price"\s*:\s*(\d+).*?"mileage"\s*:\s*(\d+)/g;
  let match;
  while ((match = listingPattern.exec(html)) !== null) {
    const price = parseInt(match[1], 10);
    const mileage = parseInt(match[2], 10);
    if (price > 500 && price < 500000) {
      results.push({ price, year: null, km: mileage, fuel: null });
    }
  }

  // Deduplicate by price+km (same listing can appear in multiple RSC chunks)
  const seen = new Set();
  return results.filter((r) => {
    const key = `${r.price}-${r.km}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
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
   * AS24 phone data is public (JSON-LD), no login needed.
   * @returns {boolean}
   */
  isLoggedIn() {
    return true;
  }

  /**
   * Returns the phone number already extracted from JSON-LD.
   * No DOM interaction needed (unlike LBC where a button click reveals it).
   * @returns {Promise<string|null>}
   */
  async revealPhone() {
    return this._adData?.phone || null;
  }

  /**
   * AS24 ads include the phone in JSON-LD (seller.telephone).
   * @returns {boolean}
   */
  hasPhone() {
    return Boolean(this._adData?.phone);
  }

  /**
   * @returns {Array<{label: string, value: string, status: string}>}
   */
  getBonusSignals() {
    return buildBonusSignals(this._rsc, this._jsonLd);
  }

  /**
   * Collects market prices from AS24 search results for the current vehicle.
   * Fetches a search page, parses prices, converts CHF→EUR if needed,
   * and submits to the backend /api/market-prices endpoint.
   *
   * @param {object} progress - Progress tracker for UI updates
   * @returns {Promise<{submitted: boolean, isCurrentVehicle: boolean}>}
   */
  async collectMarketPrices(progress) {
    if (!this._adData?.make || !this._adData?.model || !this._adData?.year_model) {
      return { submitted: false, isCurrentVehicle: false };
    }
    if (!this._fetch || !this._apiUrl) {
      console.warn('[CoPilot] AS24 collectMarketPrices: deps not injected');
      return { submitted: false, isCurrentVehicle: false };
    }

    const tld = extractTld(window.location.href);
    const country = TLD_TO_COUNTRY[tld] || 'Europe';
    const currency = TLD_TO_CURRENCY[tld] || 'EUR';
    const makeKey = (this._rsc?.make?.key || this._adData.make).toLowerCase();
    const modelKey = (this._rsc?.model?.key || this._adData.model).toLowerCase();
    const year = parseInt(this._adData.year_model, 10);
    const fuelKey = this._rsc?.fuelType || null;

    if (progress) progress.update('job', 'done', `${this._adData.make} ${this._adData.model} ${year} (${country})`);

    // Strategy 1: precise (same TLD, ±1 year, with fuel)
    // Strategy 2: wider (same TLD, ±2 years, no fuel filter)
    const strategies = [
      { yearSpread: 1, fuel: fuelKey, precision: 4, label: 'précise' },
      { yearSpread: 2, fuel: null, precision: 3, label: 'élargie' },
    ];

    let prices = [];
    let usedPrecision = 3;

    for (const strat of strategies) {
      const searchUrl = buildSearchUrl(makeKey, modelKey, year, tld, {
        yearSpread: strat.yearSpread,
        fuel: strat.fuel,
      });

      if (progress) progress.update('collect', 'running', `Recherche ${strat.label}...`);

      try {
        const resp = await fetch(searchUrl, { credentials: 'same-origin' });
        if (!resp.ok) {
          console.warn(`[CoPilot] AS24 search HTTP ${resp.status}: ${searchUrl}`);
          continue;
        }
        const html = await resp.text();
        prices = parseSearchPrices(html);
        usedPrecision = strat.precision;

        if (prices.length >= MIN_PRICES) {
          if (progress) progress.update('collect', 'done', `${prices.length} annonces trouvées`);
          break;
        }
      } catch (err) {
        console.error('[CoPilot] AS24 search error:', err);
      }
    }

    if (prices.length < MIN_PRICES) {
      if (progress) {
        progress.update('collect', 'warning', `${prices.length} annonces (min ${MIN_PRICES})`);
        progress.update('submit', 'skip', 'Pas assez de données');
        progress.update('bonus', 'skip');
      }
      return { submitted: false, isCurrentVehicle: true };
    }

    // Convert CHF to EUR if needed (market prices must be EUR in backend)
    let priceInts = prices.map((p) => p.price);
    let priceDetails = prices;
    if (currency === 'CHF') {
      priceInts = priceInts.map((p) => Math.round(p * CHF_TO_EUR));
      priceDetails = prices.map((p) => ({
        ...p,
        price: Math.round(p.price * CHF_TO_EUR),
      }));
    }

    // Submit to backend
    if (progress) progress.update('submit', 'running');
    const marketUrl = this._apiUrl.replace('/analyze', '/market-prices');
    const payload = {
      make: this._adData.make,
      model: this._adData.model,
      year,
      region: country,
      prices: priceInts,
      price_details: priceDetails,
      fuel: this._adData.fuel ? this._adData.fuel.toLowerCase() : null,
      precision: usedPrecision,
    };

    try {
      const resp = await this._fetch(marketUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (resp.ok) {
        if (progress) progress.update('submit', 'done', `${priceInts.length} prix envoyés (${country})`);
        if (progress) progress.update('bonus', 'skip', 'Pas de jobs bonus');
        return { submitted: true, isCurrentVehicle: true };
      }

      const errBody = await resp.json().catch(() => null);
      console.warn('[CoPilot] AS24 market-prices POST failed:', resp.status, errBody);
      if (progress) progress.update('submit', 'error', `Erreur serveur (${resp.status})`);
    } catch (err) {
      console.error('[CoPilot] AS24 market-prices POST error:', err);
      if (progress) progress.update('submit', 'error', 'Erreur réseau');
    }

    if (progress) progress.update('bonus', 'skip');
    return { submitted: false, isCurrentVehicle: true };
  }
}
